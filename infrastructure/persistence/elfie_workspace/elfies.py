"""SQLite and workspace Adapter for authorized Elfie projections."""

from __future__ import annotations

import json
import math
import os
import sqlite3
from pathlib import Path
from typing import Final

import yaml

from app.features.elfies import (
    CognitionEdgeRecord,
    CognitionEntityRecord,
    CognitionEventRecord,
    CognitionSnapshotRecord,
    CognitionTopicRecord,
    ElfieAppearanceRecord,
    ElfieDirectoryRecord,
    ElfieProfileRecord,
    ElfiesPortError,
)
from elfie.profile import AppearanceResolver, ResolvedAppearance
from infrastructure.persistence.elfie_workspace.brain_state import (
    YamlSelfhoodSeedAdapter,
)
from infrastructure.persistence.layout.data_home import data_home_from_db_path
from infrastructure.persistence.layout.data_layout import final_root_layout
from infrastructure.persistence.nest_db.sqlite_connection import app_sqlite_connection
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter

_REQUIRED_COGNITION_TABLES: Final[frozenset[str]] = frozenset(
    {"episodes", "nodes", "assertions"}
)
_BIG_FIVE_KEYS: Final[tuple[str, ...]] = (
    "openness",
    "conscientiousness",
    "extraversion",
    "agreeableness",
    "neuroticism",
)


class SQLiteElfiesProjectionAdapter:
    """Read projections and atomically save Elfie-owned portrait assets."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def list_directory(
        self,
        *,
        owner_user_id: int | None = None,
        species_id: str | None = None,
    ) -> tuple[ElfieDirectoryRecord, ...]:
        clauses: list[str] = []
        parameters: list[str | int] = []
        if owner_user_id is not None:
            clauses.append("elfies.owner_user_id=?")
            parameters.append(owner_user_id)
        if species_id is not None:
            clauses.append("elfies.species=?")
            parameters.append(species_id)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        try:
            with app_sqlite_connection(self._db_path) as connection:
                rows = connection.execute(
                    _DIRECTORY_SELECT
                    + where
                    + " ORDER BY elfies.adopted_at, elfies.elfie_id",
                    parameters,
                ).fetchall()
        except sqlite3.Error as error:
            raise ElfiesPortError("unable to read Elfie directory") from error
        return tuple(_directory_record(row) for row in rows)

    def get_directory(self, elfie_id: str) -> ElfieDirectoryRecord | None:
        try:
            with app_sqlite_connection(self._db_path) as connection:
                row = connection.execute(
                    _DIRECTORY_SELECT + " WHERE elfies.elfie_id=?",
                    (elfie_id,),
                ).fetchone()
        except sqlite3.Error as error:
            raise ElfiesPortError("unable to read Elfie directory") from error
        return None if row is None else _directory_record(row)

    def load_profile(self, elfie_id: str) -> ElfieProfileRecord:
        try:
            layout = final_root_layout(data_home_from_db_path(self._db_path))
            elfie_layout = layout.elfie(elfie_id)
            repository = YamlProfileStoreAdapter(elfie_layout.profile.parent)
        except ValueError as error:
            raise ElfiesPortError("invalid Elfie identity") from error
        if not repository.exists():
            return ElfieProfileRecord(
                status="empty",
                portrait_url=_portrait_url(elfie_layout, elfie_id),
            )
        try:
            profile = repository.load()
            resolved = AppearanceResolver().resolve(profile)
            raw_big_five = (
                YamlSelfhoodSeedAdapter(elfie_layout.brain).load().get("big_five")
            )
            if not isinstance(raw_big_five, dict):
                return ElfieProfileRecord(
                    status="ready",
                    appearance=_appearance_record(resolved),
                    portrait_url=_portrait_url(elfie_layout, elfie_id),
                )
            values = {
                key: _optional_number(raw_big_five.get(key)) for key in _BIG_FIVE_KEYS
            }
        except (OSError, ValueError, yaml.YAMLError):
            return ElfieProfileRecord(status="unavailable")
        return ElfieProfileRecord(
            status="ready",
            openness=values["openness"],
            conscientiousness=values["conscientiousness"],
            extraversion=values["extraversion"],
            agreeableness=values["agreeableness"],
            neuroticism=values["neuroticism"],
            appearance=_appearance_record(resolved),
            portrait_url=_portrait_url(elfie_layout, elfie_id),
        )

    def load_portrait(self, elfie_id: str, *, kind: str = "headshot") -> bytes | None:
        try:
            layout = final_root_layout(data_home_from_db_path(self._db_path)).elfie(
                elfie_id
            )
        except ValueError as error:
            raise ElfiesPortError("invalid Elfie identity") from error
        path = (
            layout.portrait_full_body
            if kind == "full_body"
            else layout.portrait_headshot
        )
        try:
            return path.read_bytes() if path.is_file() else None
        except OSError as error:
            raise ElfiesPortError("unable to read Elfie portrait") from error

    def save_portrait(self, elfie_id: str, content: bytes) -> None:
        try:
            layout = final_root_layout(data_home_from_db_path(self._db_path)).elfie(
                elfie_id
            )
        except ValueError as error:
            raise ElfiesPortError("invalid Elfie identity") from error
        try:
            layout.portrait_headshot.parent.mkdir(parents=True, exist_ok=True)
            _write_private_asset(layout.portrait_headshot, content)
        except OSError as error:
            raise ElfiesPortError("unable to save Elfie portrait") from error

    def load_cognition(self, elfie_id: str) -> CognitionSnapshotRecord:
        try:
            layout = final_root_layout(data_home_from_db_path(self._db_path))
            path = layout.elfie(elfie_id).knowledge_database
        except ValueError as error:
            raise ElfiesPortError("invalid Elfie identity") from error
        return _read_cognition(path)


_DIRECTORY_SELECT = """
SELECT elfies.elfie_id, elfies.name, elfies.owner_user_id,
       users.account_id AS owner_account_id,
       users.display_name AS owner_display_name,
       elfies.species, elfies.gender, elfies.birth_date,
       elfies.adopted_at, elfies.summary
