"""Fast event appraisal without confusing another actor with Elfie."""

from typing import Optional

from pydantic import Field
from typing_extensions import Annotated

from elfie.brain.emotion.contracts import (
    AffectDirection,
    ChannelEffect,
    ObservedOtherAffect,
)
from elfie.brain.emotion.detector.text_detector import TextEmotionDetector
from elfie.brain.emotion.emotion_types import EmotionType
from elfie.brain.emotion.stimulus import EmotionStimulusEvent, StimulusSource
from elfie.brain.workspace.contracts import (
    ExecutionPayload,
    ExecutionStatus,
    InternalPayload,
    PerceptionEvent,
    PhysicalModality,
    PhysicalPayload,
    SocialPayload,
)
from elfie.message_types import FrozenContractModel

_Timestamp = Annotated[float, Field(strict=True, ge=0.0)]


class BrainClockPulse(FrozenContractModel):
    """Coordinator mailbox control data; never a cognitive perception."""

    timestamp: _Timestamp


def _effect(
    channel: EmotionType,
    direction: AffectDirection,
    strength: int,
    *,
    confidence: float = 1.0,
) -> ChannelEffect:
    return ChannelEffect(
        channel=channel,
        direction=direction,
        strength=strength,
        confidence=max(0.0, min(1.0, confidence)),
    )


class EmotionAppraiser:
    """Map typed perceptions to provisional Elfie affect effects."""

    def __init__(self, text_detector: Optional[TextEmotionDetector] = None) -> None:
        self._text_detector = text_detector or TextEmotionDetector()

    def appraise(self, event: PerceptionEvent) -> Optional[EmotionStimulusEvent]:
        payload = event.payload
        if isinstance(payload, PhysicalPayload):
            return self._appraise_physical(event, payload)
        if isinstance(payload, SocialPayload):
            return self._appraise_social(event, payload)
        if isinstance(payload, ExecutionPayload):
            return self._appraise_execution(event, payload)
        if isinstance(payload, InternalPayload):
            return None
        return None

    @staticmethod
    def _appraise_physical(
        event: PerceptionEvent,
        payload: PhysicalPayload,
    ) -> Optional[EmotionStimulusEvent]:
        if payload.modality is not PhysicalModality.TOUCH:
            return None
        content = payload.content.lower()
        critical = "reflex emergency_stop" in content or event.salience >= 0.9
        effects = (
            _effect(EmotionType.FEAR, AffectDirection.INCREASE, 90 if critical else 55),
            _effect(
                EmotionType.SURPRISE,
                AffectDirection.INCREASE,
                75 if critical else 35,
            ),
            _effect(
                EmotionType.HAPPINESS,
                AffectDirection.DECREASE,
                35 if critical else 15,
            ),
        )
        return EmotionStimulusEvent(
            event_id=event.meta.event_id,
            effects=effects,
            source=StimulusSource.PHYSICAL,
            cause_key=(
                str(event.meta.causation_id)
                if event.meta.causation_id is not None
                else None
            ),
        )

    def _appraise_social(
        self,
        event: PerceptionEvent,
        payload: SocialPayload,
    ) -> Optional[EmotionStimulusEvent]:
        assessment = self._text_detector.assess(payload.content)
        observed = (
            ObservedOtherAffect(
                label=assessment.emotion.value,
                confidence=assessment.confidence,
                language=assessment.language,
                matched_terms=assessment.matched_terms,
            )
            if assessment.emotion is not None
            else None
        )
        effects = self._direct_social_effects(payload.content)
        if not effects and observed is None:
            return None
        return EmotionStimulusEvent(
            event_id=event.meta.event_id,
            effects=tuple(effects),
            source=StimulusSource.SOCIAL,
            observed_other_affect=observed,
            cause_key=f"{payload.channel_id}:{payload.conversation_id}",
        )

    @staticmethod
    def _direct_social_effects(content: str) -> tuple[ChannelEffect, ...]:
        text = content.casefold()
        hostile = any(
            marker in text
            for marker in (
                "you are an idiot",
                "i hate you",
                "leave me alone",
                "滚",
                "闭嘴",
                "你真笨",
                "讨厌你",
            )
        )
        caring = any(
            marker in text
            for marker in (
                "love you",
                "thank you",
                "good job",
                "你真棒",
                "谢谢你",
                "喜欢你",
            )
        )
        if hostile:
            return (
                _effect(EmotionType.ANGER, AffectDirection.INCREASE, 45),
                _effect(EmotionType.SADNESS, AffectDirection.INCREASE, 30),
                _effect(EmotionType.HAPPINESS, AffectDirection.DECREASE, 35),
            )
        if caring:
            return (
                _effect(EmotionType.HAPPINESS, AffectDirection.INCREASE, 35),
                _effect(EmotionType.SADNESS, AffectDirection.DECREASE, 20),
                _effect(EmotionType.FEAR, AffectDirection.DECREASE, 15),
            )
        # A detected owner's affect remains an observation only. It does not
        # become Elfie's sadness/anger/happiness without self-relevance.
        return ()

    @staticmethod
    def _appraise_execution(
        event: PerceptionEvent,
        payload: ExecutionPayload,
    ) -> Optional[EmotionStimulusEvent]:
        if str(payload.plan_id).startswith("reflex-"):
            return None
        if payload.executor not in {"internal", "activity"}:
            return None
        if payload.status is ExecutionStatus.COMPLETED:
            effects = (
                _effect(EmotionType.HAPPINESS, AffectDirection.INCREASE, 40),
                _effect(EmotionType.SADNESS, AffectDirection.DECREASE, 25),
                _effect(EmotionType.ANGER, AffectDirection.DECREASE, 20),
            )
        elif payload.status in {
            ExecutionStatus.REJECTED,
            ExecutionStatus.FAILED,
            ExecutionStatus.INTERRUPTED,
            ExecutionStatus.TIMED_OUT,
        }:
            effects = (
                _effect(EmotionType.SADNESS, AffectDirection.INCREASE, 40),
                _effect(EmotionType.ANGER, AffectDirection.INCREASE, 35),
                _effect(EmotionType.HAPPINESS, AffectDirection.DECREASE, 25),
            )
        else:
            return None
        return EmotionStimulusEvent(
            event_id=event.meta.event_id,
            effects=effects,
            source=StimulusSource.EXECUTION,
        )


__all__ = ("BrainClockPulse", "EmotionAppraiser")
