"""精灵稳定档案、物种外貌配置和解析接口。"""

from .defaults import load_packaged_profile_defaults
from .generator import AppearanceGenerator, create_visual_profile
from .models import (
    SUPPORTED_MORPHOLOGIES,
    AppearanceGenome,
    ElfieIdentity,
    ElfieProfile,
    EmbodimentProfile,
    ProfileProvenance,
)
from .personality_derivation import (
    PERSONALITY_KEYWORDS,
    PERSONALITY_PRESETS,
    OverrideValue,
    PersonalityDerivation,
    PersonalityDerivationError,
    derive_personality,
)
from .port import ProfileStorePort
from .resolver import AppearanceResolver, ResolvedAppearance
from .species import SUPPORTED_SPECIES, SpeciesAppearanceProfile, get_species_profile

__all__ = [
    "AppearanceGenerator",
    "AppearanceGenome",
    "AppearanceResolver",
    "EmbodimentProfile",
    "ElfieIdentity",
    "ElfieProfile",
    "ProfileStorePort",
    "ProfileProvenance",
    "PERSONALITY_KEYWORDS",
    "PERSONALITY_PRESETS",
    "OverrideValue",
    "PersonalityDerivation",
    "PersonalityDerivationError",
    "ResolvedAppearance",
    "SUPPORTED_MORPHOLOGIES",
    "SUPPORTED_SPECIES",
    "SpeciesAppearanceProfile",
    "create_visual_profile",
    "derive_personality",
    "get_species_profile",
    "load_packaged_profile_defaults",
]
