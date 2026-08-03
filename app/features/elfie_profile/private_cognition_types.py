"""JSON-safe DTO types for the approved private cognition modules."""

from __future__ import annotations

from typing import TypedDict

from app.infrastructure.persistence.elfie_cognition_reader_models import CognitionStatus


class TopicPayload(TypedDict):
    id: str
    label: str
    category: str
    weight: float


class RecentFocusPayload(TypedDict):
    topics: list[TopicPayload]


class ExperiencePayload(TypedDict):
    id: str
    occurred_at: str
    title: str
    changed: str
    importance: float
    people: list[str]


class ImportantExperiencesPayload(TypedDict):
    entries: list[ExperiencePayload]


class RelationshipNodePayload(TypedDict):
    id: str
    label: str
    kind: str
    weight: float


class RelationshipEdgePayload(TypedDict):
    source: str
    target: str
    relation_key: str
    display_label: str
    weight: float


class RelationshipWorldPayload(TypedDict):
    nodes: list[RelationshipNodePayload]
    edges: list[RelationshipEdgePayload]


class WorldNodePayload(TypedDict):
    id: str
    label: str
    kind: str
    weight: float


class WorldRingPayload(TypedDict):
    key: str
    nodes: list[WorldNodePayload]


class WorldUnderstandingPayload(TypedDict):
    summary: str
    rings: list[WorldRingPayload]


class KnowledgeNodePayload(TypedDict):
    id: str
    label: str
    kind: str
    weight: float


class KnowledgeEdgePayload(TypedDict):
    source: str
    target: str
    relation_key: str
    display_label: str
    weight: float


class KnowledgeBeliefsPayload(TypedDict):
    nodes: list[KnowledgeNodePayload]
    edges: list[KnowledgeEdgePayload]


class PrivateCognitionPayload(TypedDict):
    status: CognitionStatus
    recent_focus: RecentFocusPayload
    important_experiences: ImportantExperiencesPayload
    relationship_world: RelationshipWorldPayload
    world_understanding: WorldUnderstandingPayload
    knowledge_beliefs: KnowledgeBeliefsPayload


__all__ = [
    "ExperiencePayload",
    "ImportantExperiencesPayload",
    "KnowledgeBeliefsPayload",
    "PrivateCognitionPayload",
    "RecentFocusPayload",
    "RelationshipWorldPayload",
    "TopicPayload",
    "WorldUnderstandingPayload",
]
