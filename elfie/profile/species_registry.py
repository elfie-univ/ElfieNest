"""One read-only registry for species capabilities exposed to product clients.

The narrative card owns the stable identity and presentation metadata while the
appearance profile owns the body-generation constraints.  This registry joins
those two domain facts once, validates that they agree, and is the only public
lookup used by Adoption and settings.
"""

from __future__ import annotations

from dataclasses import dataclass

from .canon import SpeciesCanon, list_species_canons
from .species import SpeciesAppearanceProfile, get_species_profile


@dataclass(frozen=True)
class SpeciesDefinition:
    """Complete product-facing definition of one supported species."""

    species_id: str
    canon_id: str
    display_name: str
    display_name_zh: str
    earth_shape_label: str
    scene_id: str
    sort_order: int
    enabled: bool
    appearance_profile_version: int
    appearance: SpeciesAppearanceProfile
    canon: SpeciesCanon


def _build_registry() -> tuple[SpeciesDefinition, ...]:
    definitions: list[SpeciesDefinition] = []
    for canon in list_species_canons():
        appearance = get_species_profile(canon.technical_species_id)
        if appearance.species_id != canon.technical_species_id:
            raise ValueError(
                "物种注册表中的技术 ID 与外观 profile 不一致: "
                f"{canon.technical_species_id!r} != {appearance.species_id!r}"
            )
        definitions.append(
            SpeciesDefinition(
                species_id=canon.technical_species_id,
                canon_id=canon.canon_id,
                display_name=canon.display_name,
                display_name_zh=canon.display_name_zh,
                earth_shape_label=canon.earth_shape_label,
                scene_id=appearance.scene_id,
                sort_order=canon.sort_order,
                enabled=canon.visual_runtime_supported,
                appearance_profile_version=appearance.profile_version,
                appearance=appearance,
                canon=canon,
            )
        )
    return tuple(definitions)


SPECIES_REGISTRY: tuple[SpeciesDefinition, ...] = _build_registry()
SUPPORTED_SPECIES: tuple[str, ...] = tuple(
    definition.species_id for definition in SPECIES_REGISTRY if definition.enabled
)


def list_species_definitions(
    *, include_disabled: bool = False
) -> tuple[SpeciesDefinition, ...]:
    """Return registered species in the stable product order."""
    if include_disabled:
        return SPECIES_REGISTRY
    return tuple(definition for definition in SPECIES_REGISTRY if definition.enabled)


def get_species_definition(species_id: str) -> SpeciesDefinition:
    """Return one enabled product species or raise a domain validation error."""
    for definition in SPECIES_REGISTRY:
        if definition.species_id == species_id and definition.enabled:
            return definition
    raise ValueError(
        f"不支持的 species_id={species_id!r}，可选: {', '.join(SUPPORTED_SPECIES)}"
    )


def validate_species_registry() -> None:
    """Fail fast when a species definition would be ambiguous or incomplete."""
    definitions = list(SPECIES_REGISTRY)
    ids = [definition.species_id for definition in definitions]
    canon_ids = [definition.canon_id for definition in definitions]
    sort_orders = [definition.sort_order for definition in definitions]
    if len(set(ids)) != len(ids):
        raise ValueError("物种注册表包含重复的 species_id")
    if len(set(canon_ids)) != len(canon_ids):
        raise ValueError("物种注册表包含重复的 canon_id")
    if len(set(sort_orders)) != len(sort_orders):
        raise ValueError("物种注册表包含重复的 sort_order")
    for definition in definitions:
        if (
            not definition.display_name.strip()
            or not definition.display_name_zh.strip()
        ):
            raise ValueError(f"物种 {definition.species_id!r} 缺少显示名称")
        if not definition.scene_id.strip():
            raise ValueError(f"物种 {definition.species_id!r} 缺少 Godot scene_id")
        if len(definition.canon.candidate_names) < 5:
            raise ValueError(f"物种 {definition.species_id!r} 至少需要 5 组候选名字")


validate_species_registry()


__all__ = (
    "SPECIES_REGISTRY",
    "SUPPORTED_SPECIES",
    "SpeciesDefinition",
    "get_species_definition",
    "list_species_definitions",
    "validate_species_registry",
)
