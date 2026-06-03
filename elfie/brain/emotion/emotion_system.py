"""情绪系统 - Emotion System

新的情绪系统实现，整合饱和增长、分阶段衰减、频率追踪和事件去重。
"""

import logging
from typing import Dict, Optional

from elfie.brain.emotion.accumulator.decay import decay
from elfie.brain.emotion.accumulator.frequency import FrequencyTracker
from elfie.brain.emotion.accumulator.saturation import calculate_accumulation_delta
from elfie.brain.emotion.emotion_input import EmotionInput
from elfie.brain.emotion.emotion_types import EMOTION_CONFIGS, resolve_emotion_name
from elfie.brain.emotion.fusion.deduplicator import EventDeduplicator
from elfie.brain.emotion.interactions import EmotionInteractionSystem
from elfie.brain.emotion.personality import PersonalityModifier

logger = logging.getLogger("elfie.brain.emotion.emotion_system")


class EmotionSystem:
    """情绪系统 - 整合所有情绪处理组件"""

    def __init__(self, personality: Optional[Dict[str, float]] = None):
        """初始化情绪系统

        Args:
            personality: 可选的Big Five性格特征字典，用于调节情绪反应
        """
        # 初始化8种情绪为baseline值
        self.emotions: Dict[str, float] = {
            name: config["baseline"] for name, config in EMOTION_CONFIGS.items()
        }

        # 为每种情绪创建频率追踪器
        self.frequency_trackers: Dict[str, FrequencyTracker] = {
            name: FrequencyTracker() for name in EMOTION_CONFIGS
        }

        # 全局事件去重器
        self.deduplicator = EventDeduplicator()

        # 性格调节器（可选）
        if personality is not None:
            self.personality_modifier = PersonalityModifier(personality)
        else:
            self.personality_modifier = None

        # 情绪交互系统
        self.interaction_system = EmotionInteractionSystem()

        logger.info("情绪系统初始化完成，8种情绪已加载")

    def process_input(self, emotion_input: EmotionInput):
        """处理情绪输入（新API）

        Args:
            emotion_input: 情绪输入数据
        """
        # 解析情绪名称（处理别名）
        emotion = resolve_emotion_name(emotion_input.emotion)

        if emotion not in self.emotions:
            logger.warning(f"未知情绪类型: {emotion}")
            return

        # 验证输入
        if not emotion_input.validate():
            logger.warning(f"情绪输入验证失败: {emotion_input}")
            return

        # 去重检查
        if not self.deduplicator.is_new(emotion_input.event_id):
            logger.debug(f"重复事件，跳过: {emotion_input.event_id}")
            return
        self.deduplicator.mark_processed(emotion_input.event_id)

        # 记录频率
        self.frequency_trackers[emotion].record_input()

        # 计算增量（使用饱和增长公式）
        config = EMOTION_CONFIGS[emotion]
        slow_factor = self.frequency_trackers[emotion].get_slow_factor(config=config)

        # 获取基础累积速率
        base_accumulate_rate = config.get("accumulate_rate", 0.5)

        # 应用频率慢化
        frequency_adjusted_rate = base_accumulate_rate / slow_factor

        # 应用性格调节
        if self.personality_modifier:
            personality_factor = self.personality_modifier.get_accumulate_modifier(
                emotion
            )
            effective_accumulate_rate = frequency_adjusted_rate * personality_factor
        else:
            effective_accumulate_rate = frequency_adjusted_rate

        interaction_modifier = self.interaction_system.get_accumulate_modifier(
            emotion, self.emotions
        )
        effective_accumulate_rate *= interaction_modifier

        adjusted_config = {**config, "accumulate_rate": effective_accumulate_rate}

        actual_delta = calculate_accumulation_delta(
            current_value=self.emotions[emotion],
            base_delta=config["base_delta"],
            intensity=emotion_input.intensity,
            config=adjusted_config,
        )

        # 更新情绪值
        old_value = self.emotions[emotion]
        self.emotions[emotion] += actual_delta
        self.emotions[emotion] = min(self.emotions[emotion], config["max_value"])

        logger.info(
            f"🎭 [情绪更新] {emotion}: {old_value:.1f} -> {self.emotions[emotion]:.1f} "
            f"(delta={actual_delta:.2f}, intensity={emotion_input.intensity:.2f})"
        )

    def update_emotion(self, name: str, delta: float):
        """更新情绪值（向后兼容的旧API）

        Args:
            name: 情绪名称
            delta: 变化量
        """
        # 解析情绪名称（处理别名，如anxiety->fear）
        emotion = resolve_emotion_name(name)

        if emotion not in self.emotions:
            logger.warning(f"未知情绪类型: '{name}' -> '{emotion}'")
            return

        old_val = self.emotions[emotion]
        self.emotions[emotion] += delta
        # 边界裁切 (0 - 100)
        self.emotions[emotion] = max(0.0, min(100.0, self.emotions[emotion]))

        logger.info(
            f"🎭 [情绪微调] {emotion}: {old_val:.1f} -> {self.emotions[emotion]:.1f}"
        )

    def tick(self, dt: float):
        """时间滴答 - 衰减所有情绪

        Args:
            dt: 时间增量（秒）
        """
        for emotion, value in self.emotions.items():
            config = EMOTION_CONFIGS[emotion]
            old_value = value

            # 获取基础半衰期
            base_half_life = config.get("half_life", 10.0)

            # 应用性格调节到半衰期
            if self.personality_modifier:
                decay_modifier = self.personality_modifier.get_decay_modifier(emotion)
                effective_half_life = base_half_life / decay_modifier
            else:
                effective_half_life = base_half_life

            self.emotions[emotion] = decay(
                current_value=value,
                dt=dt,
                config=config,
                baseline=config["baseline"],
                half_life=effective_half_life,
            )

            # 只在有显著变化时记录日志
            if abs(self.emotions[emotion] - old_value) > 0.1:
                logger.debug(
                    f"⏱️ [情绪衰减] {emotion}: {old_value:.1f} -> {self.emotions[emotion]:.1f}"
                )

        self.interaction_system.apply_transfer_interactions(self.emotions)

    def get_dominant_mood(self) -> str:
        """获取主导情绪

        Returns:
            当前值最高的情绪名称
        """
        if not self.emotions:
            return "calm"
        return max(self.emotions.items(), key=lambda x: x[1])[0]

    def get_emotion_summary(self) -> str:
        """获取情绪摘要

        Returns:
            格式化的情绪状态字符串
        """
        items = [f"{name}:{value:.1f}" for name, value in self.emotions.items()]
        return ", ".join(items)

    def get_current_emotion_summary(self) -> str:
        """获取当前情绪摘要（向后兼容的旧API）

        Returns:
            格式化的情绪状态字符串
        """
        return self.get_emotion_summary()

    def get_emotion_value(self, name: str) -> float:
        """获取指定情绪的当前值

        Args:
            name: 情绪名称

        Returns:
            情绪值（0-100）
        """
        emotion = resolve_emotion_name(name)
        return self.emotions.get(emotion, 0.0)

    def get_expression(self) -> dict:
        """获取当前情绪的表达参数

        Returns:
            dict: {
                "expression": str,
                "actions": list,
                "voice_modifier": str,
                "intensity": float,
                "emotion": str
            }
        """
        from elfie.brain.emotion.expression_mapper import ExpressionMapper

        mapper = ExpressionMapper()
        return mapper.get_expression_for_emotions(self.emotions)
