import logging
from typing import Any, Dict, Optional

from elfie.body import BipedAnatomy, QuadrupedAnatomy, SomaticReflexArc
from elfie.body.anatomy.base import SomaticAnatomy
from elfie.brain import (
    EmotionDecayCalculator,
    EmotionSystem,
    HypothalamusEnergy,
    ThalamusContextBuilder,
)
from elfie.brain.cognition import NeocortexBrain
from elfie.brain.memory import MemorySystem
from elfie.interface import (
    MotionActuator,
    MutterActuator,
    PhysicalLimitsReflex,
    SensoryDamSignalFilter,
    SpeechActuator,
)

logger = logging.getLogger("elfie.elfie_individual")


class ElfieIndividual:
    """精灵本体核心管理器 (具身四层生命架构聚合器)"""

    def __init__(
        self, config_dir: str = None, anatomy_type: str = "biped", godot_api=None
    ):
        """
        初始化生命管理器
        :param config_dir: 配置目录
        :param anatomy_type: 身体形态学类型 ("biped" 双足, "quadruped" 四足)
        :param godot_api: Godot API服务器实例（可选）
        """
        # 1. 🧠 【大脑认知层】 (Cognition)
        self.brain = NeocortexBrain(config_dir)

        limits_dict = self.brain.profile.system_limits
        caps_dict = self.brain.profile.capabilities

        # 2. 🧬 【情绪与边缘系统】 (Core Systems)
        self.thalamus = ThalamusContextBuilder()
        self.hypothalamus = HypothalamusEnergy(limits_dict)
        self.amygdala = EmotionSystem()
        self.emotion_decay = EmotionDecayCalculator()
        self.memory = MemorySystem()
        self._was_sleeping = False

        # 3. 🔌 【神经交互总线层】 (Interface)
        self.speech_actuator = SpeechActuator()
        self.motion_actuator = MotionActuator()
        self.mutter_actuator = MutterActuator()
        self.signal_filter = SensoryDamSignalFilter()
        self.safety_reflex = PhysicalLimitsReflex(caps_dict)

        # 4. 🧱 【具身身体物理层】 (Body - 数字孪生躯体)
        self.anatomy_type = anatomy_type
        self.anatomy: SomaticAnatomy
        if anatomy_type == "quadruped":
            self.anatomy = QuadrupedAnatomy()
        else:
            self.anatomy = BipedAnatomy()

        # 脑干自律避险反射弧
        self.brainstem_reflex = SomaticReflexArc()

        # 仿真内的时间相角累加器
        self.elapsed_time = 0.0

        # Godot API 引用（用于发送表达事件）
        self.godot_api = godot_api
        self._last_expression: Optional[Dict[str, Any]] = None

    @property
    def hippocampus(self):
        """向后兼容：旧代码通过 self.hippocampus 访问记忆系统

        Task 20 将移除此属性
        """
        return self.memory

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
        """检查情绪表达变化并发送事件到 Godot"""
        if not self.godot_api:
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
            self.godot_api.send_expression(expression)
            self._last_expression = expression

    def perceive_and_respond(
        self, raw_sensor_data: Dict[str, Any], runtime_agent: Any
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
        # A0. 睡眠→唤醒边沿检测（在早期 return 之前更新状态）
        currently_sleeping = self.hypothalamus.is_sleeping
        should_consolidate = self._was_sleeping and not currently_sleeping
        self._was_sleeping = currently_sleeping

        # A. 睡眠熔断机制
        if self.hypothalamus.is_sleeping:
            sleep_mutter = self.mutter_actuator.mutter("sleeping")
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

        override_joints, reflex_event = self.brainstem_reflex.process_sensory_impact(
            anatomy=self.anatomy, tactile_sensor=tactile_data, amygdala=self.amygdala
        )

        if reflex_event["triggered"]:
            # 反射触发：绕过大脑皮层，直接产生肢体避险动作与情绪变动
            logger.warning(
                f"⚡ [脑干自律反射生效] 触发反射类型: {reflex_event['type']}"
            )

            # 发声和碎碎念表达触觉受刺激
            speech_text = reflex_event["msg"]
            mutter_msg = f"(触发了 {reflex_event['type']} 的自主神经反射弧哒！)"

            self.speech_actuator.synthesize_speech(
                speech_text, self.anatomy.voice_profile
            )

            # 将紧急反射记录进海马体
            dominant_mood = self.amygdala.get_dominant_mood()
            self.memory.record_episode(
                content=f"【脑干反射】 遭遇外界刺激: {speech_text}",
                emotion=dominant_mood,
                intensity=self.amygdala.get_emotion_value(dominant_mood),
            )

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
        has_valuable_change = self.signal_filter.filter_noise(raw_sensor_data)
        if not has_valuable_change:
            return {
                "success": True,
                "filtered": True,
                "reason": "No sensory changes, skipped.",
            }

        # 2. 中层丘脑组装具身 Context
        context = self.thalamus.assemble(
            raw_sensors=raw_sensor_data,
            energy_system=self.hypothalamus,
            emotion_engine=self.amygdala,
            memory_system=self.memory,
        )

        # 额外将具身形态描述注入 context 以利于大模型认知自己的物理形态
        context.embodied_anatomy = self.anatomy.get_anatomy_descriptor()

        # 3. 顶层大脑皮层大模型思考
        decision = self.brain.think_and_decide(context, runtime_agent)

        action = decision.action
        speech_text = decision.speech_text
        mutter_msg = decision.mutter

        # 4. 交互总线躯体物理安全拦截 (形态学限制校验)
        reflex_result = self.safety_reflex.intercept_and_validate(action, self.anatomy)
        if not reflex_result["allowed"]:
            # 形态学干涉生效：强制更改为点头，并引发轻微焦虑情绪与物理报错痛感
            logger.warning("❌ [交互总线] 形态学物理硬拦截生效！拦截非法肢体指令。")
            action = "nod_head"
            speech_text = f"哎呦！我的小毛爪撞到形态学物理定律墙壁了哒！{reflex_result['feedback_error']}"
            self.amygdala.update_emotion("anxiety", 15.0)
            self.amygdala.update_emotion("happiness", -10.0)
            mutter_msg = "(动作因形态学不兼容被强行拦截了哒...)"

        # 5. 执行具体物理驱动
        # (A) 声学发声合成
        self.speech_actuator.synthesize_speech(speech_text, self.anatomy.voice_profile)
        # (B) 小脑时域步态解算与驱动
        actual_joints = self.motion_actuator.translate_and_drive(
            anatomy=self.anatomy,
            action_intent=action,
            speed=1.0,
            elapsed_time=self.elapsed_time,
        )

        # 扣减下丘脑能耗
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
        if raw_sensor_data.get("has_new_message"):
            user_msg = raw_sensor_data.get("user_message", "")
            dominant_mood = self.amygdala.get_dominant_mood()
            self.memory.record_episode(
                content=f"主人对我说: '{user_msg}'。我回答了: '{speech_text}'，并做了动作 '{action}'。",
                emotion=dominant_mood,
                intensity=self.amygdala.get_emotion_value(dominant_mood),
            )

        return {
            "success": True,
            "speech": speech_text,
            "action": action,
            "mutter": mutter_msg,
            "joint_angles": {k: round(v, 3) for k, v in actual_joints.items()},
        }
