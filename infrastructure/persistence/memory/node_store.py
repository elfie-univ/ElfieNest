"""Compatibility operations for the semantic Memory Port.

The Brain still exposes ``MemoryNode`` for older callers. This mixin maps that
API onto the target Episode and graph fact tables; it deliberately does not
create a second entity/edge store or hide relationships in JSON.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Mapping

from elfie.brain.memory.memory_records import ClosedEpisode, NodeInput
from elfie.brain.memory.node_types import Edge, JsonValue, MemoryMetadata, MemoryNode

from .sqlite_mixin_base import SQLiteMemoryMixinBase
from .sqlite_utils import (
    bounded_score,
    canonical_json,
    content_hash,
    json_list,
    json_object,
    normalize_text,
    normalized_tokens,
    utc_now,
)


class KnowledgeNodeStoreMixin(SQLiteMemoryMixinBase):
    """Map the historical ``MemoryNode`` API to the target fact model."""

    conn: sqlite3.Connection

    def add_node(self, node: MemoryNode) -> str:
        if not node.content.strip():
            raise ValueError("memory node content must not be blank")
        if node.type == "episodic":
            return self._add_episode_node(node)
        properties = dict(node.metadata)
        properties.setdefault("memory_node_type", node.type)
        self.upsert_node_record(
            NodeInput(
                node_id=node.id,
                node_type=node.type,
                canonical_label=node.content,
                description=node.content,
                status="forgotten" if properties.get("forgotten") is True else "active",
                confidence=bounded_score(properties.get("confidence", 0.5)),
                properties=properties,
            )
        )
        return node.id

    def get_node(self, node_id: str) -> MemoryNode | None:
        with self._lock:
            episode_scope = ""
            episode_params: list[object] = [node_id]
            if getattr(self, "elfie_id", None) is not None:
                episode_scope = " AND json_extract(e.metadata_json, '$.elfie_id')=?"
                episode_params.append(str(self.elfie_id))
            episode_visibility, episode_visibility_params = self._genesis_visibility(
                "e"
            )
            episode_params.extend(episode_visibility_params)
            episode = self.conn.execute(
                "SELECT e.* FROM episodes AS e WHERE e.episode_id=?"
                + episode_scope
                + " AND "
                + episode_visibility,
                episode_params,
            ).fetchone()
            if episode is not None:
                return self._episode_row_to_node(episode)
            node_visibility, node_visibility_params = self._genesis_visibility("n")
            node_scope = ""
            node_scope_params: list[object] = []
            if getattr(self, "elfie_id", None) is not None:
                node_scope = " AND json_extract(n.properties_json, '$.elfie_id')=?"
                node_scope_params.append(str(self.elfie_id))
            row = self.conn.execute(
                "SELECT n.* FROM nodes AS n WHERE n.node_id=?"
                + node_scope
                + " AND "
                + node_visibility,
                [node_id, *node_scope_params, *node_visibility_params],
            ).fetchone()
        if row is None:
            return None
        metadata = MemoryMetadata(json_object(row["properties_json"]))
        metadata.setdefault("importance", float(row["importance"]))
        metadata.setdefault("confidence", float(row["confidence"]))
        metadata.setdefault("memory_node_type", str(row["node_type"]))
        return MemoryNode(
            id=str(row["node_id"]),
            type=str(row["node_type"]),
            content=str(row["description"] or row["canonical_label"]),
            metadata=metadata,
            edges=self.get_edges(str(row["node_id"]), direction="outgoing"),
            created_at=row["first_seen_at"],
            updated_at=row["updated_at"],
        )

    def update_node(
        self,
        node_id: str,
        *,
        content: str | None = None,
        metadata: Mapping[str, JsonValue] | MemoryMetadata | None = None,
        edges: list[Edge] | None = None,
    ) -> bool:
        with self._lock:
            episode_scope = ""
            episode_params: list[object] = [node_id]
            if getattr(self, "elfie_id", None) is not None:
                episode_scope = " AND json_extract(e.metadata_json, '$.elfie_id')=?"
                episode_params.append(str(self.elfie_id))
            episode_visibility, episode_visibility_params = self._genesis_visibility(
                "e"
            )
            episode_params.extend(episode_visibility_params)
            episode = self.conn.execute(
                "SELECT e.* FROM episodes AS e WHERE e.episode_id=?"
                + episode_scope
                + " AND "
                + episode_visibility,
                episode_params,
            ).fetchone()
            if episode is not None:
                owns = self._begin_write_transaction()
                try:
                    current = json_object(episode["metadata_json"])
                    if metadata:
                        current.update(dict(metadata))
                    text = (
                        content if content is not None else str(episode["content_text"])
                    )
                    digest = content_hash(text)
                    cursor = self.conn.execute(
                        """UPDATE episodes SET content_text=?, content_sha256=?,
                               metadata_json=?, updated_at=?, projection_revision=NULL,
                               projection_source_sha256=NULL WHERE episode_id=?"""
                        + (
                            " AND json_extract(metadata_json, '$.elfie_id')=?"
                            if getattr(self, "elfie_id", None) is not None
                            else ""
                        ),
                        (
                            text,
                            digest,
                            canonical_json(current),
                            utc_now(),
                            node_id,
                            *(
                                (str(self.elfie_id),)
                                if getattr(self, "elfie_id", None) is not None
                                else ()
                            ),
                        ),
                    )
                    self._upsert_episode_fts_from_values(
                        node_id, text, episode["summary_text"]
                    )
                    changed = cursor.rowcount > 0
                    self._commit_write_transaction(owns)
                except Exception:
                    self._rollback_write_transaction(owns)
                    raise
            else:
                node_visibility, node_visibility_params = self._genesis_visibility("n")
                node_scope = ""
                node_scope_params: list[object] = []
                if getattr(self, "elfie_id", None) is not None:
                    node_scope = " AND json_extract(n.properties_json, '$.elfie_id')=?"
                    node_scope_params.append(str(self.elfie_id))
                row = self.conn.execute(
                    "SELECT n.* FROM nodes AS n WHERE n.node_id=?"
                    + node_scope
                    + " AND "
                    + node_visibility,
                    [node_id, *node_scope_params, *node_visibility_params],
                ).fetchone()
                if row is None:
                    changed = False
                else:
                    owns = self._begin_write_transaction()
                    try:
                        properties = json_object(row["properties_json"])
                        if metadata:
                            properties.update(dict(metadata))
                        label = (
                            content
                            if content is not None
                            else str(row["canonical_label"])
                        )
                        now = utc_now()
                        cursor = self.conn.execute(
                            """UPDATE nodes SET canonical_label=?, normalized_label=?,
                                   description=?, properties_json=?, updated_at=?
                               WHERE node_id=?"""
                            + (
                                " AND json_extract(properties_json, '$.elfie_id')=?"
                                if getattr(self, "elfie_id", None) is not None
                                else ""
                            ),
                            (
                                label,
                                normalize_text(label),
                                content if content is not None else row["description"],
                                canonical_json(properties),
                                now,
                                node_id,
                                *(
                                    (str(self.elfie_id),)
                                    if getattr(self, "elfie_id", None) is not None
                                    else ()
                                ),
                            ),
                        )
                        self.conn.execute(
                            """INSERT INTO nodes_fts(node_id, searchable_text) VALUES (?, ?)
                               ON CONFLICT(node_id) DO UPDATE SET searchable_text=excluded.searchable_text""",
                            (
                                node_id,
                                "\n".join(
                                    value
                                    for value in (label, row["description"] or "")
                                    if value
                                ),
                            ),
                        )
                        changed = cursor.rowcount > 0
                        self._commit_write_transaction(owns)
                    except Exception:
                        self._rollback_write_transaction(owns)
                        raise

        if edges is not None and changed:
            for edge in edges:
                self.add_edge(node_id, edge.target, edge.rel, edge.weight)
        return changed

    def delete_node(self, node_id: str) -> bool:
        with self._lock:
            episode_scope = ""
            episode_params: list[object] = [node_id]
            if getattr(self, "elfie_id", None) is not None:
                episode_scope = " AND json_extract(e.metadata_json, '$.elfie_id')=?"
                episode_params.append(str(self.elfie_id))
            episode_visibility, episode_visibility_params = self._genesis_visibility(
                "e"
            )
            episode_params.extend(episode_visibility_params)
            episode = self.conn.execute(
                "SELECT e.episode_id FROM episodes AS e WHERE e.episode_id=?"
                + episode_scope
                + " AND "
                + episode_visibility,
                episode_params,
            ).fetchone()
            if episode is not None:
                owns = self._begin_write_transaction()
                try:
                    digest_row = self.conn.execute(
                        "SELECT content_sha256 FROM episodes WHERE episode_id=?",
                        (node_id,),
                    ).fetchone()
                    forgotten_text = (
                        f"[forgotten:{digest_row['content_sha256']}]"
                        if digest_row is not None
                        else "[forgotten]"
                    )
                    cursor = self.conn.execute(
                        """UPDATE episodes SET lifecycle='forgotten', detail_level='digest',
                               content_text=?, summary_text=NULL, updated_at=?
                           WHERE episode_id=?"""
                        + (
                            " AND json_extract(metadata_json, '$.elfie_id')=?"
                            if getattr(self, "elfie_id", None) is not None
                            else ""
                        ),
                        (
                            forgotten_text,
                            utc_now(),
                            node_id,
                            *(
                                (str(self.elfie_id),)
                                if getattr(self, "elfie_id", None) is not None
                                else ()
                            ),
                        ),
                    )
                    self._upsert_episode_fts_from_values(node_id, forgotten_text, None)
                    self._commit_write_transaction(owns)
                except Exception:
                    self._rollback_write_transaction(owns)
                    raise
            else:
                node_visibility, node_visibility_params = self._genesis_visibility("n")
                owns = self._begin_write_transaction()
                try:
                    cursor = self.conn.execute(
                        "UPDATE nodes SET status='forgotten', updated_at=? WHERE node_id=? AND "
                        + node_visibility,
                        [utc_now(), node_id, *node_visibility_params],
                    )
                    self._commit_write_transaction(owns)
                except Exception:
                    self._rollback_write_transaction(owns)
                    raise
        return cursor.rowcount > 0

    def get_nodes_by_type(self, node_type: str, limit: int = 100) -> list[MemoryNode]:
        if limit < 1:
            return []
        if node_type == "episodic":
            with self._lock:
                scope = ""
                episode_params: list[object] = [limit]
                if getattr(self, "elfie_id", None) is not None:
                    scope = " AND json_extract(e.metadata_json, '$.elfie_id')=?"
                    episode_params = [str(self.elfie_id), limit]
                visibility, visibility_params = self._genesis_visibility("e")
                episode_params[-1:-1] = visibility_params
                rows = self.conn.execute(
                    """SELECT e.* FROM episodes AS e WHERE e.lifecycle <> 'forgotten'
                       """
                    + scope
                    + " AND "
                    + visibility
                    + " ORDER BY e.occurred_from IS NULL, e.occurred_from, e.episode_id LIMIT ?",
                    episode_params,
                ).fetchall()
            return [self._episode_row_to_node(row) for row in rows]
        with self._lock:
            scope = ""
            params: list[object] = [node_type, node_type]
            if getattr(self, "elfie_id", None) is not None:
                scope = " AND json_extract(n.properties_json, '$.elfie_id')=?"
                params.append(str(self.elfie_id))
            visibility, visibility_params = self._genesis_visibility("n")
            params.extend(visibility_params)
            params.append(limit)
            rows = self.conn.execute(
                """SELECT n.* FROM nodes AS n WHERE (n.node_type=? OR json_extract(n.properties_json, '$.entity_type')=? )
                                      AND n.status <> 'forgotten' AND n.merged_into IS NULL
                   """
                + scope
                + " AND "
                + visibility
                + " ORDER BY n.node_id LIMIT ?",
                params,
            ).fetchall()
        return [
            MemoryNode(
                id=str(row["node_id"]),
                type=str(row["node_type"]),
                content=str(row["description"] or row["canonical_label"]),
                metadata=MemoryMetadata(json_object(row["properties_json"])),
                edges=self.get_edges(str(row["node_id"]), direction="outgoing"),
                created_at=row["first_seen_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def get_unconsolidated_nodes(self, node_type: str = "episodic") -> list[MemoryNode]:
        if node_type != "episodic":
            return []
        with self._lock:
            scope = ""
            params: list[object] = []
            if getattr(self, "elfie_id", None) is not None:
                scope = " AND json_extract(e.metadata_json, '$.elfie_id')=?"
                params.append(str(self.elfie_id))
            visibility, visibility_params = self._genesis_visibility("e")
            params.extend(visibility_params)
            rows = self.conn.execute(
                """SELECT e.* FROM episodes AS e
                   WHERE e.lifecycle='active'
                     AND e.consolidation_state IN ('pending', 'failed')
                     AND (e.projection_revision IS NULL OR e.projection_source_sha256 IS NULL
                          OR e.projection_source_sha256 <> e.content_sha256)
                   """
                + scope
                + " AND "
                + visibility
                + " ORDER BY e.occurred_from IS NULL, e.occurred_from, e.episode_id",
                params,
            ).fetchall()
        return [self._episode_row_to_node(row) for row in rows]

    def count_nodes(self, node_type: str | None = None) -> int:
        with self._lock:
            if node_type == "episodic":
                scope = ""
                episode_count_params: list[object] = []
                if getattr(self, "elfie_id", None) is not None:
                    scope = " AND json_extract(metadata_json, '$.elfie_id')=?"
                    episode_count_params.append(str(self.elfie_id))
                visibility, visibility_params = self._genesis_visibility("episodes")
                episode_count_params.extend(visibility_params)
                row = self.conn.execute(
                    "SELECT COUNT(*) FROM episodes WHERE lifecycle <> 'forgotten'"
                    + scope
                    + " AND "
                    + visibility,
                    episode_count_params,
                ).fetchone()
            elif node_type is None:
                scope_episode = ""
                scope_node = ""
                all_count_params: list[object] = []
                if getattr(self, "elfie_id", None) is not None:
                    scope_episode = " AND json_extract(metadata_json, '$.elfie_id')=?"
                    scope_node = " AND json_extract(properties_json, '$.elfie_id')=?"
                    all_count_params.extend([str(self.elfie_id), str(self.elfie_id)])
                episode_visibility, episode_visibility_params = (
                    self._genesis_visibility("episodes")
                )
                node_visibility, node_visibility_params = self._genesis_visibility(
                    "nodes"
                )
                all_count_params = [
                    *all_count_params[:1],
                    *episode_visibility_params,
                    *all_count_params[1:2],
                    *node_visibility_params,
                ]
                row = self.conn.execute(
                    "SELECT (SELECT COUNT(*) FROM episodes WHERE lifecycle <> 'forgotten'"
                    + scope_episode
                    + " AND "
                    + episode_visibility
                    + ") + (SELECT COUNT(*) FROM nodes WHERE status <> 'forgotten'"
                    + scope_node
                    + " AND "
                    + node_visibility
                    + ")",
                    all_count_params,
                ).fetchone()
            else:
                scope = ""
                typed_count_params: list[object] = [node_type, node_type]
                if getattr(self, "elfie_id", None) is not None:
                    scope = " AND json_extract(n.properties_json, '$.elfie_id')=?"
                    typed_count_params.append(str(self.elfie_id))
                visibility, visibility_params = self._genesis_visibility("n")
                typed_count_params.extend(visibility_params)
                row = self.conn.execute(
                    """SELECT COUNT(*) FROM nodes AS n
                        WHERE (n.node_type=? OR json_extract(n.properties_json, '$.entity_type')=? )
                          AND n.status <> 'forgotten' AND n.merged_into IS NULL"""
                    + scope
                    + " AND "
                    + visibility,
                    typed_count_params,
                ).fetchone()
        return int(row[0])

    def search_by_content(
        self,
        query: str,
        top_k: int = 5,
        node_type: str | None = None,
        *,
        privacy_scope: str | None = None,
    ) -> list[tuple[str, float]]:
        """Deterministic lexical search over Episode text and graph labels."""
        if top_k < 1 or not query.strip():
            return []
        terms = list(dict.fromkeys(normalized_tokens(query)))
        if not terms:
            return []
        like_patterns = _lexical_like_patterns(query, terms)
        # The text tables are rebuildable projections, not a second semantic
        # authority.  Bound the prefilter before the deterministic scorer so
        # a common token cannot turn Recall into a full scan of every Episode
        # and Node.  The generous cap keeps normal small stores exact while
        # making the large-store path obey the Recall latency budget.
        candidate_limit = max(512, min(4096, top_k * 64))
        candidates: list[tuple[str, str, str, str]] = []
        with self._lock:
            if node_type in (None, "episodic"):
                episode_scope = ""
                episode_params: list[object] = list(like_patterns)
                if getattr(self, "elfie_id", None) is not None:
                    episode_scope = " AND json_extract(e.metadata_json, '$.elfie_id')=?"
                    episode_params.append(str(self.elfie_id))
                if privacy_scope is not None:
                    episode_scope += " AND e.privacy_scope=?"
                    episode_params.append(privacy_scope)
                episode_visibility, episode_visibility_params = (
                    self._genesis_visibility("e")
                )
                episode_params.extend(episode_visibility_params)
                episode_where = " OR ".join(
                    "f.searchable_text LIKE ?" for _ in like_patterns
                )
                rows = self.conn.execute(
                    """SELECT e.episode_id, f.searchable_text, 'episodic' AS node_type
                       FROM episodes_fts AS f JOIN episodes AS e USING (episode_id)
                       WHERE e.lifecycle <> 'forgotten' AND ("""
                    + episode_where
                    + ")"
                    + episode_scope
                    + " AND "
                    + episode_visibility
                    + " LIMIT ?",
                    episode_params + [candidate_limit],
                ).fetchall()
                candidates.extend(
                    (str(row[0]), str(row[1]), str(row[2]), str(row[1])) for row in rows
                )
            if node_type is None or node_type != "episodic":
                node_scope = ""
                node_params: list[object] = list(like_patterns)
                if getattr(self, "elfie_id", None) is not None:
                    node_scope = " AND json_extract(n.properties_json, '$.elfie_id')=?"
                    node_params.append(str(self.elfie_id))
                if privacy_scope is not None:
                    node_scope += " AND n.privacy_scope=?"
                    node_params.append(privacy_scope)
                node_visibility, node_visibility_params = self._genesis_visibility("n")
                node_params.extend(node_visibility_params)
                node_where = " OR ".join(
                    "f.searchable_text LIKE ?" for _ in like_patterns
                )
                rows = self.conn.execute(
                    """SELECT f.node_id, f.searchable_text, n.node_type,
                                      n.canonical_label,
                                      json_extract(n.properties_json, '$.entity_type') AS entity_type
                       FROM nodes_fts AS f JOIN nodes AS n USING (node_id)
                       WHERE n.status <> 'forgotten' AND n.merged_into IS NULL
                         AND ("""
                    + node_where
                    + ")"
                    + node_scope
                    + " AND "
                    + node_visibility
                    + " LIMIT ?",
                    node_params + [candidate_limit],
                ).fetchall()
                candidates.extend(
                    (str(row[0]), str(row[1]), str(row[2]), str(row[3] or ""))
                    for row in rows
                    if node_type is None
                    or str(row[2]) == node_type
                    or str(row[3] or "") == node_type
                )
        scored: dict[str, float] = {}
        # Keep lexical matching tolerant of punctuation (for example a user
        # may search ``rare-term`` while the source stored ``rare term``),
        # without changing the stricter normalization used for identity keys.
        query_normalized = _lexical_normalize(query)
        with self._lock:
            alias_visibility, alias_visibility_params = self._genesis_visibility("n")
            alias_scope_params = (
                [str(self.elfie_id)]
                if getattr(self, "elfie_id", None) is not None
                else []
            )
            alias_privacy_params = [privacy_scope] if privacy_scope is not None else []
            exact_alias_ids = {
                str(row[0])
                for row in self.conn.execute(
                    """SELECT DISTINCT a.node_id
                         FROM node_aliases AS a
                         JOIN nodes AS n ON n.node_id=a.node_id
                        WHERE a.normalized_alias=?
                          AND n.status <> 'forgotten'
                          AND n.merged_into IS NULL
                          AND """
                    + alias_visibility
                    + (
                        " AND json_extract(n.properties_json, '$.elfie_id')=?"
                        if getattr(self, "elfie_id", None) is not None
                        else ""
                    )
                    + (" AND n.privacy_scope=?" if privacy_scope is not None else ""),
                    [
                        normalize_text(query),
                        *alias_visibility_params,
                        *alias_scope_params,
                        *alias_privacy_params,
                    ],
                ).fetchall()
            }
        for identifier, text, kind, canonical_label in candidates:
            normalized = _lexical_normalize(text)
            if not normalized:
                continue
            hits = sum(1 for term in terms if term in normalized)
            if hits == 0:
                continue
            score = hits / max(1, len(terms))
            if query_normalized in normalized:
                score += 0.5
            # Exact aliases are stronger evidence than an incidental mention
            # buried in an Episode or a long description.  Keep a small
            # canonical-label density bonus so a direct knowledge label stays
            # in the bounded seed set when a short place term matches many
            # unrelated Episodes.
            if identifier in exact_alias_ids:
                score += 0.35
            label_normalized = _lexical_normalize(canonical_label)
            if query_normalized and query_normalized in label_normalized:
                score += min(
                    0.2,
                    len(query_normalized) / max(1, len(label_normalized)) * 0.2,
                )
            if kind == "knowledge":
                score += 0.05
            scored[identifier] = max(scored.get(identifier, 0.0), score)
        return sorted(scored.items(), key=lambda item: (-item[1], item[0]))[:top_k]

    def _add_episode_node(self, node: MemoryNode) -> str:
        metadata = dict(node.metadata)
        raw_intensity = metadata.get(
            "emotion_intensity", metadata.get("intensity", 0.0)
        )
        intensity = _as_unit_interval(raw_intensity)
        importance = _as_unit_interval(
            metadata.get(
                "importance", intensity / 100.0 if intensity > 1 else intensity
            )
        )
        raw_occurred = metadata.get("timestamp") or node.created_at
        occurred = None if raw_occurred is None else str(raw_occurred)
        source_event_ids = tuple(
            str(value) for value in _list(metadata.get("source_event_ids"))
        )
        episode = ClosedEpisode(
            episode_id=node.id,
            idempotency_key=str(
                metadata.get("idempotency_key") or f"legacy-node:{node.id}"
            ),
            occurred_from=occurred,
            occurrence_precision="exact" if occurred is not None else "unknown",
            content_text=node.content,
            event_kind=str(metadata.get("event_kind") or "interaction"),
            source_event_ids=source_event_ids,
            importance=importance,
            emotion=str(metadata.get("emotion"))
            if metadata.get("emotion") is not None
            else None,
            # The compatibility API historically accepted a 0-100 intensity,
            # while the source-first Episode contract stores a unit interval.
            # Keep the legacy metadata intact, but pass the normalized value
            # into the validated durable record.
            emotion_intensity=intensity
            if isinstance(raw_intensity, (int, float))
            else None,
            stimulus=str(metadata.get("stimulus"))
            if metadata.get("stimulus") is not None
            else None,
            sensory=tuple(
                (str(key), str(value))
                for key, value in _mapping(metadata.get("sensory")).items()
            ),
            metadata=metadata,
        )
        return self.record_episode(episode).episode_id

    def _episode_row_to_node(self, row: sqlite3.Row) -> MemoryNode:
        metadata = MemoryMetadata(json_object(row["metadata_json"]))
        metadata["timestamp"] = (
            None if row["occurred_from"] is None else str(row["occurred_from"])
        )
        metadata["importance"] = float(row["importance"])
        metadata["consolidated"] = str(row["consolidation_state"]) == "consolidated"
        metadata["detail_level"] = str(row["detail_level"])
        metadata["lifecycle"] = str(row["lifecycle"])
        metadata["source_event_ids"] = _list(json_list(row["source_event_ids_json"]))
        return MemoryNode(
            id=str(row["episode_id"]),
            type="episodic",
            content=str(row["content_text"]),
            metadata=metadata,
            edges=self.get_edges(str(row["episode_id"]), direction="outgoing"),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def _upsert_episode_fts_from_values(
        self, episode_id: str, content: str, summary: str | None
    ) -> None:
        self.conn.execute(
            """INSERT INTO episodes_fts(episode_id, searchable_text) VALUES (?, ?)
               ON CONFLICT(episode_id) DO UPDATE SET searchable_text=excluded.searchable_text""",
            (
                episode_id,
                "\n".join(value for value in (content, summary or "") if value),
            ),
        )


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _list(value: object) -> list[JsonValue]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _as_unit_interval(value: object) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    if number > 1.0:
        number /= 100.0
    return max(0.0, min(1.0, number))


def _lexical_normalize(value: str) -> str:
    """Normalize searchable text without weakening semantic identity rules."""
    cleaned = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9\s]", "", value.casefold())
    return " ".join(cleaned.split())


def _lexical_like_patterns(query: str, terms: list[str]) -> list[str]:
    """Build SQL prefilters while retaining the deterministic Python scorer."""
    patterns = [f"%{term}%" for term in terms]
    ascii_parts = re.findall(r"[a-z0-9]+", query.casefold())
    if len(ascii_parts) > 1:
        patterns.append("%" + "%".join(ascii_parts) + "%")
    return list(dict.fromkeys(patterns))


__all__ = ["KnowledgeNodeStoreMixin"]
