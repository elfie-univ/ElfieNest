import logging
from typing import Dict, Any

from elfie.cognition import NeocortexBrain
from elfie.core_systems import ThalamusContextBuilder, HypothalamusEnergy, AmygdalaEmotionalState, EmotionDecayCalculator, EpisodeMemoryManager
from elfie.interface import SpeechActuator, MotionActuator, MutterActuator, SensoryDamSignalFilter, PhysicalLimitsReflex

logger = logging.getLogger("elfie.elfie_individual")

class ElfieIndividual:
    """精灵本体核心管理器 (生命全层架构聚合)"""

    def __init__(self, config_dir: str = None):
        # 1. 顶层：大脑皮层 (认知决策层)
        self.brain = NeocortexBrain(config_dir)
        
        # 从 profile 获取基础 limits 字典
        limits_dict = self.brain.profile.system_limits
        caps_dict = self.brain.profile.capabilities

        # 2. 中层：生理与情感核心 (边缘系统中枢)
        self.thalamus = ThalamusContextBuilder()
        self.hypothalamus = HypothalamusEnergy(limits_dict)
        self.amygdala = AmygdalaEmotionalState()
        self.emotion_decay = EmotionDecayCalculator()
        self.hippocampus = EpisodeMemoryManager()

        # 3. 底层：感知与动力外设 (爬行动物脑)
        self.speech_actuator = SpeechActuator()
        self.motion_actuator = MotionActuator()
        self.mutter_actuator = MutterActuator()
        
        self.signal_filter = SensoryDamSignalFilter()
        self.safety_reflex = PhysicalLimitsReflex(caps_dict)

    def tick(self, dt: float):
        """
        由世界引擎（或主周期）定时驱动的精灵生理 Tick
        :param dt: 过去的时间步长 (秒)
        """
        # (A) 下丘脑生理钟时钟钟摆 Tick 衰减
        self.hypothalamus.update_clock(dt)
        
        # (B) 杏仁核情绪荷尔蒙自然半衰期扩散衰减
        self.emotion_decay.decay_emotions(self.amygdala, dt)
        
        # (C) 睡觉时的碎碎念和夜间离线记忆固化，在 scheduler 中通过 get_fatigue 配合调用

    def perceive_and_respond(self, raw_sensor_data: Dict[str, Any], runtime_agent: Any) -> Dict[str, Any]:
        """
        外界事件/消息输入的感知与反思响应完整闭环流程 (The Somatic Loop)
        1. 信号过滤器(感知大坝)噪点拦截
        2. 丘脑拉取多方状态拼装 Context
        3. 大脑皮层分析并决策
        4. 物理反射弧拦截违规超载动作
        5. 输出肢体、语言执行，触发碎碎念
        6. 海马体情景经历记忆录入
        :param raw_sensor_data: 底层瞬间采样到的传感器信号
        :param runtime_agent: 大模型底座 RuntimeAgent 实例
        :return: 包含交互执行反馈的响应字典
        """
        # 如果当前精灵在睡眠休眠，拦截任何输入，强制打哈欠睡觉 (熔断机制)
        if self.hypothalamus.is_sleeping:
            sleep_mutter = self.mutter_actuator.mutter("sleeping")
            return {
                "success": False,
                "reason": "Elfie is sleeping",
                "speech": "",
                "action": "blink_eyes",
                "mutter": sleep_mutter
            }

        # 1. 底层感知大坝噪点过滤
        has_valuable_change = self.signal_filter.filter_noise(raw_sensor_data)
        if not has_valuable_change:
            return {"success": True, "filtered": True, "reason": "No sensory changes, skipped."}

        # 2. 中层丘脑拼装 Context
        context = self.thalamus.assemble(
            raw_sensors=raw_sensor_data,
            energy_system=self.hypothalamus,
            emotion_engine=self.amygdala,
            memory_system=self.hippocampus
        )

        # 3. 顶层大脑皮层认知决策
        decision = self.brain.think_and_decide(context, runtime_agent)
        
        action = decision.get("action", "")
        speech_text = decision.get("speech_text", "")
        mutter_msg = decision.get("mutter", "")

        # 4. 底层躯体安全反射校验 (物理约束拦截防幻觉)
        reflex_result = self.safety_reflex.intercept_and_validate(action)
        if not reflex_result["allowed"]:
            # 反射拦截，动作强制变为点头，并在语言中提示痛觉，触发负面情绪
            logger.warning("物理反射拦截警报生效！重新注入报错回馈信号。")
            action = "nod_head"
            speech_text = f"哎呦！我的小毛爪撞到坚硬的物理定律墙壁了哒！疼... {reflex_result['feedback_error']}"
            self.amygdala.update_emotion("anxiety", 15.0) # 焦虑度上升
            self.amygdala.update_emotion("happiness", -10.0) # 快乐度下降
            mutter_msg = "(物理能力拦截警告，艾菲眼眶湿润了哒...)"

        # 5. 执行具体物理驱动
        self.speech_actuator.speak(speech_text)
        self.motion_actuator.execute_action(action)
        
        # 扣减下丘脑动作能耗
        is_remote = runtime_agent.config.remote_api_key != ""
        self.hypothalamus.consume_energy_by_action(is_remote)
        
        # 成功响应增加主人亲近感，无聊度降低，快乐度增加
        self.amygdala.update_emotion("boredom", -15.0)
        self.amygdala.update_emotion("happiness", 5.0)

        # 6. 将今日经历存入海马体情景记录
        if raw_sensor_data.get("has_new_message"):
            user_msg = raw_sensor_data.get("user_message", "")
            self.hippocampus.record_episode(
                event_description=f"主人对我说: '{user_msg}'。我回答了: '{speech_text}'，并做了动作 '{action}'。",
                emotion_tag=self.amygdala.get_dominant_mood()
            )

        return {
            "success": True,
            "speech": speech_text,
            "action": action,
            "mutter": mutter_msg
        }
