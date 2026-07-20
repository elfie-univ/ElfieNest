from __future__ import annotations

import hashlib
import logging
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Union

from elfie.body import BipedAnatomy, BodyBinding, BodyRegistry, QuadrupedAnatomy
from elfie.body.native.anatomy.base import SomaticAnatomy
from elfie.body.port import BodyPort
from elfie.body.types import BodyCommand, BodyEvent, CommandResult
from elfie.brain import (
    EmotionDecayCalculator,
    EmotionSystem,
    HypothalamusEnergy,
    ThalamusContextBuilder,
)
from elfie.brain.cognition import NeocortexBrain
from elfie.brain.memory import MemorySystem
from elfie.communication import (
    CommunicationHub,
    CommunicationMessage,
    DeliveryReceipt,
    MessageKind,
)
from elfie.nervous_system import NervousSystem
from elfie.profile import (
    ElfieProfile as CharacterProfile,
)
from elfie.profile import (
    ElfieProfileRepository,
    create_visual_profile,
)
from elfie.skills import SkillManager
from elfie.state import (
    ElfieState,
    ElfieStateRepository,
    capture_elfie_state,
    restore_elfie_state,
)

logger = logging.getLogger("elfie.elfie")


class Elfie:
    """完整精灵聚合对象，复用现有认知、记忆、情绪和动作算法。"""

    def __init__(
        self,
        config_dir: str = None,
        anatomy_type: str | None = None,
        elfie_id: str | None = None,
        memory_db_path: str | None = None,
        character_profile: CharacterProfile | None = None,
        body: BodyPort | None = None,
        communication: CommunicationHub | None = None,
        skills: SkillManager | None = None,
    ):
        """
        初始化生命管理器
        :param config_dir: 配置目录
        :param anatomy_type: 旧身体形态参数；新代码优先使用 profile.embodiment
        :param elfie_id: 正式运行或测试环境中的稳定精灵标识（可选）
        :param memory_db_path: 开发工具可指定的独立记忆数据库路径（可选）
        :param character_profile: 已解析的稳定个体档案；省略时从配置目录加载
        :param body: 可选的身体端口；省略时保持原有直接传感调用路径
        """
        self._state_config_dir = (
            Path(config_dir).expanduser() if config_dir is not None else None
        )
        # 1. 🧠 【大脑认知层】 (Cognition)
        self.brain = NeocortexBrain(config_dir, elfie_id=elfie_id)

        self.character_profile = self._load_character_profile(
            config_dir=config_dir,
            elfie_id=elfie_id,
            supplied=character_profile,
        )
        self.species_id = self.character_profile.identity.species_id

        limits_dict = self.brain.profile.system_limits
        caps_dict = self.brain.profile.capabilities

        # 2. 🧬 【情绪与边缘系统】 (Core Systems)
        self.thalamus = ThalamusContextBuilder()
        self.hypothalamus = HypothalamusEnergy(limits_dict)
        self.amygdala = EmotionSystem()
        self.emotion_decay = EmotionDecayCalculator()
        resolved_memory_db_path = memory_db_path or (
            str(Path(config_dir) / "graph_memory.db") if config_dir else ":memory:"
        )
        personality_path = None
        if config_dir:
            config_path = Path(config_dir)
            for filename in ("profile.yaml", "personality.yaml"):
                candidate = config_path / filename
                if candidate.is_file():
                    personality_path = str(candidate)
                    break
        self.memory = MemorySystem(
            db_path=resolved_memory_db_path,
            personality_path=personality_path,
            elfie_id=elfie_id,
            config_dir=config_dir,
            personality_data=self.character_profile.personality or None,
        )
        self._was_sleeping = False

        # 3. 🔌 【神经系统层】 (Nervous System)
        self.nervous_system = NervousSystem(caps_dict)

        # 4. 🧱 【具身身体物理层】 (Body - 数字孪生躯体)
        self.anatomy_type = self._resolve_primary_morphology(anatomy_type)
        self.anatomy: SomaticAnatomy
        if self.anatomy_type == "quadruped":
            self.anatomy = QuadrupedAnatomy()
        else:
            self.anatomy = BipedAnatomy()

        # 仿真内的时间相角累加器
        self.elapsed_time = 0.0

        # 身体注册与当前绑定。
        self.body_registry = BodyRegistry()
        self.body_binding = BodyBinding(self.body_registry)
        self.body_binding.attach(body)

        self._last_expression: Optional[Dict[str, Any]] = None
        self.communication = (
            communication
            if communication is not None
            else CommunicationHub(self.character_profile.identity.elfie_id)
        )
        self.communication.bind_identity(self.character_profile.identity.elfie_id)
        self.skills = skills if skills is not None else SkillManager()

    def bind_identity(self, elfie_id: str) -> None:
        """注册进房间时补齐身份，让粮食策略和记忆任务读取同一精灵配置。"""
        self.brain.elfie_id = elfie_id
        self.memory.bind_elfie_identity(elfie_id, self.brain.config_dir)
        if self.character_profile.identity.elfie_id != elfie_id:
            self.character_profile = replace(
                self.character_profile,
                identity=replace(self.character_profile.identity, elfie_id=elfie_id),
            )
        self.communication.bind_identity(elfie_id)

    def _load_character_profile(
        self,
        *,
        config_dir: str | None,
        elfie_id: str | None,
        supplied: CharacterProfile | None,
    ) -> CharacterProfile:
        if supplied is not None:
            supplied.validate()
            return supplied
        if config_dir:
            repository = ElfieProfileRepository(config_dir)
            if repository.exists():
                return repository.load()

        personality = getattr(self.brain.profile, "personality", {})
        metadata = (
            personality.get("metadata", {}) if isinstance(personality, dict) else {}
        )
        appearance = (
            metadata.get("appearance", {}) if isinstance(metadata, dict) else {}
        )
        if not isinstance(appearance, dict):
            appearance = {}
        species_id = appearance.get("species", "fox")
        if species_id not in ("dog", "fox"):
            species_id = "fox"
        stable_id = elfie_id or "elfie_default"
        seed = int.from_bytes(
            hashlib.sha256(stable_id.encode("utf-8")).digest()[:8], "big"
        )
        profile = create_visual_profile(
            elfie_id=stable_id,
            display_name=str(metadata.get("name") or stable_id),
            species_id=species_id,
            seed=seed,
            height_direction=str(appearance.get("height", "standard")),
            build_direction=str(appearance.get("build", "standard")),
        )
        return replace(
            profile,
            personality=dict(self.brain.profile.personality),
            capabilities=dict(self.brain.profile.capabilities),
            system_limits=dict(self.brain.profile.system_limits),
        )

    def _resolve_primary_morphology(self, legacy_anatomy_type: str | None) -> str:
        """新档案字段优先；旧 anatomy_type 只作为测试和老配置兜底。"""
        if legacy_anatomy_type:
            return legacy_anatomy_type
        embodiment = getattr(self.character_profile, "embodiment", None)
        morphology = getattr(embodiment, "primary_morphology", "biped")
        return str(morphology or "biped")

    def register_body(self, body: BodyPort, *, make_current: bool = False) -> None:
        """登记一副可用身体，并可通过正式生命周期将其设为当前身体。"""
        self.body_binding.register(body)
        if make_current:
            self.body_binding.bind(body.body_id)

    def bind_body(self, body_id: str) -> BodyPort:
        """切换当前身体，负责旧身体断开和新身体连接。"""
        return self.body_binding.bind(body_id)

    def unbind_body(self) -> BodyPort | None:
        """断开并解除当前身体绑定。"""
        return self.body_binding.unbind()

    @property
    def profile(self) -> CharacterProfile:
        return self.character_profile

    @property
    def identity(self):
        return self.character_profile.identity

    @property
    def current_body(self) -> BodyPort | None:
        return self.body_binding.current

    def tick(self, dt: float):
        """
        由世界引擎（或主周期）定时驱动的精灵生理与时间相角 Tick
        :param dt: 过去的时间步长 (秒)
        """
        self.elapsed_time += dt

        # (A) 下丘脑生理钟时钟钟摆 Tick 衰减
        self.hypothalamus.update_clock(dt)

        # (B) 杏仁核情绪自然半衰期衰减
        self.emotion_decay.decay_emotions(self.amygdala, dt)

        # (C) 检查情绪变化，发送表达事件到 Godot
        self._send_emotion_expression()

    def _send_emotion_expression(self):
        """检查情绪表达变化并通过当前身体发送。"""
        body = self.current_body
        if body is None:
            return

        expression = self.amygdala.get_expression()
        if not expression:
            return

        # 检查表达是否发生变化
        if self._last_expression is None:
            should_send = True
        elif self._last_expression.get("expression") != expression.get(
            "expression"
        ) or self._last_expression.get("emotion") != expression.get("emotion"):
            should_send = True
        else:
            should_send = False

        if should_send:
            self.execute_body_command(
                BodyCommand(
                    action="face.expression",
                    parameters={"expression": expression},
                )
            )
            self._last_expression = expression

    def receive_body_events(
        self,
        additional_events: Iterable[BodyEvent] = (),
    ) -> Dict[str, Any]:
        """读取当前身体事件，并接收世界层补充的同类感觉事件。"""
        body = self.current_body
        events = list(body.read_events()) if body is not None else []
        events.extend(additional_events)
        return self.nervous_system.receive(events)

    def execute_body_command(self, command: BodyCommand) -> CommandResult:
        """通过神经系统的唯一控制出口驱动当前身体。"""
        body = self.current_body
        if body is None:
            raise RuntimeError("Elfie 尚未绑定 BodyPort")
        return self.nervous_system.control(body, command)

    def perceive_body_and_respond(
        self,
        runtime_agent: Any,
        debug_trace: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """从当前身体读取传感事件，复用原有认知链并记录语义动作。"""
        if self.current_body is None:
            raise RuntimeError("Elfie 尚未绑定 BodyPort")

        result = self.respond_to_body_events(
            (),
            runtime_agent,
            debug_trace=debug_trace,
        )
        action = str(result.get("action") or "")
        if not action:
            return result

        command = BodyCommand(
            action=action,
            parameters={
                "speech": result.get("speech", ""),
                "mutter": result.get("mutter", ""),
                "joint_angles": result.get("joint_angles", {}),
            },
        )
        execution = self.execute_body_command(command)
        result = {**result, "body_execution": execution.to_dict()}
        if debug_trace is not None:
            debug_trace.setdefault("stages", {})["body_output"] = execution.to_dict()
        return result

    def respond_to_body_events(
        self,
        additional_events: Iterable[BodyEvent],
        runtime_agent: Any,
        debug_trace: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """正式具身入口：BodyEvent 进入神经系统，再复用现有认知链。"""
        raw_sensor_data = self.receive_body_events(additional_events)
        if not raw_sensor_data["sensory_events"]:
            return {
                "success": True,
                "filtered": True,
                "reason": "No body events, skipped.",
            }
        return self.perceive_and_respond(
            raw_sensor_data,
            runtime_agent,
            debug_trace=debug_trace,
        )

    def perceive_and_respond(
        self,
        raw_sensor_data: Dict[str, Any],
        runtime_agent: Any,
        debug_trace: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        具身认知与反馈 Somatic Loop 闭环主神经冲动链路：
        1. 脑干反射弧检测：瞬间响应强碰撞避险/抚摸打呼（毫秒级自律反射，绕过大脑皮层）
        2. 底层感知大坝噪点过滤
        3. 中层丘脑拼装具身 Context (视觉 Viewport、空间听觉与触觉)
        4. 顶层大脑皮层多模态大模型思考
        5. 交互总线形态学动作硬拦截 (形态学限制，防动作幻觉)
        6. 下发小脑进行关节角度时序转换，声学合成发音，写入海马体
        """
        runtime_agent = self.skills.wrap_runtime(runtime_agent)
        mutter_msg: str | None
        if debug_trace is not None:
            debug_trace.clear()
            debug_trace.update(
                {
                    "raw_input": dict(raw_sensor_data),
                    "stages": {},
                    "warnings": [],
                }
            )

        # A0. 睡眠→唤醒边沿检测（在早期 return 之前更新状态）
        currently_sleeping = self.hypothalamus.is_sleeping
        should_consolidate = self._was_sleeping and not currently_sleeping
        self._was_sleeping = currently_sleeping

        # A. 睡眠熔断机制
        if self.hypothalamus.is_sleeping:
            sleep_mutter = self.nervous_system.mutter("sleeping")
            if debug_trace is not None:
                debug_trace["stages"]["sleep_gate"] = {
                    "sleeping": True,
                    "reason": "Elfie is sleeping",
                }
            return {
                "success": False,
                "reason": "Elfie is sleeping",
                "speech": "",
                "action": "blink_eyes",
                "mutter": sleep_mutter,
            }

        # A1. 刚刚唤醒 → 执行夜间记忆巩固（在 pass-through 路径上）
        if should_consolidate:
            if runtime_agent:
                self.memory.run_consolidation(runtime_agent)

        # B. 【脑干自律物理反射弧】 瞬间检测
        # 从原始传感器中捕获触觉信号 (通常来自 Godot Collision/Area3D)
        tactile_data = {
            "impact_force": raw_sensor_data.get("impact_force", 0.0),
            "impact_direction": raw_sensor_data.get("impact_direction", "none"),
            "gentle_stroke": raw_sensor_data.get("gentle_stroke", 0.0),
        }

        override_joints, reflex_event = self.nervous_system.process_reflex(
            anatomy=self.anatomy,
            tactile_sensor=tactile_data,
            emotion_system=self.amygdala,
        )
        if debug_trace is not None:
            debug_trace["stages"]["brainstem_reflex"] = {
                "tactile_input": tactile_data,
                "event": dict(reflex_event),
            }

        if reflex_event["triggered"]:
            # 反射触发：绕过大脑皮层，直接产生肢体避险动作与情绪变动
            logger.warning(
                f"⚡ [脑干自律反射生效] 触发反射类型: {reflex_event['type']}"
            )

            # 发声和碎碎念表达触觉受刺激
            speech_text = reflex_event["msg"]
            mutter_msg = f"(触发了 {reflex_event['type']} 的自主神经反射弧哒！)"

            self.nervous_system.speak(speech_text, self.anatomy.voice_profile)

            # 将紧急反射记录进海马体
            dominant_mood = self.amygdala.get_dominant_mood()
            memory_id = self.memory.record_episode(
                content=f"【脑干反射】 遭遇外界刺激: {speech_text}",
                emotion=dominant_mood,
                intensity=self.amygdala.get_emotion_value(dominant_mood),
            )

            if debug_trace is not None:
                debug_trace["stages"]["execution"] = {
                    "path": "brainstem_reflex",
                    "speech": speech_text,
                    "action": "reflex_avoidance"
                    if reflex_event["type"] == "shock_avoidance"
                    else "reflex_soothing",
                    "joint_angles": {
                        k: round(v, 3) for k, v in override_joints.items()
                    },
                }
                debug_trace["stages"]["memory_write"] = {
                    "episode_id": memory_id,
                    "written": bool(memory_id),
                }

            return {
                "success": True,
                "speech": speech_text,
                "action": "reflex_avoidance"
                if reflex_event["type"] == "shock_avoidance"
                else "reflex_soothing",
                "mutter": mutter_msg,
                "joint_angles": {k: round(v, 3) for k, v in override_joints.items()},
            }

        # 1. 交互总线感知大坝过滤
        has_valuable_change = self.nervous_system.filter_signals(raw_sensor_data)
        if debug_trace is not None:
            debug_trace["stages"]["sensory_filter"] = {
                "passed": has_valuable_change,
                "reason": "valuable_change"
                if has_valuable_change
                else "no_sensory_changes",
            }
        if not has_valuable_change:
            return {
                "success": True,
                "filtered": True,
                "reason": "No sensory changes, skipped.",
            }

        # 检测是否本地模型（没有配置任何远程 API Key）
        config = runtime_agent.config
        is_local = not any(
            provider != "ollama" and info.get("api_key", "")
            for provider, info in config.providers.items()
        )

        # 2. 中层丘脑组装具身 Context
        context = self.thalamus.assemble(
            raw_sensors=raw_sensor_data,
            energy_system=self.hypothalamus,
            emotion_engine=self.amygdala,
            memory_system=self.memory,
            is_local=is_local,
        )

        # 额外将具身形态描述注入 context 以利于大模型认知自己的物理形态
        context.embodied_anatomy = self.anatomy.get_anatomy_descriptor()
        if debug_trace is not None:
            debug_trace["stages"]["thalamus_context"] = asdict(context)

        # 3. 顶层大脑皮层大模型思考
        decision = self.brain.think_and_decide(context, runtime_agent)
        if debug_trace is not None:
            debug_trace["stages"]["decision"] = asdict(decision)

        action = decision.action
        speech_text = decision.speech_text
        mutter_msg = decision.mutter

        # 4. 交互总线躯体物理安全拦截 (形态学限制校验)
        reflex_result = self.nervous_system.validate_action(action, self.anatomy)
        if debug_trace is not None:
            debug_trace["stages"]["action_validation"] = {
                "requested_action": action,
                **dict(reflex_result),
            }
        if not reflex_result["allowed"]:
            # 形态学干涉生效：强制更改为点头，并引发轻微焦虑情绪与物理报错痛感
            logger.warning("❌ [交互总线] 形态学物理硬拦截生效！拦截非法肢体指令。")
            action = "nod_head"
            speech_text = f"哎呦！我的小毛爪撞到形态学物理定律墙壁了哒！{reflex_result['feedback_error']}"
            self.amygdala.update_emotion("anxiety", 15.0)
            self.amygdala.update_emotion("happiness", -10.0)
            mutter_msg = "(动作因形态学不兼容被强行拦截了哒...)"
            if debug_trace is not None:
                debug_trace["warnings"].append(reflex_result["feedback_error"])

        # 5. 执行具体物理驱动
        # (A) 声学发声合成
        self.nervous_system.speak(speech_text, self.anatomy.voice_profile)
        # (B) 小脑时域步态解算与驱动
        actual_joints = self.nervous_system.drive(
            anatomy=self.anatomy,
            action=action,
            speed=1.0,
            elapsed_time=self.elapsed_time,
        )

        # 扣减下丘脑能耗
        runtime_result = self.brain.last_runtime_result
        actual_model = getattr(runtime_result, "actual_model", None)
        is_remote = bool(actual_model and not actual_model.startswith("ollama/"))
        if actual_model is None and not callable(
            getattr(runtime_agent, "run_with_food", None)
        ):
            # 旧 Mock Runtime 没有实际模型信息，沿用原有 Provider 判断。
            config = runtime_agent.config
            is_remote = any(
                provider != "ollama" and info.get("api_key", "")
                for provider, info in config.providers.items()
            )
        self.hypothalamus.consume_energy_by_action(is_remote)

        # 快乐正反馈
        self.amygdala.update_emotion("boredom", -15.0)
        self.amygdala.update_emotion("happiness", 5.0)

        # 6. 将经历记入海马体
        memory_id = ""
        if raw_sensor_data.get("has_new_message"):
            user_msg = raw_sensor_data.get("user_message", "")
            dominant_mood = self.amygdala.get_dominant_mood()
            memory_id = self.memory.record_episode(
                content=f"主人对我说: '{user_msg}'。我回答了: '{speech_text}'，并做了动作 '{action}'。",
                emotion=dominant_mood,
                intensity=self.amygdala.get_emotion_value(dominant_mood),
            )

        if debug_trace is not None:
            debug_trace["stages"]["execution"] = {
                "path": "cortical",
                "speech": speech_text,
                "action": action,
                "mutter": mutter_msg,
                "joint_angles": {k: round(v, 3) for k, v in actual_joints.items()},
            }
            debug_trace["stages"]["memory_write"] = {
                "episode_id": memory_id,
                "written": bool(memory_id),
            }

        return {
            "success": True,
            "speech": speech_text,
            "action": action,
            "mutter": mutter_msg,
            "joint_angles": {k: round(v, 3) for k, v in actual_joints.items()},
        }

    def receive_message(
        self,
        *,
        channel_id: str,
        sender_id: str,
        content: str,
        kind: MessageKind = MessageKind.TEXT,
    ) -> CommunicationMessage:
        return self.communication.receive(
            channel_id=channel_id,
            sender_id=sender_id,
            content=content,
            kind=kind,
        )

    def send_message(
        self,
        *,
        channel_id: str,
        recipient_id: str,
        content: str,
        kind: MessageKind = MessageKind.TEXT,
    ) -> DeliveryReceipt:
        return self.communication.send(
            channel_id=channel_id,
            recipient_id=recipient_id,
            content=content,
            kind=kind,
        )

    def describe(self) -> Dict[str, Any]:
        """返回聚合对象的稳定身份和身体装配摘要。"""
        return {
            "elfie_id": self.identity.elfie_id,
            "display_name": self.identity.display_name,
            "species_id": self.identity.species_id,
            "current_body_id": self.body_binding.current_body_id,
            "available_bodies": [
                descriptor.to_dict() for descriptor in self.body_binding.available()
            ],
            "communication": self.communication.snapshot(),
            "skills": self.skills.snapshot(),
        }

    def snapshot_state(self) -> ElfieState:
        return capture_elfie_state(self)

    def restore_state(
        self,
        state: ElfieState,
        *,
        restore_body: bool = True,
    ) -> bool:
        return restore_elfie_state(self, state, restore_body=restore_body)

    def save_state(
        self,
        config_dir: Optional[Union[str, Path]] = None,
    ) -> Path:
        target = Path(config_dir).expanduser() if config_dir else self._state_config_dir
        if target is None:
            raise ValueError("未提供精灵配置目录，无法保存 state.yaml")
        return ElfieStateRepository(target).save(self.snapshot_state())
