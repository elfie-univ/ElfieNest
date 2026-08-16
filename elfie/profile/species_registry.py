"""The injected, typed species catalog used by Profile and Adoption."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Literal, Mapping, overload

from .canon import SpeciesCanon
from .species import SpeciesAppearanceProfile

SpeciesStatus = Literal["draft", "published", "retired"]
RESOLVABLE_STATUSES: tuple[SpeciesStatus, ...] = ("published", "retired")


@dataclass(frozen=True)
class SpeciesPresentationImages:
    """Logical asset names owned by the bundled species package."""

    headshot: str
    full_body: str


@dataclass(frozen=True)
class SpeciesGenesisProfile:
    """Per-species Genesis inputs; algorithms remain code-owned."""

    config_version: str
    stage_ranges: Mapping[str, tuple[int, int]]
    personality_prior: tuple[float, ...]
    appearance_preferences: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class SpeciesDefinition:
    """Complete typed product definition for one catalog member."""

    species_id: str
    canon_id: str
    display_name: str
    display_name_zh: str
    earth_shape_label: str
    config_package_id: str
    godot_package_id: str
    sort_order: int
    status: SpeciesStatus
    definition_version: str
    appearance_profile_version: int
    appearance: SpeciesAppearanceProfile
    canon: SpeciesCanon
    presentation_images: SpeciesPresentationImages | None
    genesis: SpeciesGenesisProfile | None

    @property
    def enabled(self) -> bool:
        """Compatibility name for callers that mean adoptable."""

        return (
            self.status == "published"
            and self.genesis is not None
            and self.presentation_images is not None
        )

    @property
    def scene_id(self) -> str:
        """Opaque v1 API compatibility field; frontend must not use it."""

        return self.godot_package_id

    @property
    def resolvable(self) -> bool:
        return self.status in RESOLVABLE_STATUSES

    @property
    def adoptable(self) -> bool:
        return self.resolvable and self.enabled


@dataclass(frozen=True)
class SpeciesCatalog:
    """One immutable product catalog loaded from the bundled config root."""

    catalog_version: str
    appearance_protocol_version: str
    definitions: tuple[SpeciesDefinition, ...]
    digest: str = ""

    def definition(
        self,
        species_id: str,
        *,
        adoptable_only: bool = False,
    ) -> SpeciesDefinition:
        for definition in self.definitions:
            if definition.species_id != species_id:
                continue
            if not definition.resolvable:
                break
            if adoptable_only and not definition.adoptable:
                break
            return definition
        raise ValueError(f"不支持的 species_id={species_id!r}")

    def list_definitions(
        self,
        *,
        include_disabled: bool = False,
    ) -> tuple[SpeciesDefinition, ...]:
        if include_disabled:
            return self.definitions
        return tuple(item for item in self.definitions if item.adoptable)

    @property
    def supported_species(self) -> tuple[str, ...]:
        return tuple(item.species_id for item in self.list_definitions())


_catalog: SpeciesCatalog | None = None


def configure_species_catalog(catalog: SpeciesCatalog) -> None:
    """Install the process catalog at the composition boundary."""

    global _catalog
    _catalog = catalog


def current_species_catalog() -> SpeciesCatalog:
    if _catalog is None:
        raise RuntimeError("SpeciesCatalog 尚未由 Bootstrap 注入")
    return _catalog


class _ConfiguredDefinitions(Sequence[SpeciesDefinition]):
    def __iter__(self) -> Iterator[SpeciesDefinition]:
        return iter(current_species_catalog().definitions)

    def __len__(self) -> int:
        return len(current_species_catalog().definitions)

    @overload
    def __getitem__(self, index: int) -> SpeciesDefinition: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[SpeciesDefinition]: ...

    def __getitem__(
        self, index: int | slice
    ) -> SpeciesDefinition | Sequence[SpeciesDefinition]:
        return current_species_catalog().definitions[index]


class _ConfiguredSpeciesIds(Sequence[str]):
    def __iter__(self) -> Iterator[str]:
        return iter(current_species_catalog().supported_species)

    def __len__(self) -> int:
        return len(current_species_catalog().supported_species)

    @overload
    def __getitem__(self, index: int) -> str: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[str]: ...

    def __getitem__(self, index: int | slice) -> str | Sequence[str]:
        return current_species_catalog().supported_species[index]

    def __contains__(self, item: object) -> bool:
        return item in current_species_catalog().supported_species

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Sequence):
            return tuple(self) == tuple(other)
        return NotImplemented

    def __repr__(self) -> str:
        return repr(tuple(self))


SPECIES_REGISTRY: Sequence[SpeciesDefinition] = _ConfiguredDefinitions()
SUPPORTED_SPECIES: Sequence[str] = _ConfiguredSpeciesIds()


def list_species_definitions(
    *,
    include_disabled: bool = False,
) -> tuple[SpeciesDefinition, ...]:
    return current_species_catalog().list_definitions(include_disabled=include_disabled)


def get_species_definition(
    species_id: str,
    *,
    adoptable_only: bool = False,
) -> SpeciesDefinition:
    return current_species_catalog().definition(
        species_id,
        adoptable_only=adoptable_only,
    )


def validate_species_registry() -> None:
    definitions = list(current_species_catalog().definitions)
    ids = [item.species_id for item in definitions]
    canon_ids = [item.canon_id for item in definitions]
    sort_orders = [item.sort_order for item in definitions]
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
        if definition.status not in ("draft", "published", "retired"):
            raise ValueError(f"物种 {definition.species_id!r} 的 status 无效")
        if not definition.godot_package_id.strip():
            raise ValueError(f"物种 {definition.species_id!r} 缺少 Godot package ID")


__all__ = (
    "RESOLVABLE_STATUSES",
    "SPECIES_REGISTRY",
    "SUPPORTED_SPECIES",
    "SpeciesCatalog",
    "SpeciesDefinition",
    "SpeciesGenesisProfile",
    "SpeciesPresentationImages",
    "SpeciesStatus",
    "configure_species_catalog",
    "current_species_catalog",
    "get_species_definition",
    "list_species_definitions",
    "validate_species_registry",
)
