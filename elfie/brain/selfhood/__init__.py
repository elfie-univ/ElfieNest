"""Selfhood: one atomic two-layer state and deterministic model projection."""

from .contracts import (
    AdaptiveSelf,
    BigFiveTraits,
    IdentityCore,
    SelfhoodPromptProjection,
    SelfhoodSpeechStyle,
    SelfhoodState,
)
from .personality_derivation import (
    BIG_FIVE_TRAITS,
    PERSONALITY_KEYWORDS,
    PERSONALITY_PRESETS,
    PersonalityDerivation,
    PersonalityDerivationError,
    derive_personality,
)
from .system import SelfhoodGrowthDisabledError, SelfhoodSystem

__all__ = (
    "BigFiveTraits",
    "AdaptiveSelf",
    "IdentityCore",
    "BIG_FIVE_TRAITS",
    "PERSONALITY_KEYWORDS",
    "PERSONALITY_PRESETS",
    "SelfhoodPromptProjection",
    "SelfhoodState",
    "SelfhoodSpeechStyle",
    "SelfhoodSystem",
    "SelfhoodGrowthDisabledError",
    "PersonalityDerivation",
    "PersonalityDerivationError",
    "derive_personality",
)
