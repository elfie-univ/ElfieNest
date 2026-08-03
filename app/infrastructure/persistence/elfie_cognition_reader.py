"""Read-only access to one Elfie's final cognition SQLite store."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Final

from app.infrastructure.persistence.elfie_cognition_reader_models import (
    CognitionEdge,
    CognitionEntity,
    CognitionEvent,
    CognitionReadResult,
    CognitionSnapshot,
    CognitionStatus,
    entity_from_row,
    event_from_row,
    number,
    text,
)

logger = logging.getLogger("elfie.profile.cognition_reader")

_REQUIRED_TABLES: Final[frozenset[str]] = frozenset(
    {
        "entities",
        "people",
        "known_elfies",
        "concepts",
        "events",
        "entity_edges",
    }
)


def read_elfie_cognition(path: Path) -> CognitionReadResult:
    """Read a final knowledge database without creating or changing it."""
    if not path.is_file():
        return CognitionReadResult(status="empty", snapshot=None)

    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(
            f"{path.expanduser().resolve(strict=False).as_uri()}?mode=ro",
            uri=True,
            timeout=0.2,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=200")
        connection.execute("PRAGMA query_only=ON")
        tables = _table_names(connection)
        if not tables:
            return CognitionReadResult(status="empty", snapshot=None)
        if not _REQUIRED_TABLES.issubset(tables):
            return CognitionReadResult(status="unavailable", snapshot=None)
        snapshot = _read_snapshot(connection)
    except (OSError, sqlite3.DatabaseError, TypeError, ValueError):
        logger.warning("无法读取精灵认知存储，已降级为不可用状态")
        return CognitionReadResult(status="unavailable", snapshot=None)
    finally:
        if connection is not None:
            connection.close()

    if not snapshot.entities and not snapshot.events and not snapshot.edges:
        return CognitionReadResult(status="empty", snapshot=None)
    return CognitionReadResult(status="ready", snapshot=snapshot)


def _table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return {str(row["name"]) for row in rows}


def _read_snapshot(connection: sqlite3.Connection) -> CognitionSnapshot:
    entity_rows = connection.execute(
        """
        SELECT e.entity_id, e.entity_type, e.name, e.summary, e.confidence,
               e.first_seen_at, e.last_seen_at, e.meta_json,
               p.display_name AS person_display_name,
               p.relationship_label AS person_relationship_label,
               p.closeness_score AS person_closeness,
               p.trust_score AS person_trust,
               p.importance_score AS person_importance,
               p.is_owner,
               k.display_name AS elfie_display_name,
               k.relationship_label AS elfie_relationship_label,
               k.closeness_score AS elfie_closeness,
               k.is_self,
               c.concept_type
          FROM entities AS e
          LEFT JOIN people AS p ON p.entity_id = e.entity_id
          LEFT JOIN known_elfies AS k ON k.entity_id = e.entity_id
          LEFT JOIN concepts AS c ON c.entity_id = e.entity_id
         ORDER BY e.entity_id
        """
    ).fetchall()
    entities = tuple(entity_from_row(row) for row in entity_rows)

    event_rows = connection.execute(
        """
        SELECT e.entity_id, e.first_seen_at, e.last_seen_at,
               e.name, e.summary, e.meta_json,
               ev.event_time, ev.event_type, ev.description,
               ev.importance_score, ev.meta_json AS event_meta_json
          FROM events AS ev
          JOIN entities AS e ON e.entity_id = ev.entity_id
         ORDER BY e.entity_id
        """
    ).fetchall()
    events = tuple(event_from_row(row) for row in event_rows)

    edge_rows = connection.execute(
        """
        SELECT edge_id, source_entity_id, target_entity_id,
               relation_type, summary, weight
          FROM entity_edges
         ORDER BY source_entity_id, target_entity_id, relation_type, edge_id
        """
    ).fetchall()
    edges = tuple(
        CognitionEdge(
            id=str(row["edge_id"]),
            source=str(row["source_entity_id"]),
            target=str(row["target_entity_id"]),
            relation_type=str(row["relation_type"]),
            summary=text(row["summary"]),
            weight=number(row["weight"], 0.5),
        )
        for row in edge_rows
    )

    core_world = ""
    for entity in entities:
        if entity.metadata.get("core_key") == "world":
            core_world = entity.summary or entity.name
            break
    return CognitionSnapshot(
        entities=entities,
        events=events,
        edges=edges,
        core_world=core_world,
    )


__all__ = [
    "CognitionEdge",
    "CognitionEntity",
    "CognitionEvent",
    "CognitionReadResult",
    "CognitionSnapshot",
    "CognitionStatus",
    "read_elfie_cognition",
]
