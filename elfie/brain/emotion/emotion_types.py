"""Fixed short-term affect channels owned by Brain Emotion."""

from __future__ import annotations

from enum import Enum, unique


@unique
class EmotionType(str, Enum):
    """The six short-term affect reservoirs.

    Relationship attachment and motivational boredom are deliberately not
    Emotion channels. They belong to their owning systems and may only appear
    as observed cues at this boundary.
    """

    HAPPINESS = "happiness"
    SADNESS = "sadness"
    ANGER = "anger"
    FEAR = "fear"
    SURPRISE = "surprise"
    DISGUST = "disgust"


EMOTION_NAMES = tuple(item.value for item in EmotionType)

# Direct domain construction still needs a deterministic safe default. The
# packaged source of truth is config/brain/emotion-dynamics.yaml; Bootstrap
# passes that document to EmotionSystem in production.
EMOTION_CONFIGS = {
    "happiness": {
        "baseline": 0.04,
        "positive_gain": 1.0,
        "negative_gain": 1.0,
        "half_life_seconds": 760.0,
        "activation_threshold": 0.18,
    },
    "sadness": {
        "baseline": 0.02,
        "positive_gain": 1.0,
        "negative_gain": 1.0,
        "half_life_seconds": 640.0,
        "activation_threshold": 0.18,
    },
    "anger": {
        "baseline": 0.01,
        "positive_gain": 1.15,
        "negative_gain": 1.0,
        "half_life_seconds": 740.0,
        "activation_threshold": 0.20,
    },
    "fear": {
        "baseline": 0.02,
        "positive_gain": 1.25,
        "negative_gain": 1.0,
        "half_life_seconds": 500.0,
        "activation_threshold": 0.20,
    },
    "surprise": {
        "baseline": 0.0,
        "positive_gain": 1.50,
        "negative_gain": 1.0,
        "half_life_seconds": 27.0,
        "activation_threshold": 0.16,
    },
    "disgust": {
        "baseline": 0.01,
        "positive_gain": 1.0,
        "negative_gain": 1.0,
        "half_life_seconds": 180.0,
        "activation_threshold": 0.20,
    },
}
__all__ = (
    "EMOTION_CONFIGS",
    "EMOTION_NAMES",
    "EmotionType",
)
