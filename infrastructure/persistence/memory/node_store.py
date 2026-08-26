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


class KnowledgeNodeStoreMixin:
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
            episode = self.conn.execute(
                "SELECT * FROM episodes WHERE episode_id=?", (node_id,)
            ).fetchone()
            if episode is not None:
                return self._episode_row_to_node(episode)
            row = self.conn.execute(
                "SELECT * FROM nodes WHERE node_id=?", (node_id,)
            ).fetchone()
        if row is None:
            return None
        metadata = MemoryMetadata(json_object(row["properties_json"]))
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
            episode = self.conn.execute(
                "SELECT * FROM episodes WHERE episode_id=?", (node_id,)
            ).fetchone()
            if episode is not None:
                current = json_object(episode["metadata_json"])
                if metadata:
                    current.update(dict(metadata))
                text = content if content is not None else str(episode["content_text"])
                digest = content_hash(text)
                cursor = self.conn.execute(
                    """UPDATE episodes SET content_text=?, content_sha256=?,
                           metadata_json=?, updated_at=? WHERE episode_id=?""",
                    (text, digest, canonical_json(current), utc_now(), node_id),
                )
                self._upsert_episode_fts_from_values(
                    node_id, text, episode["summary_text"]
                )
                self.conn.commit()
                changed = cursor.rowcount > 0
            else:
                row = self.conn.execute(
                    "SELECT * FROM nodes WHERE node_id=?", (node_id,)
                ).fetchone()
                if row is None:
                    changed = False
                else:
                    properties = json_object(row["properties_json"])
                    if metadata:
                        properties.update(dict(metadata))
                    label = (
                        content if content is not None else str(row["canonical_label"])
                    )
                    now = utc_now()
                    cursor = self.conn.execute(
                        """UPDATE nodes SET canonical_label=?, normalized_label=?,
                               description=?, properties_json=?, updated_at=?
                           WHERE node_id=?""",
                        (
                            label,
                            normalize_text(label),
                            content if content is not None else row["description"],
                            canonical_json(properties),
                            now,
                            node_id,
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
                    self.conn.commit()
                    changed = cursor.rowcount > 0
        if edges is not None and changed:
            for edge in edges:
                self.add_edge(node_id, edge.target, edge.rel, edge.weight)
        return changed

    def delete_node(self, node_id: str) -> bool:
        with self._lock:
            episode = self.conn.execute(
                "SELECT episode_id FROM episodes WHERE episode_id=?", (node_id,)
            ).fetchone()
            if episode is not None:
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
                       WHERE episode_id=?""",
                    (forgotten_text, utc_now(), node_id),
                )
                self._upsert_episode_fts_from_values(node_id, forgotten_text, None)
            else:
                cursor = self.conn.execute(
                    "UPDATE nodes SET status='forgotten', updated_at=? WHERE node_id=?",
                    (utc_now(), node_id),
                )
            self.conn.commit()
        return cursor.rowcount > 0

    def get_nodes_by_type(self, node_type: str, limit: int = 100) -> list[MemoryNode]:
        if limit < 1:
            return []
        if node_type == "episodic":
            with self._lock:
                rows = self.conn.execute(
                    """SELECT * FROM episodes WHERE lifecycle <> 'forgotten'
                       ORDER BY occurred_from, episode_id LIMIT ?""",
                    (limit,),
                ).fetchall()
            return [self._episode_row_to_node(row) for row in rows]
        with self._lock:
            rows = self.conn.execute(
                """SELECT * FROM nodes WHERE (node_type=? OR json_extract(properties_json, '$.entity_type')=? )
                                      AND status <> 'forgotten' AND merged_into IS NULL
                   ORDER BY node_id LIMIT ?""",
                (node_type, node_type, limit),
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
            rows = self.conn.execute(
                """SELECT * FROM episodes
                   WHERE lifecycle='active'
                     AND consolidation_state IN ('pending', 'failed')
                   ORDER BY occurred_from, episode_id"""
            ).fetchall()
        return [self._episode_row_to_node(row) for row in rows]

    def count_nodes(self, node_type: str | None = None) -> int:
        with self._lock:
            if node_type == "episodic":
                row = self.conn.execute(
                    "SELECT COUNT(*) FROM episodes WHERE lifecycle <> 'forgotten'"
                ).fetchone()
            elif node_type is None:
                row = self.conn.execute(
                    "SELECT (SELECT COUNT(*) FROM episodes WHERE lifecycle <> 'forgotten') + (SELECT COUNT(*) FROM nodes WHERE status <> 'forgotten')"
                ).fetchone()
            else:
                row = self.conn.execute(
                    """SELECT COUNT(*) FROM nodes
                        WHERE (node_type=? OR json_extract(properties_json, '$.entity_type')=? )
                          AND status <> 'forgotten' AND merged_into IS NULL""",
                    (node_type, node_type),
                ).fetchone()
        return int(row[0])

    def search_by_content(
        self,
        query: str,
        top_k: int = 5,
        node_type: str | None = None,
    ) -> list[tuple[str, float]]:
        """Deterministic lexical search over Episode text and graph labels."""
        if top_k < 1 or not query.strip():
            return []
        terms = list(dict.fromkeys(normalized_tokens(query)))
        if not terms:
            return []
        like_patterns = _lexical_like_patterns(query, terms)
        candidates: list[tuple[str, str, str]] = []
        with self._lock:
            if node_type in (None, "episodic"):
                episode_where = " OR ".join(
                    "f.searchable_text LIKE ?" for _ in like_patterns
                )
                rows = self.conn.execute(
                    """SELECT e.episode_id, f.searchable_text, 'episodic' AS node_type
                       FROM episodes_fts AS f JOIN episodes AS e USING (episode_id)
                       WHERE e.lifecycle <> 'forgotten' AND ("""
                    + episode_where
                    + ")",
                    like_patterns,
                ).fetchall()
                candidates.extend(
                    (str(row[0]), str(row[1]), str(row[2])) for row in rows
                )
            if node_type is None or node_type != "episodic":
                node_where = " OR ".join(
                    "f.searchable_text LIKE ?" for _ in like_patterns
                )
                rows = self.conn.execute(
                    """SELECT f.node_id, f.searchable_text, n.node_type,
                                      json_extract(n.properties_json, '$.entity_type') AS entity_type
                       FROM nodes_fts AS f JOIN nodes AS n USING (node_id)
                       WHERE n.status <> 'forgotten' AND n.merged_into IS NULL
                         AND ("""
                    + node_where
                    + ")",
                    like_patterns,
                ).fetchall()
                candidates.extend(
                    (str(row[0]), str(row[1]), str(row[2]))
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
        for identifier, text, _kind in candidates:
            normalized = _lexical_normalize(text)
            if not normalized:
                continue
            hits = sum(1 for term in terms if term in normalized)
            if hits == 0:
                continue
            score = hits / max(1, len(terms))
            if query_normalized in normalized:
                score += 0.5
            scored[identifier] = max(scored.get(identifier, 0.0), min(1.0, score))
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
        occurred = str(metadata.get("timestamp") or node.created_at or utc_now())
        source_event_ids = tuple(
            str(value) for value in _list(metadata.get("source_event_ids"))
        )
        episode = ClosedEpisode(
            episode_id=node.id,
            idempotency_key=str(
                metadata.get("idempotency_key") or f"legacy-node:{node.id}"
            ),
            occurred_from=occurred,
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
        metadata["timestamp"] = str(row["occurred_from"])
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
