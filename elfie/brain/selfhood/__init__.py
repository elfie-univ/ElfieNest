"""Selfhood: the slowly changing self-model anchored by immutable Profile facts."""

from .contracts import (
    BigFiveTraits,
    ProfileAnchorSnapshot,
    SelfhoodDerivation,
    SelfhoodSnapshot,
    SelfhoodSpeechStyle,
)
from .defaults import load_packaged_selfhood_seed, load_selfhood_seed_for_profile
from .personality_derivation import (
    BIG_FIVE_TRAITS,
    PERSONALITY_KEYWORDS,
    PERSONALITY_PRESETS,
    PersonalityDerivation,
    PersonalityDerivationError,
    derive_personality,
)
from .system import SelfhoodSystem

__all__ = (
    "BigFiveTraits",
    "BIG_FIVE_TRAITS",
    "PERSONALITY_KEYWORDS",
    "PERSONALITY_PRESETS",
    "ProfileAnchorSnapshot",
    "SelfhoodDerivation",
    "SelfhoodSnapshot",
    "SelfhoodSpeechStyle",
    "SelfhoodSystem",
    "PersonalityDerivation",
    "PersonalityDerivationError",
    "derive_personality",
    "load_packaged_selfhood_seed",
    "load_selfhood_seed_for_profile",
)
