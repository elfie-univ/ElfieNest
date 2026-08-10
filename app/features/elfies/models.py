"""Queries and results owned by the Elfies projection Feature."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ElfieRelationship = Literal["owned"]
CognitionStatus = Literal["ready", "empty", "unavailable"]
WorldRingKey = Literal["self", "family", "nest", "society", "outside"]


@dataclass(frozen=True)
class ListVisibleElfiesQuery:
    relationship: ElfieRelationship | None = None


@dataclass(frozen=True)
class GetElfieProfileQuery:
    elfie_id: str


@dataclass(frozen=True)
class ListAdminElfiesQuery:
    owner_user_id: int | None = None
    species_id: str | None = None


@dataclass(frozen=True)
class BigFiveResult:
    openness: float | None
    conscientiousness: float | None
    extraversion: float | None
    agreeableness: float | None
    neuroticism: float | None


@dataclass(frozen=True)
class ElfieProfileResult:
    elfie_id: str
    name: str
    species_id: str
    gender: str | None
    birth_date: str | None
    summary: str | None
    adopted_at: str
    profile_status: Literal["ready", "empty", "unavailable"]
    big_five: BigFiveResult | None
    personality_tags: tuple[str, ...]


@dataclass(frozen=True)
class ElfiePermissionsResult:
    can_view_profile: bool
    can_view_cognition: bool


@dataclass(frozen=True)
class VisibleElfieResult:
    relationship: ElfieRelationship
    permissions: ElfiePermissionsResult
    profile: ElfieProfileResult


@dataclass(frozen=True)
class ElfieOwnerResult:
    user_id: int
    account_id: str
    display_name: str | None


@dataclass(frozen=True)
class AdminElfieResult:
    owner: ElfieOwnerResult
    permissions: ElfiePermissionsResult
    profile: ElfieProfileResult


@dataclass(frozen=True)
class TopicResult:
    id: str
    label: str
    category: str
    weight: float


@dataclass(frozen=True)
class RecentFocusResult:
    topics: tuple[TopicResult, ...]


@dataclass(frozen=True)
class ExperienceResult:
    id: str
    occurred_at: str
    title: str
    changed: str
    importance: float
    people: tuple[str, ...]


@dataclass(frozen=True)
class ImportantExperiencesResult:
    entries: tuple[ExperienceResult, ...]


@dataclass(frozen=True)
class GraphNodeResult:
    id: str
    label: str
    kind: str
    weight: float


@dataclass(frozen=True)
class GraphEdgeResult:
    source: str
    target: str
    relation_key: str
    display_label: str
    weight: float


@dataclass(frozen=True)
class RelationshipWorldResult:
    nodes: tuple[GraphNodeResult, ...]
    edges: tuple[GraphEdgeResult, ...]


@dataclass(frozen=True)
class WorldRingResult:
    key: WorldRingKey
    nodes: tuple[GraphNodeResult, ...]


@dataclass(frozen=True)
class WorldUnderstandingResult:
    summary: str
    rings: tuple[WorldRingResult, ...]


@dataclass(frozen=True)
class KnowledgeBeliefsResult:
    nodes: tuple[GraphNodeResult, ...]
    edges: tuple[GraphEdgeResult, ...]


@dataclass(frozen=True)
class ElfieCognitionResult:
    status: CognitionStatus
    recent_focus: RecentFocusResult
    important_experiences: ImportantExperiencesResult
    relationship_world: RelationshipWorldResult
    world_understanding: WorldUnderstandingResult
    knowledge_beliefs: KnowledgeBeliefsResult


@dataclass(frozen=True)
class ElfieProfileDetailResult:
    relationship: ElfieRelationship
    permissions: ElfiePermissionsResult
    profile: ElfieProfileResult
    private_cognition: ElfieCognitionResult


__all__ = (
    "AdminElfieResult",
    "BigFiveResult",
    "CognitionStatus",
    "ElfieCognitionResult",
    "ElfieOwnerResult",
    "ElfiePermissionsResult",
    "ElfieProfileDetailResult",
    "ElfieProfileResult",
    "ElfieRelationship",
    "ExperienceResult",
    "GetElfieProfileQuery",
    "GraphEdgeResult",
    "GraphNodeResult",
    "ImportantExperiencesResult",
    "KnowledgeBeliefsResult",
    "ListAdminElfiesQuery",
    "ListVisibleElfiesQuery",
    "RecentFocusResult",
    "TopicResult",
    "VisibleElfieResult",
    "WorldRingKey",
    "WorldRingResult",
    "WorldUnderstandingResult",
)
