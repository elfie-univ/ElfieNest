"""精灵稳定档案、物种外貌配置和解析接口。"""

from .canon import (
    ELFARIA_CANON,
    SPECIES_CANON_VERSION,
    WORLD_CANON_VERSION,
    SpeciesCanon,
    WorldCanon,
    get_species_canon,
    get_species_canon_for_technical_id,
)
from .defaults import load_packaged_profile_defaults
from .generator import AppearanceGenerator, create_visual_profile
from .models import (
    SUPPORTED_MORPHOLOGIES,
    AppearanceGenome,
    ElfieIdentity,
    ElfieOrigin,
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
    "ELFARIA_CANON",
    "ElfieOrigin",
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
    "SPECIES_CANON_VERSION",
    "WORLD_CANON_VERSION",
    "SpeciesCanon",
    "SpeciesAppearanceProfile",
    "WorldCanon",
    "create_visual_profile",
    "derive_personality",
    "get_species_profile",
    "get_species_canon",
    "get_species_canon_for_technical_id",
    "load_packaged_profile_defaults",
]
