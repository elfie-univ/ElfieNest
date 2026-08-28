"""Graph projection and evidence operations for SQLite Memory."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any, Iterable, Optional

from elfie.brain.memory.memory_records import (
    AliasInput,
    AssertionEvidenceInput,
    AssertionInput,
    ConsolidationProjection,
    ConsolidationReceipt,
    DescriptionInput,
    EvidenceInput,
    MentionInput,
    NodeInput,
    RecallAssertion,
    RecallEvidence,
    RecallNode,
)
from elfie.brain.memory.node_types import Edge

from .sqlite_mixin_base import SQLiteMemoryMixinBase
from .sqlite_utils import (
    bounded_score,
    canonical_json,
    content_hash,
    json_object,
    normalize_text,
    stable_id,
    utc_now,
)

_NON_CANONICAL_NODE_TYPES = frozenset({"event", "episode", "claim"})
_MAX_EPISODE_MENTIONS = 128


class SQLiteGraphStoreMixin(SQLiteMemoryMixinBase):
    conn: sqlite3.Connection

    def apply_consolidation(
        self, projection: ConsolidationProjection
    ) -> ConsolidationReceipt:
        with self._lock:
            episode = self.conn.execute(
                "SELECT episode_id FROM episodes WHERE episode_id=?",
                (projection.episode_id,),
            ).fetchone()
            if episode is None:
                raise ValueError(f"unknown Episode: {projection.episode_id}")
            now = utc_now()
            evidence_by_id: dict[str, EvidenceInput] = {}
            node_id_map: dict[str, str] = {}
            assertion_ids: dict[str, str] = {}
            mentions_truncated = False
            try:
                self.conn.execute("BEGIN IMMEDIATE")
                for evidence in projection.evidence:
                    if (
                        evidence.source_type == "episode"
                        and evidence.source_id != projection.episode_id
                    ):
                        raise ValueError(
                            "Episode evidence must point to the projected Episode"
                        )
                    self._insert_evidence(evidence, now)
                    evidence_by_id[evidence.evidence_id] = evidence
                for node in projection.nodes:
                    node_id_map[node.node_id] = self._resolve_projection_node(node, now)
                for alias in projection.aliases:
                    resolved_node_id = node_id_map.get(alias.node_id)
                    if resolved_node_id is None:
                        resolved_node_id = self._resolve_graph_node_id_locked(
                            alias.node_id
                        )
                    if resolved_node_id is None:
                        raise ValueError(f"unknown node in alias: {alias.node_id}")
                    self._insert_alias(
                        AliasInput(
                            node_id=resolved_node_id,
                            alias=alias.alias,
                            scope=alias.scope,
                            evidence_id=alias.evidence_id,
                            confidence=alias.confidence,
                        ),
                        now,
                    )
                for description in projection.descriptions:
                    resolved_node_id = node_id_map.get(description.node_id)
                    if resolved_node_id is None:
                        resolved_node_id = self._resolve_graph_node_id_locked(
                            description.node_id
                        )
                    if resolved_node_id is None:
                        raise ValueError(
                            f"unknown node in description: {description.node_id}"
                        )
                    self._insert_description(
                        DescriptionInput(
                            node_id=resolved_node_id,
                            text=description.text,
                            language=description.language,
                            kind=description.kind,
                            evidence_id=description.evidence_id,
                            confidence=description.confidence,
                        ),
                        now,
                    )

                existing_mention_keys = {
                    (str(row[0]), row[1], row[2])
                    for row in self.conn.execute(
                        "SELECT surface_text, span_start, span_end FROM episode_mentions WHERE episode_id=?",
                        (projection.episode_id,),
                    ).fetchall()
                }
                for mention in projection.mentions:
                    if mention.episode_id != projection.episode_id:
                        raise ValueError(
                            "projection mentions must belong to the projected Episode"
                        )
                    key = (
                        mention.surface_text.strip(),
                        mention.span_start,
                        mention.span_end,
                    )
                    if (
                        key not in existing_mention_keys
                        and len(existing_mention_keys) >= _MAX_EPISODE_MENTIONS
                    ):
                        mentions_truncated = True
                        continue
                    resolved_node_id = (
                        node_id_map.get(mention.node_id)
                        if mention.node_id is not None
                        else None
                    )
                    if mention.node_id is not None and resolved_node_id is None:
                        resolved_node_id = self._resolve_graph_node_id_locked(
                            mention.node_id
                        )
                    if mention.node_id is not None and resolved_node_id is None:
                        raise ValueError(f"unknown node in mention: {mention.node_id}")
                    self._insert_mention(
                        MentionInput(
                            episode_id=mention.episode_id,
                            surface_text=mention.surface_text,
                            node_id=resolved_node_id,
                            resolution_state=mention.resolution_state,
                            role=mention.role,
                            span_start=mention.span_start,
                            span_end=mention.span_end,
                            confidence=mention.confidence,
                        ),
                        now,
                    )
                    existing_mention_keys.add(key)

                for assertion in projection.assertions:
                    if not assertion.evidence_ids:
                        raise ValueError(
                            "durable assertions require at least one evidence ID"
                        )
                    subject_id = node_id_map.get(assertion.subject_id)
                    if subject_id is None:
                        subject_id = self._resolve_graph_node_id_locked(
                            assertion.subject_id
                        )
                    if subject_id is None:
                        raise ValueError(
                            f"unknown assertion subject: {assertion.subject_id}"
                        )
                    object_node_reference = assertion.object_node_id
                    object_node_id = object_node_reference
                    if object_node_reference is not None:
                        object_node_id = node_id_map.get(object_node_reference)
                        if object_node_id is None:
                            object_node_id = self._resolve_graph_node_id_locked(
                                object_node_reference
                            )
                        if object_node_id is None:
                            raise ValueError(
                                f"unknown assertion object: {assertion.object_node_id}"
                            )
                    normalized_assertion = AssertionInput(
                        subject_id=subject_id,
                        predicate=assertion.predicate,
                        object_node_id=object_node_id,
                        object_literal=assertion.object_literal,
                        object_unit=assertion.object_unit,
                        polarity=assertion.polarity,
                        epistemic_status=assertion.epistemic_status,
                        viewpoint=assertion.viewpoint,
                        context=assertion.context,
                        valid_from=assertion.valid_from,
                        valid_to=assertion.valid_to,
                        confidence=assertion.confidence,
                        support_score=assertion.support_score,
                        conflict_group=assertion.conflict_group,
                        supersedes_assertion_id=assertion.supersedes_assertion_id,
                        evidence_ids=assertion.evidence_ids,
                        assertion_id=assertion.assertion_id,
                    )
                    if (
                        normalized_assertion.context == "correction"
                        and normalized_assertion.supersedes_assertion_id is None
                    ):
                        prior = self._latest_active_claim(
                            subject_id=subject_id,
                            predicate=normalized_assertion.predicate,
                            object_node_id=object_node_id,
                            object_literal=normalized_assertion.object_literal,
                        )
                        if prior is not None:
                            normalized_assertion = AssertionInput(
                                subject_id=normalized_assertion.subject_id,
                                predicate=normalized_assertion.predicate,
                                object_node_id=normalized_assertion.object_node_id,
                                object_literal=normalized_assertion.object_literal,
                                object_unit=normalized_assertion.object_unit,
                                polarity=normalized_assertion.polarity,
                                epistemic_status=normalized_assertion.epistemic_status,
                                viewpoint=normalized_assertion.viewpoint,
                                context=normalized_assertion.context,
                                valid_from=normalized_assertion.valid_from,
                                valid_to=normalized_assertion.valid_to,
                                confidence=normalized_assertion.confidence,
                                support_score=normalized_assertion.support_score,
                                conflict_group=normalized_assertion.conflict_group,
                                supersedes_assertion_id=prior,
                                evidence_ids=normalized_assertion.evidence_ids,
                                assertion_id=normalized_assertion.assertion_id,
                            )
                    assertion_id = self._insert_assertion(normalized_assertion, now)
                    assertion_ids[assertion.assertion_id or assertion_id] = assertion_id
                    superseded_id = normalized_assertion.supersedes_assertion_id
                    if superseded_id is not None:
                        if superseded_id == assertion_id:
                            raise ValueError("an assertion cannot supersede itself")
                        if not self._assertion_exists(superseded_id):
                            raise ValueError(
                                f"unknown superseded assertion: {superseded_id}"
                            )
                        self.conn.execute(
                            "UPDATE assertions SET lifecycle='superseded', updated_at=? WHERE assertion_id=?",
                            (now, superseded_id),
                        )
                    for evidence_id in assertion.evidence_ids:
                        if (
                            evidence_id not in evidence_by_id
                            and not self.conn.execute(
                                "SELECT 1 FROM evidence WHERE evidence_id=?",
                                (evidence_id,),
                            ).fetchone()
                        ):
                            raise ValueError(
                                f"unknown evidence for assertion: {evidence_id}"
                            )
                        self._insert_assertion_evidence(
                            AssertionEvidenceInput(
                                assertion_id=assertion_id,
                                evidence_id=evidence_id,
                            ),
                            assertion_id,
                            now,
                        )

                for link in projection.assertion_evidence:
                    assertion_id = assertion_ids.get(
                        link.assertion_id, link.assertion_id
                    )
                    if not self._assertion_exists(assertion_id):
                        raise ValueError(
                            f"unknown assertion in evidence link: {assertion_id}"
                        )
                    if (
                        link.evidence_id not in evidence_by_id
                        and not self.conn.execute(
                            "SELECT 1 FROM evidence WHERE evidence_id=?",
                            (link.evidence_id,),
                        ).fetchone()
                    ):
                        raise ValueError(
                            f"unknown evidence in assertion link: {link.evidence_id}"
                        )
                    self._insert_assertion_evidence(link, assertion_id, now)

                self.conn.execute(
                    """UPDATE episodes SET consolidation_state='consolidated',
                           lease_owner=NULL, lease_until=NULL, next_attempt_at=NULL,
                           updated_at=? WHERE episode_id=?""",
                    (now, projection.episode_id),
                )
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
        return ConsolidationReceipt(
            episode_id=projection.episode_id,
            status="consolidated",
            nodes_created=len(projection.nodes),
            assertions_created=len(projection.assertions),
            evidence_created=len(projection.evidence),
            mentions_truncated=mentions_truncated,
        )

    def upsert_node_record(self, node: NodeInput) -> str:
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                self._upsert_node(node, utc_now())
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
        return node.node_id

    def merge_graph_nodes(self, source_id: str, target_id: str) -> bool:
        """Merge one identity into another without losing source evidence.

        Mentions are retargeted.  Assertions are either retargeted in place or
        folded into an existing qualified assertion while their evidence links
        remain attached.  The source node itself is retained as a merge
        pointer, so old IDs continue to resolve after a restart.
        """
        if source_id == target_id:
            return False
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                source = self.conn.execute(
                    "SELECT node_id, canonical_label FROM nodes WHERE node_id=?",
                    (source_id,),
                ).fetchone()
                target_root = self._resolve_graph_node_id_locked(target_id)
                source_root = self._resolve_graph_node_id_locked(source_id)
                if source is None or target_root is None or source_root != source_id:
                    self.conn.rollback()
                    return False
                if target_root == source_id:
                    raise ValueError("node merge would create an identity cycle")
                now = utc_now()

                # Keep one canonical target for all historical mentions.
                self.conn.execute(
                    "UPDATE episode_mentions SET node_id=? WHERE node_id=?",
                    (target_root, source_id),
                )

                # Copy the old spelling into the target's aliases before the
                # source is hidden from normal search.
                self._insert_alias(
                    AliasInput(
                        node_id=target_root,
                        alias=str(source["canonical_label"]),
                        confidence=1.0,
                    ),
                    now,
                )

                # Move assertion endpoints.  A qualified duplicate is folded
                # into its canonical row; all evidence links are copied first.
                rows = self.conn.execute(
                    "SELECT * FROM assertions WHERE subject_node_id=? OR object_node_id=?",
                    (source_id, source_id),
                ).fetchall()
                for row in rows:
                    new_subject = (
                        target_root
                        if row["subject_node_id"] == source_id
                        else row["subject_node_id"]
                    )
                    new_object = (
                        target_root
                        if row["object_node_id"] == source_id
                        else row["object_node_id"]
                    )
                    assertion_input = _row_as_assertion_input(
                        row, new_subject, new_object
                    )
                    fingerprint = _assertion_fingerprint(assertion_input)
                    duplicate = self.conn.execute(
                        "SELECT assertion_id FROM assertions WHERE fingerprint=? AND assertion_id<>?",
                        (fingerprint, row["assertion_id"]),
                    ).fetchone()
                    if duplicate is not None:
                        self.conn.execute(
                            """INSERT INTO assertion_evidence(assertion_id, evidence_id, stance, created_at)
                               SELECT ?, evidence_id, stance, ? FROM assertion_evidence
                                WHERE assertion_id=?
                               ON CONFLICT(assertion_id, evidence_id) DO UPDATE SET
                                   stance=CASE
                                       WHEN assertion_evidence.stance=excluded.stance
                                           THEN assertion_evidence.stance
                                       ELSE 'context'
                                   END""",
                            (duplicate["assertion_id"], now, row["assertion_id"]),
                        )
                        self.conn.execute(
                            "UPDATE assertions SET lifecycle='superseded', updated_at=? WHERE assertion_id=?",
                            (now, row["assertion_id"]),
                        )
                    else:
                        self.conn.execute(
                            "UPDATE assertions SET subject_node_id=?, object_node_id=?, fingerprint=?, updated_at=? WHERE assertion_id=?",
                            (
                                new_subject,
                                new_object,
                                fingerprint,
                                now,
                                row["assertion_id"],
                            ),
                        )
                self.conn.execute(
                    "UPDATE nodes SET merged_into=?, updated_at=? WHERE node_id=?",
                    (target_root, now, source_id),
                )
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
        return True

    def resolve_graph_node_id(self, node_id: str) -> str | None:
        """Follow bounded merge pointers without exposing SQL to Brain code."""
        with self._lock:
            return self._resolve_graph_node_id_locked(node_id)

    def _resolve_graph_node_id_locked(self, node_id: str) -> str | None:
        current = node_id
        seen: set[str] = set()
        while current not in seen:
            seen.add(current)
            row = self.conn.execute(
                "SELECT node_id, merged_into FROM nodes WHERE node_id=?",
                (current,),
            ).fetchone()
            if row is None:
                return None
            if row["merged_into"] is None:
                return str(row["node_id"])
            current = str(row["merged_into"])
        return None

    def get_graph_node(self, node_id: str) -> Optional[RecallNode]:
        resolved = self.resolve_graph_node_id(node_id)
        if resolved is None:
            return None
        with self._lock:
            row = self.conn.execute(
                """SELECT node_id, node_type, canonical_label, description,
                          confidence FROM nodes WHERE node_id=?""",
                (resolved,),
            ).fetchone()
        if row is None:
            return None
        return RecallNode(
            node_id=str(row["node_id"]),
            node_type=str(row["node_type"]),
            label=str(row["canonical_label"]),
            description=row["description"],
            relevance=float(row["confidence"]),
        )

    def list_graph_nodes(self, limit: int = 100) -> tuple[RecallNode, ...]:
        with self._lock:
            rows = self.conn.execute(
                """SELECT node_id, node_type, canonical_label, description,
                          confidence FROM nodes WHERE status <> 'forgotten'
                                              AND merged_into IS NULL
                   ORDER BY node_id LIMIT ?""",
                (max(0, limit),),
            ).fetchall()
        return tuple(
            RecallNode(
                node_id=str(row["node_id"]),
                node_type=str(row["node_type"]),
                label=str(row["canonical_label"]),
                description=row["description"],
                relevance=float(row["confidence"]),
            )
            for row in rows
        )

    def find_graph_nodes(self, query: str, limit: int = 20) -> tuple[RecallNode, ...]:
        normalized = normalize_text(query)
        if not normalized:
            return ()
        like = f"%{normalized}%"
        with self._lock:
            rows = self.conn.execute(
                """SELECT DISTINCT n.node_id, n.node_type, n.canonical_label,
                          n.description, n.confidence,
                          CASE WHEN n.normalized_label=? OR a.normalized_alias=? THEN 1.0
                               WHEN n.normalized_label LIKE ? THEN 0.8
                               WHEN a.normalized_alias LIKE ? THEN 0.75
                               ELSE 0.5 END AS score
                     FROM nodes AS n LEFT JOIN node_aliases AS a ON a.node_id=n.node_id
                    WHERE n.status <> 'forgotten' AND n.merged_into IS NULL
                      AND (n.normalized_label LIKE ? OR a.normalized_alias LIKE ?
                           OR lower(COALESCE(n.description,'')) LIKE ?)
                    ORDER BY score DESC, n.node_id LIMIT ?""",
                (normalized, normalized, like, like, like, like, like, max(0, limit)),
            ).fetchall()
        return tuple(
            RecallNode(
                node_id=str(row["node_id"]),
                node_type=str(row["node_type"]),
                label=str(row["canonical_label"]),
                description=row["description"],
                relevance=float(row["score"]),
            )
            for row in rows
        )

    def graph_assertions_for(
        self,
        node_ids: Iterable[str],
        *,
        relation_types: Iterable[str] = (),
        limit: int = 80,
        occurred_from: str | None = None,
        occurred_to: str | None = None,
    ) -> tuple[RecallAssertion, ...]:
        ids = tuple(
            dict.fromkeys(
                resolved
                for node_id in node_ids
                if (resolved := self.resolve_graph_node_id(node_id)) is not None
            )
        )
        if not ids or limit < 1:
            return ()
        placeholders = ",".join("?" for _ in ids)
        relations = tuple(dict.fromkeys(relation_types))
        relation_clause = ""
        params: list[Any] = list(ids) + list(ids)
        if relations:
            relation_clause = (
                " AND a.predicate IN (" + ",".join("?" for _ in relations) + ")"
            )
            params.extend(relations)
        time_clause = ""
        if occurred_from is not None or occurred_to is not None:
            episode_conditions = ["p.lifecycle <> 'forgotten'"]
            time_params: list[Any] = []
            if occurred_from is not None:
                episode_conditions.append("p.occurred_from >= ?")
                time_params.append(occurred_from)
            if occurred_to is not None:
                episode_conditions.append("p.occurred_from <= ?")
                time_params.append(occurred_to)
            time_clause = (
                " AND EXISTS (SELECT 1 FROM assertion_evidence AS ae_time "
                "JOIN evidence AS e ON e.evidence_id=ae_time.evidence_id "
                "LEFT JOIN episodes AS p ON p.episode_id=e.source_id "
                "WHERE ae_time.assertion_id=a.assertion_id AND ("
                + "e.source_type <> 'episode' OR ("
                + " AND ".join(episode_conditions)
                + ")))"
            )
            params.extend(time_params)
        params.append(limit)
        with self._lock:
            rows = self.conn.execute(
                f"""SELECT a.*,
                           COALESCE((SELECT group_concat(evidence_id, ',')
                                       FROM (SELECT ae.evidence_id
                                               FROM assertion_evidence AS ae
                                              WHERE ae.assertion_id=a.assertion_id
                                              ORDER BY ae.evidence_id)), '')
                               AS evidence_ids_csv
                         FROM assertions AS a
                    WHERE a.lifecycle='active'
                      AND (a.subject_node_id IN ({placeholders})
                           OR a.object_node_id IN ({placeholders}))
                      {relation_clause}
                      {time_clause}
                    ORDER BY a.support_score DESC, a.assertion_id LIMIT ?""",
                params,
            ).fetchall()
        return tuple(_row_to_assertion(row) for row in rows)

    def get_assertion_evidence(
        self, assertion_ids: Iterable[str], limit: int = 24
    ) -> tuple[RecallEvidence, ...]:
        ids = tuple(dict.fromkeys(assertion_ids))
        if not ids or limit < 1:
            return ()
        placeholders = ",".join("?" for _ in ids)
        with self._lock:
            rows = self.conn.execute(
                f"""SELECT e.evidence_id, e.source_id, e.excerpt, e.media_locator,
                           CASE
                               WHEN SUM(CASE WHEN ae.stance='supports' THEN 1 ELSE 0 END) > 0
                                AND SUM(CASE WHEN ae.stance='contradicts' THEN 1 ELSE 0 END) > 0
                                   THEN 'context'
                               WHEN SUM(CASE WHEN ae.stance='supports' THEN 1 ELSE 0 END) > 0
                                   THEN 'supports'
                               WHEN SUM(CASE WHEN ae.stance='contradicts' THEN 1 ELSE 0 END) > 0
                                   THEN 'contradicts'
                               ELSE 'context'
                           END AS stance
                      FROM evidence AS e
                      JOIN assertion_evidence AS ae ON ae.evidence_id=e.evidence_id
                     WHERE ae.assertion_id IN ({placeholders})
                     GROUP BY e.evidence_id, e.source_id, e.excerpt, e.media_locator
                     ORDER BY e.evidence_id LIMIT ?""",
                list(ids) + [max(0, limit)],
            ).fetchall()
        unique: dict[str, RecallEvidence] = {}
        for row in rows:
            evidence_id = str(row["evidence_id"])
            unique.setdefault(
                evidence_id,
                RecallEvidence(
                    evidence_id=evidence_id,
                    source_id=str(row["source_id"]),
                    excerpt=row["excerpt"],
                    media_locator=row["media_locator"],
                    stance=str(row["stance"]),
                ),
            )
        return tuple(unique.values())

    def get_evidence(self, evidence_id: str) -> Optional[RecallEvidence]:
        with self._lock:
            row = self.conn.execute(
                """SELECT e.evidence_id, e.source_id, e.excerpt, e.media_locator,
                          CASE
                              WHEN SUM(CASE WHEN ae.stance='supports' THEN 1 ELSE 0 END) > 0
                               AND SUM(CASE WHEN ae.stance='contradicts' THEN 1 ELSE 0 END) > 0
                                  THEN 'context'
                              WHEN SUM(CASE WHEN ae.stance='supports' THEN 1 ELSE 0 END) > 0
                                   THEN 'supports'
                              WHEN SUM(CASE WHEN ae.stance='contradicts' THEN 1 ELSE 0 END) > 0
                                  THEN 'contradicts'
                              WHEN COUNT(ae.stance) > 0 THEN 'context'
                              ELSE 'supports'
                          END AS stance
                     FROM evidence AS e LEFT JOIN assertion_evidence AS ae
                       ON ae.evidence_id=e.evidence_id
                    WHERE e.evidence_id=?
                    GROUP BY e.evidence_id, e.source_id, e.excerpt, e.media_locator""",
                (evidence_id,),
            ).fetchone()
        if row is None:
            return None
        return RecallEvidence(
            evidence_id=str(row["evidence_id"]),
            source_id=str(row["source_id"]),
            excerpt=row["excerpt"],
            media_locator=row["media_locator"],
            stance=str(row["stance"]),
        )

    def get_assertion_evidence_for_ids(
        self, evidence_ids: Iterable[str]
    ) -> tuple[RecallEvidence, ...]:
        ids = tuple(dict.fromkeys(evidence_ids))
        if not ids:
            return ()
        placeholders = ",".join("?" for _ in ids)
        with self._lock:
            rows = self.conn.execute(
                f"""SELECT e.evidence_id, e.source_id, e.excerpt, e.media_locator,
                          CASE
                              WHEN SUM(CASE WHEN ae.stance='supports' THEN 1 ELSE 0 END) > 0
                               AND SUM(CASE WHEN ae.stance='contradicts' THEN 1 ELSE 0 END) > 0
                                  THEN 'context'
                              WHEN SUM(CASE WHEN ae.stance='supports' THEN 1 ELSE 0 END) > 0
                                   THEN 'supports'
                               WHEN SUM(CASE WHEN ae.stance='contradicts' THEN 1 ELSE 0 END) > 0
                                   THEN 'contradicts'
                               WHEN COUNT(ae.stance) > 0 THEN 'context'
                               ELSE 'supports'
                           END AS stance
                      FROM evidence AS e LEFT JOIN assertion_evidence AS ae
                        ON ae.evidence_id=e.evidence_id
                     WHERE e.evidence_id IN ({placeholders})
                     GROUP BY e.evidence_id, e.source_id, e.excerpt, e.media_locator
                     ORDER BY e.evidence_id""",
                list(ids),
            ).fetchall()
        return tuple(
            RecallEvidence(
                evidence_id=str(row["evidence_id"]),
                source_id=str(row["source_id"]),
                excerpt=row["excerpt"],
                media_locator=row["media_locator"],
                stance=str(row["stance"]),
            )
            for row in rows
        )

    def get_edges(self, node_id: str, direction: str = "outgoing") -> list[Edge]:
        resolved_node_id = self.resolve_graph_node_id(node_id) or node_id
        clauses = ""
        params: list[Any] = [resolved_node_id]
        if direction == "incoming":
            clauses = "a.object_node_id=?"
        elif direction == "outgoing":
            clauses = "a.subject_node_id=?"
        else:
            clauses = "(a.subject_node_id=? OR a.object_node_id=?)"
            params.append(resolved_node_id)
        with self._lock:
            rows = self.conn.execute(
                f"""SELECT a.subject_node_id, a.object_node_id, a.predicate,
                           a.support_score FROM assertions AS a
                    WHERE a.lifecycle='active' AND {clauses}
                    ORDER BY a.assertion_id""",
                params,
            ).fetchall()
        return [
            Edge(
                target=(
                    str(row["subject_node_id"])
                    if direction == "incoming"
                    else str(row["object_node_id"])
                    if direction == "outgoing"
                    else str(
                        row["object_node_id"]
                        if str(row["subject_node_id"]) == resolved_node_id
                        else row["subject_node_id"]
                    )
                ),
                rel=str(row["predicate"]),
                weight=float(row["support_score"]),
            )
            for row in rows
            if row["object_node_id"] is not None
        ]

    def add_edge(
        self, source_id: str, target_id: str, rel: str, weight: float = 0.5
    ) -> str:
        now = utc_now()
        evidence_id = (
            "legacy-edge:"
            + hashlib.sha256(f"{source_id}|{target_id}|{rel}".encode()).hexdigest()[:24]
        )
        assertion = AssertionInput(
            subject_id=source_id,
            predicate=str(rel),
            object_node_id=target_id,
            confidence=bounded_score(weight),
            support_score=bounded_score(weight),
            evidence_ids=(evidence_id,),
        )
        evidence = EvidenceInput(
            evidence_id=evidence_id,
            source_type="legacy",
            source_id=evidence_id,
            excerpt=f"legacy edge {source_id} {rel} {target_id}",
        )
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                self._ensure_compat_node(source_id, now)
                self._ensure_compat_node(target_id, now)
                self._insert_evidence(evidence, now)
                assertion_id = self._insert_assertion(assertion, now)
                self._insert_assertion_evidence(
                    AssertionEvidenceInput(
                        assertion_id=assertion_id, evidence_id=evidence_id
                    ),
                    assertion_id,
                    now,
                )
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
        return assertion_id

    def record_sourced_assertion(
        self,
        assertion: AssertionInput,
        evidence: EvidenceInput,
        *,
        stance: str = "supports",
    ) -> str:
        """Write one already-qualified assertion for import/seed adapters."""
        if evidence.evidence_id not in assertion.evidence_ids:
            assertion = AssertionInput(
                subject_id=assertion.subject_id,
                predicate=assertion.predicate,
                object_node_id=assertion.object_node_id,
                object_literal=assertion.object_literal,
                object_unit=assertion.object_unit,
                polarity=assertion.polarity,
                epistemic_status=assertion.epistemic_status,
                viewpoint=assertion.viewpoint,
                context=assertion.context,
                valid_from=assertion.valid_from,
                valid_to=assertion.valid_to,
                confidence=assertion.confidence,
                support_score=assertion.support_score,
                conflict_group=assertion.conflict_group,
                evidence_ids=tuple(assertion.evidence_ids) + (evidence.evidence_id,),
                assertion_id=assertion.assertion_id,
            )
        with self._lock:
            now = utc_now()
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                self._ensure_compat_node(assertion.subject_id, now)
                if assertion.object_node_id is not None:
                    self._ensure_compat_node(assertion.object_node_id, now)
                self._insert_evidence(evidence, now)
                assertion_id = self._insert_assertion(assertion, now)
                self._insert_assertion_evidence(
                    AssertionEvidenceInput(
                        assertion_id=assertion_id,
                        evidence_id=evidence.evidence_id,
                        stance=stance,  # type: ignore[arg-type]
                    ),
                    assertion_id,
                    now,
                )
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
        return assertion_id

    def _resolve_projection_node(self, node: NodeInput, now: str) -> str:
        """Resolve a proposed semantic node to one canonical identity.

        Event/claim nodes are intentionally episode-scoped and are never
        merged by label.  Reusable semantic anchors are matched by canonical
        label or an unambiguous alias within the same type and scope.  An
        ambiguous surface creates the proposed candidate instead of silently
        choosing one existing identity.
        """
        requested = self._resolve_graph_node_id_locked(node.node_id)
        if requested is not None:
            existing = self.conn.execute(
                "SELECT node_type, normalized_label, scope, properties_json FROM nodes WHERE node_id=?",
                (requested,),
            ).fetchone()
            if existing is None:
                raise ValueError(f"resolved node disappeared: {requested}")
            if (
                str(existing["node_type"]) != node.node_type
                or str(existing["scope"]) != node.scope
                or str(existing["normalized_label"])
                != normalize_text(node.canonical_label)
            ):
                properties = json_object(existing["properties_json"])
                if not properties.get("compat_placeholder"):
                    raise ValueError(
                        f"node ID is already bound to another identity: {node.node_id}"
                    )
            self._upsert_node(
                NodeInput(
                    node_id=requested,
                    node_type=node.node_type,
                    canonical_label=node.canonical_label,
                    description=node.description,
                    scope=node.scope,
                    status=node.status,
                    confidence=node.confidence,
                    properties={
                        key: value
                        for key, value in node.properties.items()
                        if key != "compat_placeholder"
                    },
                ),
                now,
            )
            return requested

        normalized = normalize_text(node.canonical_label)
        if node.node_type not in _NON_CANONICAL_NODE_TYPES:
            rows = self.conn.execute(
                """SELECT node_id FROM nodes
                   WHERE normalized_label=? AND node_type=? AND scope=?
                     AND status <> 'forgotten' AND merged_into IS NULL
                   ORDER BY node_id LIMIT 2""",
                (normalized, node.node_type, node.scope),
            ).fetchall()
            alias_rows = self.conn.execute(
                """SELECT DISTINCT n.node_id FROM node_aliases AS a
                   JOIN nodes AS n ON n.node_id=a.node_id
                  WHERE a.normalized_alias=? AND a.scope=?
                    AND n.node_type=? AND n.status <> 'forgotten'
                    AND n.merged_into IS NULL
                  ORDER BY n.node_id LIMIT 2""",
                (normalized, node.scope, node.node_type),
            ).fetchall()
            candidates = {str(row[0]) for row in rows}
            candidates.update(str(row[0]) for row in alias_rows)
            if len(candidates) == 1:
                resolved = next(iter(candidates))
                existing = self.conn.execute(
                    "SELECT canonical_label FROM nodes WHERE node_id=?", (resolved,)
                ).fetchone()
                canonical_label = (
                    str(existing["canonical_label"])
                    if existing is not None
                    else node.canonical_label
                )
                self._upsert_node(
                    NodeInput(
                        node_id=resolved,
                        node_type=node.node_type,
                        canonical_label=canonical_label,
                        description=node.description,
                        scope=node.scope,
                        status=node.status,
                        confidence=node.confidence,
                        properties=node.properties,
                    ),
                    now,
                )
                return resolved

        self._upsert_node(node, now)
        return node.node_id

    def _upsert_node(self, node: NodeInput, now: str) -> None:
        label = node.canonical_label.strip()
        if not label:
            raise ValueError("node label must not be blank")
        existing = self.conn.execute(
            "SELECT node_type, normalized_label, scope, properties_json, description, first_seen_at FROM nodes WHERE node_id=?",
            (node.node_id,),
        ).fetchone()
        if existing is not None and (
            str(existing["node_type"]) != node.node_type
            or str(existing["normalized_label"]) != normalize_text(label)
            or str(existing["scope"]) != node.scope
        ):
            existing_properties = json_object(existing["properties_json"])
            if not existing_properties.get("compat_placeholder"):
                raise ValueError(
                    f"node ID is already bound to another identity: {node.node_id}"
                )
        properties = json_object(existing["properties_json"]) if existing else {}
        properties.pop("compat_placeholder", None)
        properties.update(dict(node.properties))
        description = node.description
        if description is None and existing is not None:
            description = existing["description"]
        first_seen = (
            existing["first_seen_at"]
            if existing is not None and existing["first_seen_at"]
            else now
        )
        self.conn.execute(
            """INSERT INTO nodes (
                   node_id, node_type, canonical_label, normalized_label,
                   description, scope, status, confidence, properties_json,
                   first_seen_at, last_seen_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(node_id) DO UPDATE SET
                   node_type=excluded.node_type,
                   canonical_label=excluded.canonical_label,
                   normalized_label=excluded.normalized_label,
                   description=COALESCE(excluded.description, nodes.description),
                   scope=excluded.scope,
                   status=excluded.status,
                   confidence=MAX(nodes.confidence, excluded.confidence),
                   properties_json=excluded.properties_json,
                   last_seen_at=excluded.last_seen_at,
                   updated_at=excluded.updated_at""",
            (
                node.node_id,
                node.node_type,
                label,
                normalize_text(label),
                description,
                node.scope,
                node.status,
                bounded_score(node.confidence),
                canonical_json(properties),
                first_seen,
                now,
                now,
            ),
        )
        self.conn.execute(
            """INSERT INTO nodes_fts(node_id, searchable_text) VALUES (?, ?)
               ON CONFLICT(node_id) DO UPDATE SET searchable_text=excluded.searchable_text""",
            (
                node.node_id,
                "\n".join(value for value in (label, description or "") if value),
            ),
        )

    def _insert_alias(self, alias: AliasInput, now: str) -> None:
        self.conn.execute(
            """INSERT INTO node_aliases (
                   alias_id, node_id, alias, normalized_alias, scope,
                   evidence_id, confidence, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(node_id, normalized_alias, scope) DO UPDATE SET
                   evidence_id=COALESCE(excluded.evidence_id, node_aliases.evidence_id),
                   confidence=MAX(node_aliases.confidence, excluded.confidence)""",
            (
                stable_id(
                    "alias:",
                    alias.node_id,
                    normalize_text(alias.alias),
                    alias.scope,
                    length=24,
                ),
                alias.node_id,
                alias.alias.strip(),
                normalize_text(alias.alias),
                alias.scope,
                alias.evidence_id,
                bounded_score(alias.confidence),
                now,
            ),
        )
        self._refresh_node_text_projection(alias.node_id)

    def _insert_description(self, description: DescriptionInput, now: str) -> None:
        digest = content_hash(description.text)
        self.conn.execute(
            """INSERT OR IGNORE INTO node_descriptions (
                   description_id, node_id, text, language, kind,
                   content_sha256, evidence_id, confidence, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "description:"
                + hashlib.sha256(
                    f"{description.node_id}|{description.language}|{description.kind}|{digest}".encode()
                ).hexdigest()[:24],
                description.node_id,
                description.text.strip(),
                description.language,
                description.kind,
                digest,
                description.evidence_id,
                bounded_score(description.confidence),
                now,
            ),
        )
        self._refresh_node_text_projection(description.node_id)

    def _insert_mention(self, mention: MentionInput, now: str) -> None:
        # SQLite treats NULLs as distinct in a UNIQUE constraint.  Resolve the
        # nullable span explicitly so replaying the same semantic mention is
        # idempotent even when no character offsets were extracted.
        existing = self.conn.execute(
            """SELECT mention_id FROM episode_mentions
                WHERE episode_id=? AND surface_text=?
                  AND ((span_start=? ) OR (span_start IS NULL AND ? IS NULL))
                  AND ((span_end=? ) OR (span_end IS NULL AND ? IS NULL))""",
            (
                mention.episode_id,
                mention.surface_text.strip(),
                mention.span_start,
                mention.span_start,
                mention.span_end,
                mention.span_end,
            ),
        ).fetchone()
        mention_id = (
            str(existing["mention_id"])
            if existing is not None
            else stable_id(
                "mention:",
                mention.episode_id,
                normalize_text(mention.surface_text),
                mention.span_start,
                mention.span_end,
                length=32,
            )
        )
        self.conn.execute(
            """INSERT INTO episode_mentions (
                   mention_id, episode_id, node_id, resolution_state, role,
                   surface_text, span_start, span_end, confidence, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(episode_id, surface_text, span_start, span_end)
               DO UPDATE SET node_id=COALESCE(excluded.node_id, episode_mentions.node_id),
                   resolution_state=excluded.resolution_state,
                   confidence=MAX(episode_mentions.confidence, excluded.confidence)""",
            (
                mention_id,
                mention.episode_id,
                mention.node_id,
                mention.resolution_state,
                mention.role,
                mention.surface_text.strip(),
                mention.span_start,
                mention.span_end,
                bounded_score(mention.confidence),
                now,
            ),
        )

    def _insert_evidence(self, evidence: EvidenceInput, now: str) -> None:
        if (
            evidence.source_type == "episode"
            and not self.conn.execute(
                "SELECT 1 FROM episodes WHERE episode_id=?", (evidence.source_id,)
            ).fetchone()
        ):
            raise ValueError(
                f"Episode evidence points to an unknown source: {evidence.source_id}"
            )
        existing = self.conn.execute(
            """SELECT source_type, source_id, excerpt, media_locator, modality,
                              span_start, span_end, speaker, viewpoint,
                              captured_at, extraction_run_id, source_sha256
                         FROM evidence WHERE evidence_id=?""",
            (evidence.evidence_id,),
        ).fetchone()
        if existing is not None and (
            str(existing["source_type"]) != evidence.source_type
            or str(existing["source_id"]) != evidence.source_id
            or existing["excerpt"] != evidence.excerpt
            or existing["media_locator"] != evidence.media_locator
            or str(existing["modality"]) != evidence.modality
            or existing["span_start"] != evidence.span_start
            or existing["span_end"] != evidence.span_end
            or existing["speaker"] != evidence.speaker
            or existing["viewpoint"] != evidence.viewpoint
            or existing["captured_at"] != evidence.captured_at
            or existing["extraction_run_id"] != evidence.extraction_run_id
            or existing["source_sha256"] != evidence.source_sha256
        ):
            raise ValueError(
                f"evidence ID is already bound to different source data: {evidence.evidence_id}"
            )
        self.conn.execute(
            """INSERT OR IGNORE INTO evidence (
                   evidence_id, source_type, source_id, excerpt, media_locator,
                   modality, span_start, span_end, speaker, viewpoint,
                   captured_at, extraction_run_id, source_sha256, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                evidence.evidence_id,
                evidence.source_type,
                evidence.source_id,
                evidence.excerpt,
                evidence.media_locator,
                evidence.modality,
                evidence.span_start,
                evidence.span_end,
                evidence.speaker,
                evidence.viewpoint,
                evidence.captured_at,
                evidence.extraction_run_id,
                evidence.source_sha256,
                now,
            ),
        )

    def _refresh_all_text_projections(self) -> None:
        """Rebuild node search text inside an existing write transaction."""
        for row in self.conn.execute("SELECT node_id FROM nodes").fetchall():
            self._refresh_node_text_projection(str(row[0]))

    def _refresh_node_text_projection(self, node_id: str) -> None:
        row = self.conn.execute(
            "SELECT canonical_label, description FROM nodes WHERE node_id=?",
            (node_id,),
        ).fetchone()
        if row is None:
            return
        values = [str(row["canonical_label"])]
        if row["description"]:
            values.append(str(row["description"]))
        values.extend(
            str(item[0])
            for item in self.conn.execute(
                "SELECT alias FROM node_aliases WHERE node_id=? ORDER BY alias_id",
                (node_id,),
            ).fetchall()
        )
        values.extend(
            str(item[0])
            for item in self.conn.execute(
                "SELECT text FROM node_descriptions WHERE node_id=? ORDER BY description_id",
                (node_id,),
            ).fetchall()
        )
        self.conn.execute(
            """INSERT INTO nodes_fts(node_id, searchable_text) VALUES (?, ?)
               ON CONFLICT(node_id) DO UPDATE SET searchable_text=excluded.searchable_text""",
            (node_id, "\n".join(value for value in values if value)),
        )

    def _insert_assertion(self, assertion: AssertionInput, now: str) -> str:
        fingerprint = _assertion_fingerprint(assertion)
        assertion_id = assertion.assertion_id or "assertion:" + fingerprint[:24]
        existing_by_id = self.conn.execute(
            "SELECT fingerprint FROM assertions WHERE assertion_id=?", (assertion_id,)
        ).fetchone()
        if (
            existing_by_id is not None
            and str(existing_by_id["fingerprint"]) != fingerprint
        ):
            raise ValueError(
                f"assertion ID is already bound to a different claim: {assertion_id}"
            )
        base = _assertion_base(assertion)
        conflict_group = (
            assertion.conflict_group
            or "conflict:" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]
        )
        literal = (
            None
            if assertion.object_literal is None
            else canonical_json(assertion.object_literal)
        )
        self.conn.execute(
            """INSERT INTO assertions (
                   assertion_id, subject_node_id, predicate, object_node_id,
                   object_literal_json, object_unit, polarity, epistemic_status,
                   viewpoint, context, valid_from, valid_to, confidence,
                   support_score, conflict_group, fingerprint, lifecycle,
                   supersedes_assertion_id, created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
               ON CONFLICT(fingerprint) DO UPDATE SET
                   confidence=MAX(assertions.confidence, excluded.confidence),
                   support_score=MAX(assertions.support_score, excluded.support_score),
                   updated_at=excluded.updated_at""",
            (
                assertion_id,
                assertion.subject_id,
                assertion.predicate,
                assertion.object_node_id,
                literal,
                assertion.object_unit,
                assertion.polarity,
                assertion.epistemic_status,
                assertion.viewpoint,
                assertion.context,
                assertion.valid_from,
                assertion.valid_to,
                bounded_score(assertion.confidence),
                bounded_score(assertion.support_score),
                conflict_group,
                fingerprint,
                assertion.supersedes_assertion_id,
                now,
                now,
            ),
        )
        row = self.conn.execute(
            "SELECT assertion_id FROM assertions WHERE fingerprint=?", (fingerprint,)
        ).fetchone()
        if row is None:
            raise RuntimeError("assertion write did not return an ID")
        return str(row["assertion_id"])

    def _insert_assertion_evidence(
        self, link: AssertionEvidenceInput, assertion_id: str, now: str
    ) -> None:
        self.conn.execute(
            """INSERT INTO assertion_evidence (
                   assertion_id, evidence_id, stance, created_at
               ) VALUES (?, ?, ?, ?)
               ON CONFLICT(assertion_id, evidence_id) DO UPDATE SET
                   stance=CASE
                       WHEN assertion_evidence.stance=excluded.stance
                           THEN assertion_evidence.stance
                       ELSE 'context'
                   END""",
            (assertion_id, link.evidence_id, link.stance, now),
        )

    def _assertion_exists(self, assertion_id: str) -> bool:
        return (
            self.conn.execute(
                "SELECT 1 FROM assertions WHERE assertion_id=?", (assertion_id,)
            ).fetchone()
            is not None
        )

    def _latest_active_claim(
        self,
        *,
        subject_id: str,
        predicate: str,
        object_node_id: str | None,
        object_literal: object | None,
    ) -> str | None:
        """Find a prior value for an explicit correction, never a conflict."""
        rows = self.conn.execute(
            """SELECT assertion_id, object_node_id, object_literal_json
                 FROM assertions
                WHERE subject_node_id=? AND predicate=? AND lifecycle='active'
                ORDER BY updated_at DESC, assertion_id DESC""",
            (subject_id, predicate),
        ).fetchall()
        desired_literal = (
            None if object_literal is None else canonical_json(object_literal)
        )
        for row in rows:
            if (
                row["object_node_id"] == object_node_id
                and row["object_literal_json"] == desired_literal
            ):
                continue
            return str(row["assertion_id"])
        return None

    def _ensure_compat_node(self, node_id: str, now: str) -> None:
        self.conn.execute(
            """INSERT OR IGNORE INTO nodes (
                   node_id, node_type, canonical_label, normalized_label,
                   confidence, properties_json, first_seen_at, last_seen_at, updated_at
               ) VALUES (?, 'entity', ?, ?, 0.5, ?, ?, ?, ?)""",
            (
                node_id,
                node_id,
                normalize_text(node_id),
                canonical_json({"compat_placeholder": True}),
                now,
                now,
                now,
            ),
        )


def _assertion_base(assertion: AssertionInput) -> str:
    object_value = (
        f"node:{assertion.object_node_id}"
        if assertion.object_node_id is not None
        else f"literal:{canonical_json(assertion.object_literal)}"
    )
    return "|".join((assertion.subject_id, assertion.predicate, object_value))


def _assertion_fingerprint(assertion: AssertionInput) -> str:
    payload = {
        "base": _assertion_base(assertion),
        "object_unit": assertion.object_unit,
        "polarity": assertion.polarity,
        "epistemic_status": assertion.epistemic_status,
        "viewpoint": assertion.viewpoint,
        "context": assertion.context,
        "valid_from": assertion.valid_from,
        "valid_to": assertion.valid_to,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _row_as_assertion_input(
    row: sqlite3.Row,
    subject_id: str,
    object_node_id: str | None,
) -> AssertionInput:
    literal = None
    if row["object_literal_json"] is not None:
        literal = json.loads(str(row["object_literal_json"]))
    # Evidence is copied separately during a merge; this object only exists to
    # recompute the qualified assertion fingerprint after changing endpoints.
    return AssertionInput(
        subject_id=str(subject_id),
        predicate=str(row["predicate"]),
        object_node_id=object_node_id,
        object_literal=literal,
        object_unit=row["object_unit"],
        polarity=str(row["polarity"]),  # type: ignore[arg-type]
        epistemic_status=str(row["epistemic_status"]),  # type: ignore[arg-type]
        viewpoint=row["viewpoint"],
        context=row["context"],
        valid_from=row["valid_from"],
        valid_to=row["valid_to"],
        confidence=bounded_score(row["confidence"]),
        support_score=bounded_score(row["support_score"]),
        conflict_group=row["conflict_group"],
        supersedes_assertion_id=row["supersedes_assertion_id"],
    )


def _row_to_assertion(row: sqlite3.Row) -> RecallAssertion:
    literal = None
    if row["object_literal_json"] is not None:
        literal = json.loads(row["object_literal_json"])
    qualifiers = {
        key: row[key]
        for key in (
            "object_unit",
            "viewpoint",
            "context",
            "valid_from",
            "valid_to",
            "polarity",
            "epistemic_status",
            "conflict_group",
            "supersedes_assertion_id",
        )
        if row[key] is not None
    }
    evidence_ids = tuple(
        value for value in str(row["evidence_ids_csv"] or "").split(",") if value
    )
    return RecallAssertion(
        assertion_id=str(row["assertion_id"]),
        subject_id=str(row["subject_node_id"]),
        predicate=str(row["predicate"]),
        object_node_id=(
            None if row["object_node_id"] is None else str(row["object_node_id"])
        ),
        object_literal=literal,
        qualifiers=qualifiers,
        status=str(row["lifecycle"]),
        evidence_ids=evidence_ids,
        relevance=float(row["support_score"]),
    )


__all__ = ["SQLiteGraphStoreMixin"]