FROM elfies JOIN users ON users.id=elfies.owner_user_id
"""


def _appearance_record(resolved: ResolvedAppearance) -> ElfieAppearanceRecord:
    payload = resolved.to_payload()
    material_parameters = {
        str(key): float(value) if isinstance(value, (int, float)) else str(value)
        for key, value in sorted(payload["material_parameters"].items())
    }
    return ElfieAppearanceRecord(
        species_id=str(payload["species_id"]),
        profile_version=int(payload["profile_version"]),
        height_scale=float(payload["height_scale"]),
        build_scale=float(payload["build_scale"]),
        height_label=str(payload["height_label"]),
        build_label=str(payload["build_label"]),
        bone_scales={
            str(key): float(value)
            for key, value in sorted(payload["bone_scales"].items())
        },
        blend_shapes={
            str(key): float(value)
            for key, value in sorted(payload["blend_shapes"].items())
        },
        material_parameters=material_parameters,
        species_traits={
            str(key): float(value)
            for key, value in sorted(payload["species_traits"].items())
        },
    )


def _directory_record(row: sqlite3.Row) -> ElfieDirectoryRecord:
    return ElfieDirectoryRecord(
        elfie_id=str(row["elfie_id"]),
        name=str(row["name"]),
        owner_user_id=int(row["owner_user_id"]),
        owner_account_id=str(row["owner_account_id"]),
        owner_display_name=(
            None
            if row["owner_display_name"] is None
            else str(row["owner_display_name"])
        ),
        species_id=str(row["species"]),
        gender=None if row["gender"] is None else str(row["gender"]),
        birth_date=(None if row["birth_date"] is None else str(row["birth_date"])),
        adopted_at=str(row["adopted_at"]),
        summary=None if row["summary"] is None else str(row["summary"]),
    )


def _portrait_url(layout, elfie_id: str) -> str:
    return (
        f"/api/v1/elfies/{elfie_id}/portrait"
        if layout.portrait_headshot.is_file()
        else ""
    )


def _write_private_asset(path: Path, content: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            os.chmod(path, 0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_cognition(path: Path) -> CognitionSnapshotRecord:
    if not path.is_file():
        return CognitionSnapshotRecord(status="empty")
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
        tables = {
            str(row["name"])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if not tables:
            return CognitionSnapshotRecord(status="empty")
        if not _REQUIRED_COGNITION_TABLES.issubset(tables):
            return CognitionSnapshotRecord(status="unavailable")
        snapshot = _cognition_snapshot(connection)
    except (OSError, sqlite3.DatabaseError, TypeError, ValueError):
        return CognitionSnapshotRecord(status="unavailable")
    finally:
        if connection is not None:
            connection.close()
    if not snapshot.entities and not snapshot.events and not snapshot.edges:
        return CognitionSnapshotRecord(status="empty")
    return snapshot


def _cognition_snapshot(connection: sqlite3.Connection) -> CognitionSnapshotRecord:
    entity_rows = connection.execute(
        """SELECT node_id, node_type, canonical_label, description, confidence,
                  properties_json, status
             FROM nodes WHERE status <> 'forgotten' ORDER BY node_id"""
    ).fetchall()
    entities = tuple(_target_cognition_entity(row) for row in entity_rows)
    event_rows = connection.execute(
        """SELECT episode_id, occurred_from, occurred_to, content_text,
                  summary_text, event_kind, importance, metadata_json, lifecycle
             FROM episodes WHERE lifecycle <> 'forgotten'
             ORDER BY occurred_from, episode_id"""
    ).fetchall()
    events = tuple(_target_cognition_event(row, connection) for row in event_rows)
    edge_rows = connection.execute(
        """SELECT subject_node_id, object_node_id, predicate, context,
                  support_score FROM assertions
             WHERE lifecycle='active' AND object_node_id IS NOT NULL
             ORDER BY subject_node_id, object_node_id, predicate, assertion_id"""
    ).fetchall()
    edges = tuple(
        CognitionEdgeRecord(
            source=str(row["subject_node_id"]),
            target=str(row["object_node_id"]),
            relation_type=str(row["predicate"]),
            summary=_text(row["context"]),
            weight=_number(row["support_score"], 0.5),
        )
        for row in edge_rows
    )
    core_world = next(
        (
            entity.summary or entity.name
            for entity in entities
            if entity.core_key == "world"
        ),
        "",
    )
    return CognitionSnapshotRecord(
        status="ready",
        entities=entities,
        events=events,
        edges=edges,
        core_world=core_world,
    )


def _target_cognition_entity(row: sqlite3.Row) -> CognitionEntityRecord:
    metadata = _target_metadata(row["properties_json"])
    entity_type = _text(row["node_type"]) or "object"
    return CognitionEntityRecord(
        id=str(row["node_id"]),
        entity_type=entity_type,
        name=_text(row["canonical_label"]),
        summary=_text(row["description"]),
        relationship_label=(
            _text(metadata.get("relationship_label"))
            or _text(metadata.get("relationship"))
        ),
        relation_key=(
            _text(metadata.get("relation_kind"))
            or _text(metadata.get("relationship_key"))
            or ""
        ),
        weight=max(
            _number(metadata.get("importance")),
            _number(metadata.get("importance_score")),
            _number(row["confidence"]),
        ),
        closeness=max(
            _number(metadata.get("closeness_score")),
            _number(metadata.get("trust_score")),
        ),
        is_self=bool(metadata.get("is_self")),
        world_ring=_optional_text(metadata.get("world_ring")),
        concept_kind=(
            _optional_text(metadata.get("kind"))
            or _optional_text(metadata.get("concept_type"))
            or (entity_type if entity_type not in {"entity", "object"} else None)
        ),
        core_key=_optional_text(metadata.get("core_key")),
    )


def _target_cognition_event(
    row: sqlite3.Row,
    connection: sqlite3.Connection,
) -> CognitionEventRecord:
    metadata = _target_metadata(row["metadata_json"])
    mention_rows = connection.execute(
        """SELECT n.canonical_label, n.node_type
             FROM episode_mentions AS m JOIN nodes AS n ON n.node_id=m.node_id
            WHERE m.episode_id=? AND m.resolution_state='resolved'
            ORDER BY m.mention_id LIMIT 32""",
        (row["episode_id"],),
    ).fetchall()
    topics = tuple(
        CognitionTopicRecord(
            label=str(item["canonical_label"]),
            category=_optional_text(item["node_type"]),
        )
        for item in mention_rows
    )
    if not topics:
        raw_topics = metadata.get("topics")
        if isinstance(raw_topics, dict):
            raw_topics = tuple(raw_topics.items())
        if isinstance(raw_topics, (list, tuple)):
            topic_values: list[CognitionTopicRecord] = []
            for item in raw_topics:
                if isinstance(item, str) and item.strip():
                    topic_values.append(CognitionTopicRecord(item.strip(), None))
                elif isinstance(item, dict):
                    label = _text(item.get("label") or item.get("topic"))
                    if label:
                        topic_values.append(
                            CognitionTopicRecord(
                                label,
                                _optional_text(item.get("category")),
                            )
                        )
            topics = tuple(topic_values)
    return CognitionEventRecord(
        id=str(row["episode_id"]),
        occurred_at=str(row["occurred_from"]),
        event_type=_text(row["event_kind"]),
        description=_text(row["summary_text"] or row["content_text"]),
        importance=_number(row["importance"]),
        topics=topics,
        major_event=bool(metadata.get("major_event")),
        lifecycle_event=_text(metadata.get("lifecycle_event")),
        title=_text(metadata.get("title")),
        changed=_text(metadata.get("changed")),
        people=_string_items(metadata.get("people")),
    )


def _cognition_entity(row: sqlite3.Row) -> CognitionEntityRecord:
    metadata = _memory_metadata(row["meta_json"])
    entity_type = _text(row["entity_type"])
    person_display = _text(row["person_display_name"])
    elfie_display = _text(row["elfie_display_name"])
    if person_display:
        entity_type = "person"
    elif elfie_display or row["is_self"] is not None:
        entity_type = "elfie"
    return CognitionEntityRecord(
        id=str(row["entity_id"]),
        entity_type=entity_type,
        name=_text(row["name"]),
        summary=_text(row["summary"]),
        relationship_label=(
            _text(row["person_relationship_label"])
            or _text(row["elfie_relationship_label"])
            or _text(metadata.get("relationship"))
        ),
        relation_key=(
            _text(metadata.get("relation_kind"))
            or _text(metadata.get("relationship_key"))
        ),
        weight=max(
            _number(row["person_importance"]),
            _number(metadata.get("importance")),
            _number(row["confidence"]),
        ),
        closeness=max(
            _number(row["person_closeness"]),
            _number(row["elfie_closeness"]),
        ),
        is_self=bool(row["is_self"]),
        world_ring=_optional_text(metadata.get("world_ring")),
        concept_kind=(
            _optional_text(metadata.get("kind"))
            or _optional_text(metadata.get("concept_type"))
            or _optional_text(row["concept_type"])
        ),
        core_key=_optional_text(metadata.get("core_key")),
    )


def _cognition_event(row: sqlite3.Row) -> CognitionEventRecord:
    metadata = _json_object(row["event_meta_json"])
    if not metadata:
        metadata = _memory_metadata(row["meta_json"])
    occurred_at = (
        _text(row["event_time"])
        or _text(row["last_seen_at"])
        or _text(row["first_seen_at"])
    )
    description = (
        _text(row["description"]) or _text(row["summary"]) or _text(row["name"])
    )
    importance = max(
        _number(row["importance_score"]),
        _number(metadata.get("importance")),
        _number(metadata.get("emotion_intensity")),
        _number(metadata.get("intensity")) / 100.0,
    )
    return CognitionEventRecord(
        id=str(row["entity_id"]),
        occurred_at=occurred_at,
        event_type=_text(row["event_type"]),
        description=description,
        importance=importance,
        topics=_topics(metadata),
        major_event=bool(metadata.get("major_event")),
        lifecycle_event=_text(metadata.get("lifecycle_event")),
        title=_text(metadata.get("title")),
        changed=_text(metadata.get("changed")),
        people=_string_items(metadata.get("people")),
    )


def _memory_metadata(value: object) -> dict[str, object]:
    wrapper = _json_object(value)
    nested = wrapper.get("memory_metadata")
    return _string_key_object(nested)


def _target_metadata(value: object) -> dict[str, object]:
    """Decode target node/episode properties without legacy wrappers."""
    return _string_key_object(_json_object(value))


def _topics(metadata: dict[str, object]) -> tuple[CognitionTopicRecord, ...]:
    raw = metadata.get("topics", metadata.get("topic_metadata"))
    if isinstance(raw, dict):
        raw = tuple(raw.items())
    if not isinstance(raw, (list, tuple)):
        return ()
    topics: list[CognitionTopicRecord] = []
    for item in raw:
        if isinstance(item, str):
            label = item.strip()
            if label:
                topics.append(
                    CognitionTopicRecord(
                        label=label,
                        category=_optional_text(metadata.get("topic_category")),
                    )
                )
        elif isinstance(item, dict):
            topic = _string_key_object(item)
            label = _text(topic.get("label", topic.get("topic")))
            if label:
                topics.append(
                    CognitionTopicRecord(
                        label=label,
                        category=(
                            _optional_text(topic.get("category"))
                            or _optional_text(topic.get("topic_category"))
                        ),
                    )
                )
    return tuple(topics)


def _json_object(value: object) -> dict[str, object]:
    if not isinstance(value, str) or not value:
        return {}
    parsed: object = json.loads(value)
    return _string_key_object(parsed)


def _string_key_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _string_items(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(
        item.strip() for item in value if isinstance(item, str) and item.strip()
    )


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _optional_text(value: object) -> str | None:
    normalized = _text(value)
    return normalized or None


def _number(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    numeric = float(value)
    return min(1.0, max(0.0, numeric)) if math.isfinite(numeric) else default


def _optional_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    if not math.isfinite(numeric):
        return None
    return min(1.0, max(0.0, numeric))


__all__ = ("SQLiteElfiesProjectionAdapter",)
