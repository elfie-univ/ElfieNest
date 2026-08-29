"""Pure perception appraisal and coordinator clock control data."""

from typing import Optional

from pydantic import Field
from typing_extensions import Annotated

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


class EmotionAppraiser:
    """Map typed perceptions to inert stimuli without mutation authority."""

    def __init__(self, text_detector: Optional[TextEmotionDetector] = None) -> None:
        self._text_detector = text_detector or TextEmotionDetector()

    def appraise(self, event: PerceptionEvent) -> Optional[EmotionStimulusEvent]:
        """Return a stimulus for supported perceptions, otherwise no appraisal."""
        payload = event.payload
        if isinstance(payload, PhysicalPayload):
            if payload.modality is not PhysicalModality.TOUCH:
                return None
            return EmotionStimulusEvent(
                event_id=event.meta.event_id,
                emotion=EmotionType.FEAR,
                intensity=event.salience,
                source=StimulusSource.PHYSICAL,
            )
        if isinstance(payload, SocialPayload):
            assessment = self._text_detector.assess(payload.content)
            if assessment.emotion is not None:
                return EmotionStimulusEvent(
                    event_id=event.meta.event_id,
                    emotion=assessment.emotion,
                    intensity=min(1.0, event.salience * assessment.confidence),
                    source=StimulusSource.SOCIAL,
                )
            return EmotionStimulusEvent(
                event_id=event.meta.event_id,
                emotion=EmotionType.ATTACHMENT,
                intensity=event.salience,
                source=StimulusSource.SOCIAL,
            )
        if isinstance(payload, ExecutionPayload):
            return self._appraise_execution(event, payload)
        if isinstance(payload, InternalPayload):
            return None
        return None

    @staticmethod
    def _appraise_execution(
        event: PerceptionEvent,
        payload: ExecutionPayload,
    ) -> Optional[EmotionStimulusEvent]:
        if payload.status is ExecutionStatus.COMPLETED:
            emotion = EmotionType.HAPPINESS
        elif payload.status in {
            ExecutionStatus.REJECTED,
            ExecutionStatus.FAILED,
            ExecutionStatus.INTERRUPTED,
            ExecutionStatus.TIMED_OUT,
        }:
            emotion = EmotionType.ANGER
        else:
            return None
        return EmotionStimulusEvent(
            event_id=event.meta.event_id,
            emotion=emotion,
            intensity=event.salience,
            source=StimulusSource.EXECUTION,
        )


__all__ = ("BrainClockPulse", "EmotionAppraiser")
