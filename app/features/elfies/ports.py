"""Read-only authoritative boundaries consumed by the Elfies Feature."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping, Protocol

from .models import CognitionStatus


class ElfiesPortError(RuntimeError):
    """An Elfies authority could not be read safely."""


@dataclass(frozen=True)
class ElfieDirectoryRecord:
    elfie_id: str
    name: str
    owner_user_id: int
    owner_account_id: str
    owner_display_name: str | None
    species_id: str
    gender: str | None
    birth_date: str | None
    adopted_at: str
    summary: str | None


@dataclass(frozen=True)
class ElfieAppearanceRecord:
    species_id: str
    profile_version: int
    height_scale: float
    build_scale: float
    height_label: str
    build_label: str
    bone_scales: Mapping[str, float]
    blend_shapes: Mapping[str, float]
    material_parameters: Mapping[str, str | float]
    species_traits: Mapping[str, float]


@dataclass(frozen=True)
class ElfieProfileRecord:
    status: Literal["ready", "empty", "unavailable"]
    openness: float | None = None
    conscientiousness: float | None = None
    extraversion: float | None = None
    agreeableness: float | None = None
    neuroticism: float | None = None
    appearance: ElfieAppearanceRecord | None = None


@dataclass(frozen=True)
class CognitionTopicRecord:
    label: str
    category: str | None


@dataclass(frozen=True)
class CognitionEntityRecord:
    id: str
    entity_type: str
    name: str
    summary: str
    relationship_label: str
    relation_key: str
    weight: float
    closeness: float
    is_self: bool
    world_ring: str | None
    concept_kind: str | None
    core_key: str | None


@dataclass(frozen=True)
class CognitionEventRecord:
    id: str
    occurred_at: str
    event_type: str
    description: str
    importance: float
    topics: tuple[CognitionTopicRecord, ...]
    major_event: bool
    lifecycle_event: str
    title: str
    changed: str
    people: tuple[str, ...]


@dataclass(frozen=True)
class CognitionEdgeRecord:
    source: str
    target: str
    relation_type: str
    summary: str
    weight: float


@dataclass(frozen=True)
class CognitionSnapshotRecord:
    status: CognitionStatus
    entities: tuple[CognitionEntityRecord, ...] = ()
    events: tuple[CognitionEventRecord, ...] = ()
    edges: tuple[CognitionEdgeRecord, ...] = ()
    core_world: str = ""


class ElfiesQueryPort(Protocol):
    def list_directory(
        self,
        *,
        owner_user_id: int | None = None,
        species_id: str | None = None,
    ) -> tuple[ElfieDirectoryRecord, ...]: ...

    def get_directory(self, elfie_id: str) -> ElfieDirectoryRecord | None: ...

    def load_profile(self, elfie_id: str) -> ElfieProfileRecord: ...

    def load_cognition(self, elfie_id: str) -> CognitionSnapshotRecord: ...


__all__ = (
    "CognitionEdgeRecord",
    "CognitionEntityRecord",
    "CognitionEventRecord",
    "CognitionSnapshotRecord",
    "CognitionTopicRecord",
    "ElfieDirectoryRecord",
    "ElfieAppearanceRecord",
    "ElfieProfileRecord",
    "ElfiesPortError",
    "ElfiesQueryPort",
)
