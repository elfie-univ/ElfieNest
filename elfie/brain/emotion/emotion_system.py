"""情绪系统 - Emotion System

新的情绪系统实现，整合饱和增长、分阶段衰减、频率追踪和事件去重。
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Dict, Final, Mapping, Optional, Tuple

from elfie.brain.emotion.accumulator.decay import decay
from elfie.brain.emotion.accumulator.frequency import FrequencyTracker
from elfie.brain.emotion.accumulator.saturation import calculate_accumulation_delta
from elfie.brain.emotion.contracts import EmotionSnapshot, EmotionValue
from elfie.brain.emotion.emotion_input import EmotionInput
from elfie.brain.emotion.emotion_types import (
    EMOTION_CONFIGS,
    EmotionType,
    resolve_emotion_name,
)
from elfie.brain.emotion.fusion.deduplicator import EventDeduplicator
from elfie.brain.emotion.interactions import EmotionInteractionSystem
from elfie.brain.emotion.personality import PersonalityModifier
from elfie.brain.emotion.stimulus import EmotionStimulusEvent, StimulusSource
from elfie.brain.state_lifecycle import StateRestoreError
from elfie.message_types import EventId

if TYPE_CHECKING:
    from elfie.brain.emotion.expression_mapper import EmotionExpression

logger = logging.getLogger("elfie.brain.emotion.emotion_system")

_LEGACY_STIMULUS_SOURCES: Final[Mapping[StimulusSource, str]] = {
    StimulusSource.PHYSICAL: "physical",
    StimulusSource.SOCIAL: "text",
    StimulusSource.EXECUTION: "brain",
    StimulusSource.MODEL: "brain",
}


class EmotionTimeRegressionError(Exception):
    """Raised when emotion state receives an older simulation timestamp."""

    def __init__(self, previous_timestamp: float, requested_timestamp: float) -> None:
        self.previous_timestamp = previous_timestamp
        self.requested_timestamp = requested_timestamp
        super().__init__(previous_timestamp, requested_timestamp)

    def __str__(self) -> str:
        return (
            "emotion simulation time cannot move backwards: "
            f"{self.previous_timestamp} -> {self.requested_timestamp}"
        )


@dataclass(frozen=True)
class EmotionCheckpoint:
    """Persistence-neutral checkpoint for the mutable affect owner."""

    revision: int
    last_updated_at: float
    emotions: Tuple[Tuple[str, float], ...]
    frequency_expire_times: Tuple[Tuple[str, Tuple[float, ...]], ...]
    processed_events: Tuple[Tuple[str, float], ...]
    source_event_ids: Tuple[EventId, ...]


class EmotionSystem:
    """情绪系统 - 整合所有情绪处理组件"""

    def __init__(
        self,
        personality: Optional[Dict[str, float]] = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        expression_config: Mapping[str, Any] | None = None,
    ):
        """初始化情绪系统

        Args:
            personality: 可选的Big Five性格特征字典，用于调节情绪反应
        """
        self._clock = clock
        from elfie.brain.emotion.expression_mapper import ExpressionMapper

        self._expression_mapper = ExpressionMapper(expression_config)
        self.last_updated_at = float(clock())
        self.revision = 0
        self._source_event_ids: deque[EventId] = deque(maxlen=32)

        # 初始化8种情绪为baseline值
        self.emotions: Dict[str, float] = {
            name: config["baseline"] for name, config in EMOTION_CONFIGS.items()
        }

        # 为每种情绪创建频率追踪器
        self.frequency_trackers: Dict[str, FrequencyTracker] = {
            name: FrequencyTracker(clock=self._simulation_time)
            for name in EMOTION_CONFIGS
        }

        # 全局事件去重器
        self.deduplicator = EventDeduplicator(clock=self._simulation_time)

        # 性格调节器（可选）
        self.personality_modifier: Optional[PersonalityModifier] = None
        if personality is not None:
            self.personality_modifier = PersonalityModifier(personality)

        # 情绪交互系统
        self.interaction_system = EmotionInteractionSystem()

        logger.info("情绪系统初始化完成，8种情绪已加载")

    def _simulation_time(self) -> float:
        """Return the single simulation time used by all accumulators."""
        return self.last_updated_at

    def process_input(self, emotion_input: EmotionInput) -> None:
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
        self._source_event_ids.append(EventId(emotion_input.event_id))

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
        self.revision += 1

        logger.info(
            f"🎭 [情绪更新] {emotion}: {old_value:.1f} -> {self.emotions[emotion]:.1f} "
            f"(delta={actual_delta:.2f}, intensity={emotion_input.intensity:.2f})"
        )

    def apply_stimulus(self, stimulus: EmotionStimulusEvent) -> None:
        """Apply one coordinator-appraised, deduplicable stimulus."""
        self.process_input(
            EmotionInput(
                emotion=stimulus.emotion.value,
                intensity=stimulus.intensity,
                source=_LEGACY_STIMULUS_SOURCES[stimulus.source],
                event_id=str(stimulus.event_id),
                timestamp=self.last_updated_at,
            )
        )

    def reconcile_turn(
        self,
        checkpoint: EmotionCheckpoint,
        *,
        turn_id: str,
        emotion: EmotionType,
        intensity: float,
        confidence: float,
        timestamp: float,
    ) -> None:
        """Replace a turn's provisional appraisal with model feedback.

        The coordinator is the sole writer and calls this only after the
        model returns.  We restore the pre-stimulus checkpoint, replay any
        elapsed decay, then apply exactly one model-owned stimulus.  This
        prevents the entry appraisal and the correction from accumulating
        twice while preserving clock continuity.
        """
        if timestamp < checkpoint.last_updated_at:
            raise EmotionTimeRegressionError(checkpoint.last_updated_at, timestamp)
        self._restore_checkpoint_unchecked(checkpoint)
        self.advance_to(timestamp)
        self.apply_stimulus(
            EmotionStimulusEvent(
                event_id=EventId(f"emotion-feedback:{turn_id}"),
                emotion=emotion,
                intensity=max(0.0, min(1.0, intensity * confidence)),
                source=StimulusSource.MODEL,
            )
        )

    def update_emotion(self, name: str, delta: float) -> None:
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
        self.revision += 1

        logger.info(
            f"🎭 [情绪微调] {emotion}: {old_val:.1f} -> {self.emotions[emotion]:.1f}"
        )

    def tick(self, dt: float) -> None:
        """时间滴答 - 衰减所有情绪

        Args:
            dt: 时间增量（秒）
        """
        self.advance_to(self.last_updated_at + dt)

    def advance_to(self, timestamp: float) -> None:
        """Advance emotion decay to one absolute simulation timestamp."""
        if timestamp < self.last_updated_at:
            raise EmotionTimeRegressionError(self.last_updated_at, timestamp)
        if timestamp == self.last_updated_at:
            return
        self._decay_all(timestamp - self.last_updated_at)
        self.last_updated_at = timestamp
        self.revision += 1

    def _decay_all(self, dt: float) -> None:
        """Apply existing emotion decay and interaction formulas."""
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

    def snapshot(self, at: float) -> EmotionSnapshot:
        """Advance first, then seal normalized immutable emotion values."""
        self.advance_to(at)
        return EmotionSnapshot(
            revision=self.revision,
            captured_at=datetime.fromtimestamp(at, timezone.utc),
            values=tuple(
                EmotionValue(name=name, intensity=value / 100.0)
                for name, value in self.emotions.items()
            ),
            dominant=self.get_dominant_mood() if self.emotions else None,
            source_event_ids=tuple(self._source_event_ids),
        )

    def checkpoint(self) -> EmotionCheckpoint:
        """Seal all mutable affect state, including deduplication windows."""
        return EmotionCheckpoint(
            revision=self.revision,
            last_updated_at=self.last_updated_at,
            emotions=tuple(sorted(self.emotions.items())),
            frequency_expire_times=tuple(
                (
                    name,
                    tuple(tracker.expire_times),
                )
                for name, tracker in sorted(self.frequency_trackers.items())
            ),
            processed_events=tuple(sorted(self.deduplicator.processed_events.items())),
            source_event_ids=tuple(self._source_event_ids),
        )

    def validate_checkpoint(self, checkpoint: EmotionCheckpoint) -> None:
        """Reject an older or structurally incompatible affect checkpoint."""
        if checkpoint.revision < self.revision:
            raise StateRestoreError(
                "emotion checkpoint revision is older than current state"
            )
        if (
            checkpoint.revision == self.revision
            and checkpoint.last_updated_at < self.last_updated_at
        ):
            raise StateRestoreError(
                "emotion checkpoint simulation time is older than current state"
            )
        expected = set(EMOTION_CONFIGS)
        actual = {name for name, _value in checkpoint.emotions}
        if actual != expected:
            raise ValueError("emotion checkpoint contains an incompatible emotion set")
        for name, value in checkpoint.emotions:
            if not 0.0 <= value <= EMOTION_CONFIGS[name]["max_value"]:
                raise ValueError(f"emotion checkpoint value out of range: {name}")
        if {name for name, _values in checkpoint.frequency_expire_times} != expected:
            raise ValueError("emotion checkpoint contains incompatible frequency state")

    def restore(self, checkpoint: EmotionCheckpoint) -> None:
        """Restore a committed affect checkpoint without rewinding the owner."""
        self.validate_checkpoint(checkpoint)
        self._restore_checkpoint_unchecked(checkpoint)

    def _restore_checkpoint_unchecked(self, checkpoint: EmotionCheckpoint) -> None:
        """Restore exact state for a same-turn reconciliation transaction."""
        self.emotions = dict(checkpoint.emotions)
        self.last_updated_at = checkpoint.last_updated_at
        self.revision = checkpoint.revision
        for name, values in checkpoint.frequency_expire_times:
            self.frequency_trackers[name].expire_times.clear()
            self.frequency_trackers[name].expire_times.extend(values)
        self.deduplicator.processed_events = dict(checkpoint.processed_events)
        self._source_event_ids = deque(checkpoint.source_event_ids, maxlen=32)

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

    def get_expression(self) -> EmotionExpression:
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
        return self._expression_mapper.get_expression_for_emotions(self.emotions)
