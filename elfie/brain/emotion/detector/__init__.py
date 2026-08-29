"""First-version text-only emotion detector boundary."""

from typing import Any, Dict

from elfie.brain.emotion.detector.text_detector import (
    TextEmotionAssessment,
    TextEmotionDetector,
)
from elfie.brain.emotion.emotion_input import EmotionInput


class EmotionDetectionError(ValueError):
    """Base error for the explicit first-version detector boundary."""


class UnsupportedEmotionModalityError(EmotionDetectionError):
    """Raised when a caller asks the first version to inspect media/audio."""


class NoEmotionDetectedError(EmotionDetectionError):
    """Raised when supported text contains no actionable affect signal."""


class EmotionDetector:
    """Expose only the model-free text detector supported in version one."""

    def __init__(self):
        self._text_detector = None

    def _get_text_detector(self):
        if self._text_detector is None:
            self._text_detector = TextEmotionDetector()
        return self._text_detector

    def detect(self, input_data: Dict[str, Any]) -> EmotionInput:
        """Detect one actionable text emotion.

        Args:
            input_data: ``type=text`` with content and an event identity.

        Returns:
            A validated legacy ``EmotionInput`` for the supported text cue.

        Raises:
            UnsupportedEmotionModalityError: The input is not text.
            NoEmotionDetectedError: Text is neutral or ambiguous.
        """
        input_type = input_data.get("type", "text")
        event_id = input_data.get("event_id", "unknown")

        if input_type != "text":
            raise UnsupportedEmotionModalityError(
                f"emotion modality is not supported in v1: {input_type}"
            )
        content = input_data.get("content", "")
        assessment = self._get_text_detector().assess(content)
        if assessment.emotion is None:
            raise NoEmotionDetectedError("no actionable emotion detected in text")
        return EmotionInput(
            emotion=assessment.emotion.value,
            intensity=assessment.confidence,
            source="text",
            event_id=event_id,
        )


__all__ = [
    "EmotionDetector",
    "TextEmotionDetector",
    "TextEmotionAssessment",
    "EmotionDetectionError",
    "UnsupportedEmotionModalityError",
    "NoEmotionDetectedError",
]
