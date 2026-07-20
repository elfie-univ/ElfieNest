"""精灵稳定档案、物种外貌配置和解析接口。"""

from .generator import AppearanceGenerator, create_visual_profile
from .models import (
    SUPPORTED_MORPHOLOGIES,
    AppearanceGenome,
    ElfieIdentity,
    ElfieProfile,
    EmbodimentProfile,
    ProfileProvenance,
)
from .repository import ElfieProfileRepository
from .resolver import AppearanceResolver, ResolvedAppearance
from .species import SUPPORTED_SPECIES, SpeciesAppearanceProfile, get_species_profile

__all__ = [
    "AppearanceGenerator",
    "AppearanceGenome",
    "AppearanceResolver",
    "EmbodimentProfile",
    "ElfieIdentity",
    "ElfieProfile",
    "ElfieProfileRepository",
    "ProfileProvenance",
    "ResolvedAppearance",
    "SUPPORTED_MORPHOLOGIES",
    "SUPPORTED_SPECIES",
    "SpeciesAppearanceProfile",
    "create_visual_profile",
    "get_species_profile",
]
