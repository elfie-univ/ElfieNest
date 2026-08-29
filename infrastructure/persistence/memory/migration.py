"""One-way importer from the pre-episodes SQLite layout.

The importer never mutates the source database. It requires a fresh target so
that a failed import can be discarded and retried without dual-write state.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from elfie.brain.memory.memory_records import (
    AssertionInput,
    ClosedEpisode,
    EvidenceInput,
    NodeInput,
)

from .sqlite_memory_store import SQLiteMemoryStoreAdapter
from .sqlite_utils import bounded_score, json_object

_LEGACY_TABLES = frozenset(
    {
        "entities",
        "people",
        "known_elfies",
        "concepts",
        "places",
        "events",
        "entity_edges",
        "memory_notes",
        "source_evidence_links",
    }
)


@dataclass(frozen=True)
class MigrationReport:
    """Reconciliation evidence for one source-to-fresh-target import."""

    source_path: str
    target_path: str
    source_entities: int = 0
    source_events: int = 0
    source_edges: int = 0
    imported_nodes: int = 0
    imported_episodes: int = 0
    imported_assertions: int = 0
    imported_evidence: int = 0
    skipped_rows: int = 0
    source_digest: str = ""
    target_digest: str = ""
    episode_hash_matches: int = 0
    episode_hash_mismatches: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    # Keys are namespaced by legacy family (``entity:<id>``, ``event:<id>``,
    # ``edge:<id>`` and ``source_link:<id>``) because old IDs were not
    # globally unique across tables.
    id_mapping: Mapping[str, str] = field(default_factory=dict)

    @property
    def reconciled(self) -> bool:
        return (
            self.source_entities <= self.imported_nodes
            and self.source_events == self.imported_episodes
            and self.imported_assertions == self.source_edges
            and self.episode_hash_matches == self.imported_episodes
            and not self.episode_hash_mismatches
            and not self.skipped_rows
            and bool(self.target_digest)
        )


def import_legacy_database(
    source_path: str | Path,
    target_path: str | Path,
) -> MigrationReport:
    """Import the old entity graph into a fresh target database.

    Existing target files are accepted only when they contain no user tables.
    This prevents accidental overwrite of a live Memory database.
    """
    source = Path(source_path)
    target = Path(target_path)
    if source.resolve() == target.resolve():
        raise ValueError("source and target database must be different")
    if not source.is_file():
        raise FileNotFoundError(source)
    _validate_fresh_target(target)
    source_digest = _database_digest(source)
    warnings: list[str] = []
    id_mapping: dict[str, str] = {}
    with _readonly(source) as connection, SQLiteMemoryStoreAdapter(target) as store:
        tables = _tables(connection)
        if not _LEGACY_TABLES.intersection(tables):
            raise ValueError(
                "source database does not contain the legacy Memory schema"
            )
        source_entities = _count(connection, "entities")
        source_events = _count(connection, "events")
        source_edges = _count(connection, "entity_edges")
        imported_nodes = _import_entities(connection, store, warnings, id_mapping)
        imported_episodes = _import_events(connection, store, warnings, id_mapping)
        imported_assertions, imported_evidence = _import_edges(
            connection, store, warnings, id_mapping
        )
        linked_assertions, linked_evidence = _import_source_links(
            connection, store, warnings, id_mapping
        )
        _report_unresolved_notes(connection, warnings)
        episode_hash_matches, episode_hash_mismatches = _reconcile_episode_hashes(
            connection, store
        )
        target_digest = _database_digest(target)
    return MigrationReport(
        source_path=str(source),
        target_path=str(target),
        source_entities=source_entities,
        source_events=source_events,
        source_edges=source_edges,
        imported_nodes=imported_nodes,
        imported_episodes=imported_episodes,
        imported_assertions=imported_assertions + linked_assertions,
        imported_evidence=imported_evidence + linked_evidence,
        skipped_rows=len(warnings),
        source_digest=source_digest,
        target_digest=target_digest,
        episode_hash_matches=episode_hash_matches,
        episode_hash_mismatches=episode_hash_mismatches,
        warnings=tuple(warnings),
        id_mapping=dict(sorted(id_mapping.items())),
    )


def _validate_fresh_target(target: Path) -> None:
    if target.exists():
        if target.is_symlink() or not target.is_file():
            raise ValueError(f"unsafe migration target: {target}")
        with sqlite3.connect(str(target)) as connection:
            tables = _tables(connection)
        if tables:
            raise ValueError("migration target must be a fresh empty database")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def _readonly(path: Path):
    connection = sqlite3.connect(
        f"{path.expanduser().resolve(strict=True).as_uri()}?mode=ro",
        uri=True,
        timeout=2.0,
    )
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row["name"])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _count(connection: sqlite3.Connection, table: str) -> int:
    return (
        int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        if table in _tables(connection)
        else 0
    )


def _import_entities(
    connection: sqlite3.Connection,
    store: SQLiteMemoryStoreAdapter,
    warnings: list[str],
    id_mapping: dict[str, str],
) -> int:
    if "entities" not in _tables(connection):
        return 0
    imported = 0
    for row in connection.execute("SELECT * FROM entities ORDER BY entity_id"):
        metadata = json_object(row["meta_json"])
        for table, key in (
            ("people", "entity_id"),
            ("known_elfies", "entity_id"),
            ("concepts", "entity_id"),
            ("places", "entity_id"),
        ):
            if table not in _tables(connection):
                continue
            subtype = connection.execute(
                f"SELECT * FROM {table} WHERE {key}=?", (row["entity_id"],)
            ).fetchone()
            if subtype is not None:
                metadata[f"legacy_{table}"] = {
                    str(column): subtype[column] for column in subtype.keys()
                }
        node_type = str(metadata.get("memory_node_type") or row["entity_type"])
        try:
            store.upsert_node_record(
                NodeInput(
                    node_id=str(row["entity_id"]),
                    node_type=node_type,
                    canonical_label=str(row["name"]),
                    description=row["summary"],
                    confidence=bounded_score(row["confidence"]),
                    importance=bounded_score(
                        metadata.get(
                            "importance", metadata.get("importance_score", 0.5)
                        )
                    ),
                    properties=metadata,
                )
            )
            imported += 1
            id_mapping[f"entity:{row['entity_id']}"] = str(row["entity_id"])
        except (TypeError, ValueError, sqlite3.DatabaseError) as error:
            warnings.append(f"entity {row['entity_id']}: {error}")
    return imported


def _import_events(
    connection: sqlite3.Connection,
    store: SQLiteMemoryStoreAdapter,
    warnings: list[str],
    id_mapping: dict[str, str],
) -> int:
    if "events" not in _tables(connection):
        return 0
    imported = 0
    entity_columns = _columns(connection, "entities")
    event_columns = _columns(connection, "events")
    entity_name = "e.name" if "name" in entity_columns else "NULL"
    entity_summary = "e.summary" if "summary" in entity_columns else "NULL"
    entity_first_seen = (
        "e.first_seen_at" if "first_seen_at" in entity_columns else "NULL"
    )
    entity_meta = "e.meta_json" if "meta_json" in entity_columns else "NULL"
    event_time = "ev.event_time" if "event_time" in event_columns else "NULL"
    event_type = "ev.event_type" if "event_type" in event_columns else "NULL"
    event_description = "ev.description" if "description" in event_columns else "NULL"
    event_importance = (
        "ev.importance_score" if "importance_score" in event_columns else "0.5"
    )
    event_meta = "ev.meta_json" if "meta_json" in event_columns else "NULL"
    for row in connection.execute(
        f"""SELECT ev.*, {entity_name} AS entity_name,
                    {entity_summary} AS entity_summary,
                    {entity_first_seen} AS entity_first_seen,
                    {entity_meta} AS entity_meta,
                    {event_time} AS legacy_event_time,
                    {event_type} AS legacy_event_type,
                    {event_description} AS legacy_description,
                    {event_importance} AS legacy_importance,
                    {event_meta} AS legacy_meta
             FROM events AS ev LEFT JOIN entities AS e ON e.entity_id=ev.entity_id
             ORDER BY {"ev.event_time, " if "event_time" in event_columns else ""}ev.entity_id"""
    ):
        content = str(
            row["legacy_description"]
            or row["entity_summary"]
            or row["entity_name"]
            or ""
        ).strip()
        if not content:
            warnings.append(f"event {row['entity_id']}: missing complete content")
            continue
        occurred_value = row["legacy_event_time"] or row["entity_first_seen"]
        occurred = None if occurred_value is None else str(occurred_value)
        metadata = json_object(row["legacy_meta"])
        metadata.update(json_object(row["entity_meta"]))
        metadata.setdefault(
            "legacy_content_sha256",
            hashlib.sha256(content.encode("utf-8")).hexdigest(),
        )
        try:
            store.record_episode(
                ClosedEpisode(
                    episode_id=str(row["entity_id"]),
                    idempotency_key=f"legacy:event:{row['entity_id']}",
                    occurred_from=occurred,
                    occurrence_precision="exact" if occurred is not None else "unknown",
                    content_text=content,
                    event_kind=str(row["legacy_event_type"] or "legacy"),
                    importance=bounded_score(row["legacy_importance"]),
                    source_event_ids=(str(row["entity_id"]),),
                    source_version=(
                        str(metadata.get("source_version"))
                        if metadata.get("source_version")
                        else None
                    ),
                    privacy_scope=str(metadata.get("privacy_scope", "private")),
                    metadata=metadata,
                )
            )
            imported += 1
            id_mapping[f"event:{row['entity_id']}"] = str(row["entity_id"])
        except (TypeError, ValueError, sqlite3.DatabaseError) as error:
            warnings.append(f"event {row['entity_id']}: {error}")
    return imported


def _import_edges(
    connection: sqlite3.Connection,
    store: SQLiteMemoryStoreAdapter,
    warnings: list[str],
    id_mapping: dict[str, str],
) -> tuple[int, int]:
    if "entity_edges" not in _tables(connection):
        return 0, 0
    imported = 0
    evidence_count = 0
    for row in connection.execute("SELECT * FROM entity_edges ORDER BY edge_id"):
        edge_id = str(row["edge_id"])
        # An old edge has no trustworthy source by itself.  Keeping it as an
        # active Assertion would manufacture provenance, so migration records
        # an explicit skip until an operator links it to a verified Episode or
        # approved seed source.
        warnings.append(f"edge {edge_id}: skipped source-less legacy edge")
    return imported, evidence_count


def _import_source_links(
    connection: sqlite3.Connection,
    store: SQLiteMemoryStoreAdapter,
    warnings: list[str],
    id_mapping: dict[str, str],
) -> tuple[int, int]:
    # Legacy links may refer to an edge or note. Edge source IDs are already
    # represented above; retain unresolvable links as standalone evidence so
    # provenance is not silently discarded.
    if "source_evidence_links" not in _tables(connection):
        return 0, 0
    imported_assertions = 0
    imported_evidence = 0
    for row in connection.execute(
        "SELECT * FROM source_evidence_links ORDER BY link_id"
    ):
        evidence_id = f"legacy-link:{row['link_id']}"
        try:
            if str(row["target_type"]) == "edge" and "entity_edges" in _tables(
                connection
            ):
                edge = connection.execute(
                    "SELECT * FROM entity_edges WHERE edge_id=?",
                    (row["target_id"],),
                ).fetchone()
                if edge is None:
                    warnings.append(
                        f"source link {row['link_id']}: unknown edge target"
                    )
                    continue
                source_id = str(row["source_id"])
                source_episode = store.get_episode(source_id)
                if source_episode is None:
                    warnings.append(
                        f"source link {row['link_id']}: edge source is not a verified Episode"
                    )
                    continue
                store.record_sourced_assertion(
                    AssertionInput(
                        subject_id=str(edge["source_entity_id"]),
                        predicate=str(edge["relation_type"]),
                        object_node_id=str(edge["target_entity_id"]),
                        confidence=bounded_score(edge["confidence"]),
                        support_score=bounded_score(edge["weight"]),
                        importance=bounded_score(edge["weight"]),
                        evidence_ids=(evidence_id,),
                        assertion_id=f"legacy-assertion:{edge['edge_id']}",
                    ),
                    EvidenceInput(
                        evidence_id=evidence_id,
                        source_type="episode",
                        source_id=source_id,
                        excerpt=f"legacy edge link {row['target_id']}",
                        source_sha256=source_episode.content_sha256,
                        source_version=source_episode.source_version,
                    ),
                )
                imported_assertions += 1
                imported_evidence += 1
                id_mapping[f"edge:{edge['edge_id']}"] = (
                    f"legacy-assertion:{edge['edge_id']}"
                )
                id_mapping[f"source_link:{row['link_id']}"] = evidence_id
                continue
            warnings.append(
                f"source link {row['link_id']}: skipped unverified legacy source"
            )
        except (TypeError, ValueError, sqlite3.DatabaseError) as error:
            warnings.append(f"source link {row['link_id']}: {error}")
    return imported_assertions, imported_evidence


def _reconcile_episode_hashes(
    connection: sqlite3.Connection,
    store: SQLiteMemoryStoreAdapter,
) -> tuple[int, tuple[str, ...]]:
    """Compare eligible legacy event content with target Episode hashes."""
    if "events" not in _tables(connection):
        return 0, ()
    entity_columns = (
        _columns(connection, "entities") if "entities" in _tables(connection) else set()
    )
    event_columns = _columns(connection, "events")
    entity_name = "e.name" if "name" in entity_columns else "NULL"
    entity_summary = "e.summary" if "summary" in entity_columns else "NULL"
    event_description = "ev.description" if "description" in event_columns else "NULL"
    rows = connection.execute(
        f"""SELECT ev.entity_id,
                       {event_description} AS event_description,
                       {entity_summary} AS entity_summary,
                       {entity_name} AS entity_name
                  FROM events AS ev LEFT JOIN entities AS e ON e.entity_id=ev.entity_id
                 ORDER BY ev.entity_id"""
    ).fetchall()
    matches = 0
    mismatches: list[str] = []
    for row in rows:
        content = str(
            row["event_description"]
            or row["entity_summary"]
            or row["entity_name"]
            or ""
        ).strip()
        if not content:
            continue
        target = store.connection.execute(
            "SELECT content_sha256 FROM episodes WHERE episode_id=?",
            (row["entity_id"],),
        ).fetchone()
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        target_meta = (
            json_object(
                store.connection.execute(
                    "SELECT metadata_json FROM episodes WHERE episode_id=?",
                    (row["entity_id"],),
                ).fetchone()[0]
            )
            if target is not None
            else {}
        )
        if target is not None and target_meta.get("legacy_content_sha256") == digest:
            matches += 1
        else:
            mismatches.append(str(row["entity_id"]))
    return matches, tuple(mismatches)


def _report_unresolved_notes(
    connection: sqlite3.Connection,
    warnings: list[str],
) -> None:
    if "memory_notes" not in _tables(connection):
        return
    linked = (
        {
            str(row[0])
            for row in connection.execute(
                "SELECT target_id FROM source_evidence_links WHERE target_type='note'"
            ).fetchall()
        }
        if "source_evidence_links" in _tables(connection)
        else set()
    )
    for row in connection.execute("SELECT note_id FROM memory_notes"):
        note_id = str(row[0])
        if note_id not in linked:
            warnings.append(f"note {note_id}: no durable source reference")


def _database_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with sqlite3.connect(str(path)) as connection:
        connection.row_factory = sqlite3.Row
        for table in sorted(_tables(connection)):
            digest.update(table.encode("utf-8"))
            columns = [
                str(row[1])
                for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
            ]
            digest.update(json.dumps(columns, sort_keys=True).encode("utf-8"))
            for row in connection.execute(
                f"SELECT * FROM {table} ORDER BY rowid"
            ).fetchall():
                digest.update(repr(tuple(row)).encode("utf-8"))
    return digest.hexdigest()


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(row[1])
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }


__all__ = ["MigrationReport", "import_legacy_database"]
