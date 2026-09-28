"""Single-product-root SQLite registry for additive Memory ontology entries."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Mapping

from elfie.brain.memory.ontology import (
    EpisodeTypeSpec,
    MemoryOntologyError,
    MemoryOntologySnapshot,
    NodeTypeSpec,
    OntologyStatus,
    PredicateSpec,
)
from elfie.brain.memory.ontology_registry import OntologyEntryKind
from infrastructure.persistence.memory.ontology_loader import (
    parse_memory_ontology_document,
)
from infrastructure.persistence.nest_db.sqlite_connection import (
    UnsafeSQLitePathError,
    connect_app_sqlite,
)

_SCHEMA_VERSION = 1
_TABLES = frozenset({"ontology_registry_meta", "ontology_extensions"})
_STATUSES = frozenset({"candidate", "active", "deprecated"})


class MemoryOntologyRegistrySchemaError(RuntimeError):
    """An ontology registry database is unknown, partial, or unsupported."""


class SQLiteMemoryOntologyRegistryAdapter:
    """Persist controlled vocabulary extensions shared under one data root."""

    def __init__(
        self,
        db_path: str | Path,
        core_document: Mapping[str, Any],
    ) -> None:
        self._db_path = Path(db_path)
        if self._db_path.name != "ontology.sqlite":
            raise ValueError(f"ontology registry requires ontology.sqlite: {db_path}")
        self._core_document = dict(core_document)
        self._lock = RLock()
        try:
            self.conn = connect_app_sqlite(self._db_path, check_same_thread=False)
        except UnsafeSQLitePathError as error:
            raise MemoryOntologyRegistrySchemaError(str(error)) from error
        try:
            self._initialize_schema()
        except Exception:
            self.conn.close()
            raise

    def __enter__(self) -> SQLiteMemoryOntologyRegistryAdapter:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self.conn.close()

    @property
    def revision(self) -> int:
        row = self.conn.execute(
            "SELECT revision FROM ontology_registry_meta WHERE singleton=1"
        ).fetchone()
        if row is None:
            raise MemoryOntologyRegistrySchemaError(
                f"ontology registry metadata is missing: {self._db_path}"
            )
        return int(row[0])

    def snapshot(self) -> MemoryOntologySnapshot:
        with self._lock:
            return self._snapshot_for_rows(self._read_extensions(), self.revision)

    def propose_node_type(self, spec: NodeTypeSpec) -> int:
        if spec.core or spec.status != "candidate":
            raise MemoryOntologyError(
                "a proposed node type must be a non-core candidate"
            )
        return self._propose(
            "node_type",
            spec.node_type,
            {
                "id": spec.node_type,
                "label": spec.label,
                "group": spec.group_id,
                "color": spec.color,
            },
        )

    def propose_episode_type(self, spec: EpisodeTypeSpec) -> int:
        if spec.core or spec.status != "candidate":
            raise MemoryOntologyError(
                "a proposed Episode type must be a non-core candidate"
            )
        return self._propose(
            "episode_type",
            spec.event_kind,
            {"id": spec.event_kind, "label": spec.label},
        )

    def propose_predicate(self, spec: PredicateSpec) -> int:
        if spec.core or spec.status != "candidate":
            raise MemoryOntologyError(
                "a proposed predicate must be a non-core candidate"
            )
        return self._propose("predicate", spec.predicate, _predicate_definition(spec))

    def set_extension_status(
        self,
        kind: OntologyEntryKind,
        key: str,
        status: OntologyStatus,
    ) -> int:
        if status not in _STATUSES:
            raise MemoryOntologyError(
                f"unsupported ontology extension status: {status}"
            )
        normalized_kind = _validate_kind(kind)
        normalized_key = key.strip().casefold().replace("-", "_")
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                row = self.conn.execute(
                    "SELECT status FROM ontology_extensions WHERE kind=? AND entry_key=?",
                    (normalized_kind, normalized_key),
                ).fetchone()
                if row is None:
                    raise MemoryOntologyError(
                        f"unknown ontology extension: {normalized_kind}/{normalized_key}"
                    )
                current = str(row["status"])
                if current == status:
                    self.conn.commit()
                    return self.revision
                allowed = {
                    "candidate": {"active", "deprecated"},
                    "active": {"deprecated"},
                    "deprecated": set(),
                }
                if status not in allowed[current]:
                    raise MemoryOntologyError(
                        f"invalid ontology extension transition: {current} -> {status}"
                    )
                next_revision = self.revision + 1
                rows = self._read_extensions()
                updated = tuple(
                    (
                        entry_kind,
                        entry_key,
                        status
                        if (entry_kind, entry_key) == (normalized_kind, normalized_key)
                        else entry_status,
                        definition,
                    )
                    for entry_kind, entry_key, entry_status, definition in rows
                )
                self._snapshot_for_rows(updated, next_revision)
                self.conn.execute(
                    "UPDATE ontology_extensions SET status=?, updated_at=? "
                    "WHERE kind=? AND entry_key=?",
                    (status, _utc_now(), normalized_kind, normalized_key),
                )
                self.conn.execute(
                    "UPDATE ontology_registry_meta SET revision=? WHERE singleton=1",
                    (next_revision,),
                )
                self.conn.commit()
                return next_revision
            except Exception:
                self.conn.rollback()
                raise

    def _propose(
        self, kind: OntologyEntryKind, key: str, definition: Mapping[str, Any]
    ) -> int:
        normalized_kind = _validate_kind(kind)
        normalized_key = key.strip().casefold().replace("-", "_")
        payload = json.dumps(
            dict(definition), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                if (
                    self.conn.execute(
                        "SELECT 1 FROM ontology_extensions WHERE kind=? AND entry_key=?",
                        (normalized_kind, normalized_key),
                    ).fetchone()
                    is not None
                ):
                    raise MemoryOntologyError(
                        f"ontology extension already exists: {normalized_kind}/{normalized_key}"
                    )
                current_rows = self._read_extensions()
                candidate_definition = json.loads(payload)
                next_revision = self.revision + 1
                proposed = (
                    *current_rows,
                    (
                        normalized_kind,
                        normalized_key,
                        "candidate",
                        candidate_definition,
                    ),
                )
                self._snapshot_for_rows(proposed, next_revision)
                self.conn.execute(
                    "INSERT INTO ontology_extensions"
                    "(kind, entry_key, status, definition_json, created_at, updated_at) "
                    "VALUES (?, ?, 'candidate', ?, ?, ?)",
                    (
                        normalized_kind,
                        normalized_key,
                        payload,
                        _utc_now(),
                        _utc_now(),
                    ),
                )
                self.conn.execute(
                    "UPDATE ontology_registry_meta SET revision=? WHERE singleton=1",
                    (next_revision,),
                )
                self.conn.commit()
                return next_revision
            except Exception:
                self.conn.rollback()
                raise

    def _read_extensions(
        self,
    ) -> tuple[tuple[str, str, OntologyStatus, Mapping[str, Any]], ...]:
        rows = self.conn.execute(
            "SELECT kind, entry_key, status, definition_json "
            "FROM ontology_extensions ORDER BY kind, entry_key"
        ).fetchall()
        result: list[tuple[str, str, OntologyStatus, Mapping[str, Any]]] = []
        for row in rows:
            try:
                definition = json.loads(str(row["definition_json"]))
            except json.JSONDecodeError as error:
                raise MemoryOntologyRegistrySchemaError(
                    f"invalid ontology extension JSON in {self._db_path}"
                ) from error
            if not isinstance(definition, dict):
                raise MemoryOntologyRegistrySchemaError(
                    f"ontology extension definition must be an object: {self._db_path}"
                )
            status = str(row["status"])
            if status not in _STATUSES:
                raise MemoryOntologyRegistrySchemaError(
                    f"invalid ontology extension status in {self._db_path}"
                )
            result.append(
                (
                    str(row["kind"]),
                    str(row["entry_key"]),
                    status,  # type: ignore[arg-type]
                    definition,
                )
            )
        return tuple(result)

    def _snapshot_for_rows(
        self,
        rows: tuple[tuple[str, str, OntologyStatus, Mapping[str, Any]], ...],
        revision: int,
    ) -> MemoryOntologySnapshot:
        return parse_memory_ontology_document(
            self._core_document,
            registry_revision=revision,
            extensions=rows,
        )

    def _initialize_schema(self) -> None:
        existing = {
            str(row["name"])
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        user_tables = existing - {"sqlite_sequence"}
        version = int(self.conn.execute("PRAGMA user_version").fetchone()[0])
        if version not in (0, _SCHEMA_VERSION):
            raise MemoryOntologyRegistrySchemaError(
                f"unsupported ontology registry schema version {version}: {self._db_path}"
            )
        if version == 0 and user_tables:
            raise MemoryOntologyRegistrySchemaError(
                f"partial ontology registry has no schema version: {self._db_path}"
            )
        if version == _SCHEMA_VERSION and user_tables != _TABLES:
            raise MemoryOntologyRegistrySchemaError(
                f"ontology registry tables do not match schema v{_SCHEMA_VERSION}: {self._db_path}"
            )
        if version == _SCHEMA_VERSION:
            return
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute(
            "CREATE TABLE ontology_registry_meta ("
            "singleton INTEGER PRIMARY KEY CHECK (singleton=1), "
            "revision INTEGER NOT NULL CHECK (revision >= 0))"
        )
        self.conn.execute(
            "CREATE TABLE ontology_extensions ("
            "kind TEXT NOT NULL CHECK (kind IN ('node_type','episode_type','predicate')), "
            "entry_key TEXT NOT NULL CHECK (length(trim(entry_key)) > 0), "
            "status TEXT NOT NULL CHECK (status IN ('candidate','active','deprecated')), "
            "definition_json TEXT NOT NULL CHECK (json_valid(definition_json)), "
            "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
            "PRIMARY KEY(kind, entry_key))"
        )
        self.conn.execute(
            "INSERT INTO ontology_registry_meta(singleton, revision) VALUES (1, 0)"
        )
        self.conn.execute(f"PRAGMA user_version={_SCHEMA_VERSION}")
        self.conn.commit()


def _validate_kind(kind: str) -> OntologyEntryKind:
    if kind not in {"node_type", "episode_type", "predicate"}:
        raise MemoryOntologyError(f"unsupported ontology extension kind: {kind}")
    return kind  # type: ignore[return-value]


def _predicate_definition(spec: PredicateSpec) -> dict[str, Any]:
    return {
        "label": spec.label,
        "subject_groups": list(spec.subject_groups),
        "subject_types": list(spec.subject_types),
        "object_groups": list(spec.object_groups),
        "object_types": list(spec.object_types),
        "object_literal": spec.object_literal,
        "symmetric": spec.symmetric,
        "inverse": spec.inverse,
        "qualifiers": list(spec.qualifiers),
        "source_required": spec.source_required,
        "salience": spec.salience,
        "self_stance": spec.self_stance,
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


__all__ = (
    "MemoryOntologyRegistrySchemaError",
    "SQLiteMemoryOntologyRegistryAdapter",
)
