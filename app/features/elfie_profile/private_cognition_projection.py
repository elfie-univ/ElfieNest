"""Project private memory facts into the approved five-module profile DTO."""

from __future__ import annotations

from typing import Final

from app.features.elfie_profile.private_cognition_focus import (
    important_experiences,
    recent_topics,
)
from app.features.elfie_profile.private_cognition_graphs import (
    knowledge_beliefs,
    relationship_world,
    world_understanding,
)
from app.features.elfie_profile.private_cognition_types import (
    PrivateCognitionPayload,
)
from app.infrastructure.persistence.elfie_cognition_reader import (
    CognitionReadResult,
    CognitionStatus,
)

_RINGS: Final[tuple[str, ...]] = ("self", "family", "nest", "society", "outside")


def project_private_cognition(
    result: CognitionReadResult,
    *,
    elfie_id: str,
    elfie_name: str,
) -> PrivateCognitionPayload:
    """Return only bounded, presentation-ready facts for an owned Elfie."""
    if result.snapshot is None:
        return _empty_payload(result.status, elfie_name)
    snapshot = result.snapshot
    return {
        "status": result.status,
        "recent_focus": {"topics": recent_topics(snapshot.events, elfie_name)},
        "important_experiences": {"entries": important_experiences(snapshot.events)},
        "relationship_world": relationship_world(
            snapshot.entities, snapshot.edges, elfie_id, elfie_name
        ),
        "world_understanding": world_understanding(snapshot.entities, snapshot.core_world),
        "knowledge_beliefs": knowledge_beliefs(snapshot.entities, snapshot.edges),
    }


def _empty_payload(status: CognitionStatus, elfie_name: str) -> PrivateCognitionPayload:
    return {
        "status": status,
        "recent_focus": {"topics": []},
        "important_experiences": {"entries": []},
        "relationship_world": {
            "nodes": [{"id": "self", "label": elfie_name, "kind": "self", "weight": 1.0}],
            "edges": [],
        },
        "world_understanding": {"summary": "", "rings": [{"key": key, "nodes": []} for key in _RINGS]},
        "knowledge_beliefs": {"nodes": [], "edges": []},
    }


__all__ = ["PrivateCognitionPayload", "project_private_cognition"]
