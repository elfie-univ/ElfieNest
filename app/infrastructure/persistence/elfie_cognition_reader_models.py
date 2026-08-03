"""Typed row models for the read-only Elfie cognition reader."""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from typing import Any, Literal

CognitionStatus = Literal["ready", "empty", "unavailable"]


@dataclass(frozen=True)
class CognitionEntity:
    """A safe, denormalized entity row used by the feature projection."""

    __slots__ = (
        "id", "entity_type", "name", "summary", "metadata",
        "relationship_label", "relation_key", "weight", "is_self",
    )

    id: str
    entity_type: str
    name: str
    summary: str
    metadata: dict[str, Any]
    relationship_label: str
    relation_key: str
    weight: float
    is_self: bool


@dataclass(frozen=True)
class CognitionEvent:
    """An event row with its original bounded metadata."""

    __slots__ = ("id", "occurred_at", "event_type", "description", "importance", "metadata")

    id: str
    occurred_at: str
    event_type: str
    description: str
    importance: float
    metadata: dict[str, Any]


@dataclass(frozen=True)
class CognitionEdge:
    """A stored directed edge between final entity rows."""

    __slots__ = ("id", "source", "target", "relation_type", "summary", "weight")

    id: str
    source: str
    target: str
    relation_type: str
    summary: str
    weight: float


@dataclass(frozen=True)
class CognitionSnapshot:
    """All rows needed by the five approved cognition modules."""

    __slots__ = ("entities", "events", "edges", "core_world")

    entities: tuple[CognitionEntity, ...]
    events: tuple[CognitionEvent, ...]
    edges: tuple[CognitionEdge, ...]
    core_world: str


@dataclass(frozen=True)
class CognitionReadResult:
    """A bounded read outcome; storage failures never escape to the API."""

    __slots__ = ("status", "snapshot")

    status: CognitionStatus
    snapshot: CognitionSnapshot | None


def entity_from_row(row: sqlite3.Row) -> CognitionEntity:
    """Convert one final entity row without exposing raw JSON to callers."""
    wrapper = _json_object(row["meta_json"])
    nested = wrapper.get("memory_metadata")
    metadata = dict(nested) if isinstance(nested, dict) else {}
    concept_type = _text(row["concept_type"])
    if concept_type:
        metadata.setdefault("concept_type", concept_type)
    entity_type = _text(row["entity_type"])
    person_display = _text(row["person_display_name"])
    elfie_display = _text(row["elfie_display_name"])
    if person_display:
        entity_type = "person"
    elif elfie_display or row["is_self"] is not None:
        entity_type = "elfie"
    relation_label = _text(row["person_relationship_label"]) or _text(
        row["elfie_relationship_label"]
    ) or _text(metadata.get("relationship"))
    relation_key = _text(metadata.get("relation_kind")) or _text(
        metadata.get("relationship_key")
    )
    direct_weight = max(
        _number(row["person_importance"]), _number(row["person_closeness"]),
        _number(row["person_trust"]), _number(row["elfie_closeness"]),
        _number(metadata.get("importance")), _number(row["confidence"]),
    )
    return CognitionEntity(
        id=str(row["entity_id"]), entity_type=entity_type,
        name=_text(row["name"]), summary=_text(row["summary"]),
        metadata=metadata, relationship_label=relation_label,
        relation_key=relation_key, weight=direct_weight,
        is_self=bool(row["is_self"]),
    )


def event_from_row(row: sqlite3.Row) -> CognitionEvent:
    """Convert one final event row into the bounded projection input."""
    metadata = _json_object(row["event_meta_json"])
    if not metadata:
        wrapper = _json_object(row["meta_json"])
        nested = wrapper.get("memory_metadata")
        metadata = dict(nested) if isinstance(nested, dict) else {}
    occurred_at = _text(row["event_time"]) or _text(row["last_seen_at"]) or _text(
        row["first_seen_at"]
    )
    description = _text(row["description"]) or _text(row["summary"]) or _text(
        row["name"]
    )
    return CognitionEvent(
        id=str(row["entity_id"]), occurred_at=occurred_at,
        event_type=_text(row["event_type"]), description=description,
        importance=_number(row["importance_score"]), metadata=metadata,
    )


def json_object(value: Any) -> dict[str, Any]:
    """Parse a JSON object stored in a final cognition row."""
    return _json_object(value)


def text(value: Any) -> str:
    """Normalize nullable SQLite text values."""
    return _text(value)


def number(value: Any, default: float = 0.0) -> float:
    """Normalize a bounded numeric SQLite value."""
    return _number(value, default)


def _json_object(value: Any) -> dict[str, Any]:
    if not isinstance(value, str) or not value:
        return {}
    parsed = json.loads(value)
    return parsed if isinstance(parsed, dict) else {}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    numeric = float(value)
    return min(1.0, max(0.0, numeric)) if math.isfinite(numeric) else default


__all__ = [
    "CognitionEdge", "CognitionEntity", "CognitionEvent",
    "CognitionReadResult", "CognitionSnapshot", "CognitionStatus",
    "entity_from_row", "event_from_row", "json_object", "number", "text",
]
