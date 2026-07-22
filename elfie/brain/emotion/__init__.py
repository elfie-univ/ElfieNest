from elfie.brain.emotion.decay_calculator import EmotionDecayCalculator
from elfie.brain.emotion.emotion_input import EmotionInput
from elfie.brain.emotion.emotion_system import (
    EmotionSystem,
    EmotionTimeRegressionError,
)
from elfie.brain.emotion.emotion_types import (
    EMOTION_ALIASES,
    EMOTION_CONFIGS,
    EmotionType,
    resolve_emotion_name,
)
from elfie.brain.emotion.emotional_state import AmygdalaEmotionalState
from elfie.brain.emotion.interactions import EmotionInteractionSystem
from elfie.brain.emotion.personality import (
    PersonalityModifier,
    calculate_personality_modifier,
)
from elfie.brain.emotion.stimulus import EmotionStimulusEvent, StimulusSource

__all__ = [
    "AmygdalaEmotionalState",
    "EmotionDecayCalculator",
    "EmotionSystem",
    "EmotionTimeRegressionError",
    "EmotionStimulusEvent",
    "EmotionInput",
    "EmotionType",
    "EMOTION_CONFIGS",
    "EMOTION_ALIASES",
    "resolve_emotion_name",
    "PersonalityModifier",
    "calculate_personality_modifier",
    "EmotionInteractionSystem",
    "StimulusSource",
]
