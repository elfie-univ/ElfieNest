"""Graph projection and evidence operations for SQLite Memory."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import replace
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
from elfie.brain.memory.predicates import (
    PREDICATE_REGISTRY_VERSION,
    UnknownPredicateError,
    resolve_predicate,
)
from elfie.brain.memory.score_policy import EvidenceStance, MemoryScorePolicy

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
            episode_visibility, episode_visibility_params = self._genesis_visibility(
                "e"
            )
            episode_scope = ""
            episode_scope_params: list[object] = []
            if getattr(self, "elfie_id", None) is not None:
                episode_scope = " AND json_extract(e.metadata_json, '$.elfie_id')=?"
                episode_scope_params.append(str(self.elfie_id))
            episode = self.conn.execute(
                "SELECT e.episode_id, e.content_sha256, e.source_version, "
                "e.projection_revision, e.projection_source_sha256 "
                "FROM episodes AS e WHERE e.episode_id=? AND "
                + episode_visibility
                + episode_scope,
                [
                    projection.episode_id,
                    *episode_visibility_params,
                    *episode_scope_params,
                ],
            ).fetchone()
            if episode is None:
                raise ValueError(f"unknown Episode: {projection.episode_id}")
            expected_hash = projection.source_sha256 or str(episode["content_sha256"])
            if expected_hash != str(episode["content_sha256"]):
                raise ValueError("projection source hash is stale")
            if (
                projection.source_version is not None
                and projection.source_version != episode["source_version"]
            ):
                raise ValueError("projection source version is stale")
            # Bind omitted provenance fields to the current source so a
            # first attempt and a retry that supplies the explicit hash/version
            # resolve to the same deterministic projection revision.
            projection = replace(
                projection,
                source_version=(
                    projection.source_version
                    if projection.source_version is not None
                    else episode["source_version"]
                ),
                source_sha256=expected_hash,
            )
            computed_revision = _projection_revision(projection)
            if (
                projection.projection_revision is not None
                and projection.projection_revision != computed_revision
            ):
                raise ValueError(
                    "projection_revision does not match projection content"
                )
            projection_revision = computed_revision
            if (
                episode["projection_revision"] == projection_revision
                and episode["projection_source_sha256"] == expected_hash
            ):
                return ConsolidationReceipt(
                    episode_id=projection.episode_id,
                    status="duplicate",
                )
            now = utc_now()
            evidence_by_id: dict[str, EvidenceInput] = {}
            node_id_map: dict[str, str] = {}
            assertion_ids: dict[str, str] = {}
            mentions_truncated = False
            owns = self._begin_write_transaction()
            try:
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
                    try:
                        canonical_predicate = resolve_predicate(assertion.predicate)
                    except UnknownPredicateError:
                        raise
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
                        predicate=canonical_predicate,
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
                        importance=assertion.importance,
                        object_literal_type=assertion.object_literal_type,
                        predicate_registry_version=PREDICATE_REGISTRY_VERSION,
                        policy_version=assertion.policy_version,
                        genesis_submission_id=assertion.genesis_submission_id,
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
                            object_literal_type=normalized_assertion.object_literal_type,
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
                                importance=normalized_assertion.importance,
                                object_literal_type=normalized_assertion.object_literal_type,
                                predicate_registry_version=normalized_assertion.predicate_registry_version,
                                policy_version=normalized_assertion.policy_version,
                                genesis_submission_id=normalized_assertion.genesis_submission_id,
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
                            "UPDATE assertions SET lifecycle='superseded', updated_at=? "
                            "WHERE assertion_id=? AND "
                            + self._assertion_namespace_predicate("assertions"),
                            (now, superseded_id, *self._assertion_namespace_params()),
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
                           updated_at=? WHERE episode_id=?"""
                    + (
                        " AND json_extract(metadata_json, '$.elfie_id')=?"
                        if getattr(self, "elfie_id", None) is not None
                        else ""
                    ),
                    (
                        now,
                        projection.episode_id,
                        *(
                            (str(self.elfie_id),)
                            if getattr(self, "elfie_id", None) is not None
                            else ()
                        ),
                    ),
                )
                self.conn.execute(
                    """UPDATE episodes SET projection_revision=?,
                           projection_source_sha256=content_sha256,
                           last_reinforced_at=?, last_reviewed_at=?,
                           updated_at=? WHERE episode_id=?"""
                    + (
                        " AND json_extract(metadata_json, '$.elfie_id')=?"
                        if getattr(self, "elfie_id", None) is not None
                        else ""
                    ),
                    (
                        projection_revision,
                        now,
                        now,
                        now,
                        projection.episode_id,
                        *(
                            (str(self.elfie_id),)
                            if getattr(self, "elfie_id", None) is not None
                            else ()
                        ),
                    ),
                )
                self._commit_write_transaction(owns)
            except Exception:
                self._rollback_write_transaction(owns)
                # A nested projection failure rolls back the complete outer
                # Unit of Work as well.  Persist the bounded diagnostic after
                # that rollback in either case, while leaving fact rows
                # unpublished and retryable.
                self._record_projection_diagnostic(
                    projection,
                    reason="projection_validation_failed",
                )
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
            owns = self._begin_write_transaction()
            try:
                self._upsert_node(node, utc_now())
                self._commit_write_transaction(owns)
            except Exception:
                self._rollback_write_transaction(owns)
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
            owns = self._begin_write_transaction()
            try:
                source = self.conn.execute(
                    "SELECT node_id, canonical_label FROM nodes WHERE node_id=?",
                    (source_id,),
                ).fetchone()
                target_root = self._resolve_graph_node_id_locked(target_id)
                source_root = self._resolve_graph_node_id_locked(source_id)
                if source is None or target_root is None or source_root != source_id:
                    self._commit_write_transaction(owns)
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
                self._commit_write_transaction(owns)
            except Exception:
                self._rollback_write_transaction(owns)
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
            visibility, visibility_params = self._genesis_visibility("n")
            namespace_clause = ""
            namespace_params: list[object] = []
            if getattr(self, "elfie_id", None) is not None:
                namespace_clause = (
                    " AND json_extract(n.properties_json, '$.elfie_id')=?"
                )
                namespace_params.append(str(self.elfie_id))
            row = self.conn.execute(
                "SELECT n.node_id, n.merged_into FROM nodes AS n WHERE n.node_id=?"
                + namespace_clause
                + " AND "
                + visibility,
                [current, *namespace_params, *visibility_params],
            ).fetchone()
            if row is None:
                return None
            if row["merged_into"] is None:
                return str(row["node_id"])
            current = str(row["merged_into"])
        return None

    def get_graph_node(
        self, node_id: str, *, privacy_scope: str | None = None
    ) -> Optional[RecallNode]:
        resolved = self.resolve_graph_node_id(node_id)
        if resolved is None:
            return None
        with self._lock:
            scope = ""
            params: list[object] = [resolved]
            if getattr(self, "elfie_id", None) is not None:
                scope = " AND json_extract(properties_json, '$.elfie_id')=?"
                params.append(str(self.elfie_id))
            if privacy_scope is not None:
                scope += " AND n.privacy_scope=?"
                params.append(privacy_scope)
            visibility, visibility_params = self._genesis_visibility("n")
            params.extend(visibility_params)
            row = self.conn.execute(
                """SELECT node_id, node_type, canonical_label, description,
                          confidence, importance FROM nodes AS n WHERE n.node_id=?"""
                + scope
                + " AND "
                + visibility,
                params,
            ).fetchone()
        if row is None:
            return None
        return RecallNode(
            node_id=str(row["node_id"]),
            node_type=str(row["node_type"]),
            label=str(row["canonical_label"]),
            description=row["description"],
            relevance=float(row["confidence"]),
            importance=float(row["importance"]),
            confidence=float(row["confidence"]),
        )

    def list_graph_nodes(
        self, limit: int = 100, *, privacy_scope: str | None = None
    ) -> tuple[RecallNode, ...]:
        with self._lock:
            scope = ""
            params: list[object] = [max(0, limit)]
            if getattr(self, "elfie_id", None) is not None:
                scope = " AND json_extract(n.properties_json, '$.elfie_id')=?"
                params = [str(self.elfie_id), max(0, limit)]
            if privacy_scope is not None:
                scope += " AND n.privacy_scope=?"
                params.insert(-1, privacy_scope)
            visibility, visibility_params = self._genesis_visibility("n")
            params[-1:-1] = visibility_params
            rows = self.conn.execute(
                """SELECT n.node_id, n.node_type, n.canonical_label, n.description,
                          n.confidence, n.importance FROM nodes AS n WHERE n.status <> 'forgotten'
                                              AND n.merged_into IS NULL"""
                + scope
                + " AND "
                + visibility
                + " ORDER BY n.node_id LIMIT ?",
                params,
            ).fetchall()
        return tuple(
            RecallNode(
                node_id=str(row["node_id"]),
                node_type=str(row["node_type"]),
                label=str(row["canonical_label"]),
                description=row["description"],
                relevance=float(row["confidence"]),
                importance=float(row["importance"]),
                confidence=float(row["confidence"]),
            )
            for row in rows
        )

    def find_graph_nodes(
        self, query: str, limit: int = 20, *, privacy_scope: str | None = None
    ) -> tuple[RecallNode, ...]:
        normalized = normalize_text(query)
        if not normalized:
            return ()
        like = f"%{normalized}%"
        with self._lock:
            scope = ""
            params: list[object] = [normalized, normalized, like, like]
            if getattr(self, "elfie_id", None) is not None:
                scope = " AND json_extract(n.properties_json, '$.elfie_id')=?"
                params.append(str(self.elfie_id))
            if privacy_scope is not None:
                scope += " AND n.privacy_scope=?"
                params.append(privacy_scope)
            visibility, visibility_params = self._genesis_visibility("n")
            params.extend(visibility_params)
            params.extend([like, like, like])
            params.append(max(0, limit))
            rows = self.conn.execute(
                """SELECT DISTINCT n.node_id, n.node_type, n.canonical_label,
                          n.description, n.confidence, n.importance,
                          CASE WHEN n.normalized_label=? OR a.normalized_alias=? THEN 1.0
                               WHEN n.normalized_label LIKE ? THEN 0.8
                               WHEN a.normalized_alias LIKE ? THEN 0.75
                               ELSE 0.5 END AS score
                     FROM nodes AS n LEFT JOIN node_aliases AS a ON a.node_id=n.node_id
                    WHERE n.status <> 'forgotten' AND n.merged_into IS NULL"""
                + scope
                + " AND "
                + visibility
                + """
                      AND (n.normalized_label LIKE ? OR a.normalized_alias LIKE ?
                           OR lower(COALESCE(n.description,'')) LIKE ?)
                    ORDER BY score DESC, n.node_id LIMIT ?""",
                params,
            ).fetchall()
        return tuple(
            RecallNode(
                node_id=str(row["node_id"]),
                node_type=str(row["node_type"]),
                label=str(row["canonical_label"]),
                description=row["description"],
                relevance=float(row["score"]),
                importance=float(row["importance"]),
                confidence=float(row["confidence"]),
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
        person_node_ids: Iterable[str] = (),
        place_node_ids: Iterable[str] = (),
        emotion_labels: Iterable[str] = (),
        topic_labels: Iterable[str] = (),
        cause_labels: Iterable[str] = (),
        privacy_scope: str | None = None,
        include_unknown_time: bool = False,
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
        assertion_visibility, assertion_visibility_params = self._genesis_visibility(
            "a"
        )
        params: list[Any] = list(ids) + list(ids) + list(assertion_visibility_params)
        namespace_clause = ""
        if getattr(self, "elfie_id", None) is not None or privacy_scope is not None:
            namespace_conditions = ["ns.node_id=a.subject_node_id"]
            if getattr(self, "elfie_id", None) is not None:
                namespace_conditions.append(
                    "json_extract(ns.properties_json, '$.elfie_id')=?"
                )
                params.append(str(self.elfie_id))
            if privacy_scope is not None:
                namespace_conditions.append("ns.privacy_scope=?")
                params.append(privacy_scope)
            namespace_clause = (
                " AND EXISTS (SELECT 1 FROM nodes AS ns WHERE "
                + " AND ".join(namespace_conditions)
                + ")"
            )
            object_conditions: list[str] = []
            if getattr(self, "elfie_id", None) is not None:
                object_conditions.append(
                    "json_extract(no.properties_json, '$.elfie_id')=?"
                )
                params.append(str(self.elfie_id))
            if privacy_scope is not None:
                object_conditions.append("no.privacy_scope=?")
                params.append(privacy_scope)
            if object_conditions:
                namespace_clause += (
                    " AND (a.object_node_id IS NULL OR EXISTS ("
                    "SELECT 1 FROM nodes AS no WHERE no.node_id=a.object_node_id AND "
                    + " AND ".join(object_conditions)
                    + "))"
                )
        if relations:
            relation_clause = (
                " AND a.predicate IN (" + ",".join("?" for _ in relations) + ")"
            )
            params.extend(relations)
        time_clause = ""
        if (
            occurred_from is not None
            or occurred_to is not None
            or person_node_ids
            or place_node_ids
            or emotion_labels
            or topic_labels
            or cause_labels
            or privacy_scope is not None
        ):
            episode_conditions = ["p.lifecycle <> 'forgotten'"]
            time_params: list[Any] = []
            time_conditions: list[str] = []
            if occurred_from is not None:
                time_conditions.append(
                    "(p.occurred_from >= ? OR "
                    "(p.occurrence_precision='range' AND p.occurred_to >= ?))"
                )
                time_params.extend((occurred_from, occurred_from))
            if occurred_to is not None:
                time_conditions.append(
                    "p.occurred_from IS NOT NULL AND p.occurred_from <= ?"
                )
                time_params.append(occurred_to)
            if time_conditions:
                time_expression = " AND ".join(time_conditions)
                episode_conditions.append(
                    "(p.occurred_from IS NULL OR (" + time_expression + "))"
                    if include_unknown_time
                    else time_expression
                )
            facet_conditions, facet_params = _episode_facet_conditions(
                person_node_ids=person_node_ids,
                place_node_ids=place_node_ids,
                emotion_labels=emotion_labels,
                topic_labels=topic_labels,
                cause_labels=cause_labels,
                privacy_scope=privacy_scope,
            )
            episode_conditions.extend(facet_conditions)
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
            params.extend(facet_params)
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
                    WHERE a.lifecycle IN ('active', 'superseded')
                      AND (a.subject_node_id IN ({placeholders})
                           OR a.object_node_id IN ({placeholders}))
                      AND {assertion_visibility}
                      {namespace_clause}
                      {relation_clause}
                      {time_clause}
                    ORDER BY CASE WHEN a.lifecycle='active' THEN 0 ELSE 1 END,
                             a.importance DESC, a.confidence DESC, a.assertion_id LIMIT ?""",
                params,
            ).fetchall()
        return tuple(_row_to_assertion(row) for row in rows)

    def get_assertion_evidence(
        self,
        assertion_ids: Iterable[str],
        limit: int = 24,
        *,
        privacy_scope: str | None = None,
    ) -> tuple[RecallEvidence, ...]:
        ids = tuple(dict.fromkeys(assertion_ids))
        if not ids or limit < 1:
            return ()
        placeholders = ",".join("?" for _ in ids)
        evidence_visibility, evidence_visibility_params = self._genesis_visibility("e")
        assertion_visibility, assertion_visibility_params = self._genesis_visibility(
            "a"
        )
        link_visibility, link_visibility_params = self._genesis_visibility("ae")
        assertion_namespace_clause = ""
        assertion_namespace_params: list[object] = []
        if getattr(self, "elfie_id", None) is not None or privacy_scope is not None:
            assertion_namespace_conditions = ["an.node_id=a.subject_node_id"]
            if getattr(self, "elfie_id", None) is not None:
                assertion_namespace_conditions.append(
                    "json_extract(an.properties_json, '$.elfie_id')=?"
                )
                assertion_namespace_params.append(str(self.elfie_id))
            if privacy_scope is not None:
                assertion_namespace_conditions.append("an.privacy_scope=?")
                assertion_namespace_params.append(privacy_scope)
            assertion_namespace_clause = (
                " AND EXISTS (SELECT 1 FROM nodes AS an WHERE "
                + " AND ".join(assertion_namespace_conditions)
                + ")"
            )
        privacy_clause = ""
        privacy_params: list[object] = []
        if privacy_scope is not None:
            privacy_clause = (
                " AND (e.source_type <> 'episode' OR EXISTS ("
                "SELECT 1 FROM episodes AS p WHERE p.episode_id=e.source_id "
                "AND p.lifecycle <> 'forgotten' AND p.privacy_scope=?))"
            )
            privacy_params.append(privacy_scope)
        with self._lock:
            rows = self.conn.execute(
                f"""SELECT e.evidence_id, e.source_type, e.source_id, e.source_version,
                           e.excerpt, e.media_locator, e.modality, e.span_start,
                           e.span_end, e.speaker, e.viewpoint, e.captured_at,
                           e.attribution,
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
                      JOIN assertions AS a ON a.assertion_id=ae.assertion_id
                     WHERE ae.assertion_id IN ({placeholders})
                       AND {evidence_visibility}
                       AND {assertion_visibility}
                       {assertion_namespace_clause}
                       AND {link_visibility}
                       {privacy_clause}
                     GROUP BY e.evidence_id, e.source_type, e.source_id, e.source_version,
                              e.excerpt, e.media_locator, e.modality, e.span_start,
                              e.span_end, e.speaker, e.viewpoint, e.captured_at, e.attribution
                     ORDER BY e.evidence_id LIMIT ?""",
                list(ids)
                + evidence_visibility_params
                + assertion_visibility_params
                + assertion_namespace_params
                + link_visibility_params
                + privacy_params
                + [max(0, limit)],
            ).fetchall()
        unique: dict[str, RecallEvidence] = {}
        for row in rows:
            evidence_id = str(row["evidence_id"])
            unique.setdefault(
                evidence_id,
                RecallEvidence(
                    evidence_id=evidence_id,
                    source_type=str(row["source_type"]),
                    source_id=str(row["source_id"]),
                    source_version=row["source_version"],
                    excerpt=row["excerpt"],
                    media_locator=row["media_locator"],
                    stance=str(row["stance"]),
                    modality=str(row["modality"]),
                    span_start=row["span_start"],
                    span_end=row["span_end"],
                    speaker=row["speaker"],
                    viewpoint=row["viewpoint"],
                    captured_at=row["captured_at"],
                    attribution=row["attribution"],
                ),
            )
        return tuple(unique.values())

    def get_evidence(self, evidence_id: str) -> Optional[RecallEvidence]:
        evidence_visibility, evidence_visibility_params = self._genesis_visibility("e")
        namespace_clause = ""
        namespace_params: list[object] = []
        if getattr(self, "elfie_id", None) is not None:
            namespace_clause = (
                " AND ((e.source_type='episode' AND EXISTS ("
                "SELECT 1 FROM episodes AS source_e "
                "WHERE source_e.episode_id=e.source_id "
                "AND json_extract(source_e.metadata_json, '$.elfie_id')=?))"
                " OR (e.source_type<>'episode' AND EXISTS ("
                "SELECT 1 FROM assertion_evidence AS source_ae "
                "JOIN assertions AS source_a ON source_a.assertion_id=source_ae.assertion_id "
                "JOIN nodes AS source_n ON source_n.node_id=source_a.subject_node_id "
                "WHERE source_ae.evidence_id=e.evidence_id "
                "AND json_extract(source_n.properties_json, '$.elfie_id')=?)))"
            )
            namespace_params.extend([str(self.elfie_id), str(self.elfie_id)])
        with self._lock:
            row = self.conn.execute(
                """SELECT e.evidence_id, e.source_type, e.source_id, e.source_version,
                          e.excerpt, e.media_locator, e.modality, e.span_start,
                          e.span_end, e.speaker, e.viewpoint, e.captured_at, e.attribution,
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
                    WHERE e.evidence_id=? AND """
                + evidence_visibility
                + namespace_clause
                + """
                     GROUP BY e.evidence_id, e.source_type, e.source_id, e.source_version,
                              e.excerpt, e.media_locator, e.modality, e.span_start,
                              e.span_end, e.speaker, e.viewpoint, e.captured_at, e.attribution""",
                [evidence_id, *evidence_visibility_params, *namespace_params],
            ).fetchone()
        if row is None:
            return None
        return RecallEvidence(
            evidence_id=str(row["evidence_id"]),
            source_type=str(row["source_type"]),
            source_id=str(row["source_id"]),
            source_version=row["source_version"],
            excerpt=row["excerpt"],
            media_locator=row["media_locator"],
            stance=str(row["stance"]),
            modality=str(row["modality"]),
            span_start=row["span_start"],
            span_end=row["span_end"],
            speaker=row["speaker"],
            viewpoint=row["viewpoint"],
            captured_at=row["captured_at"],
            attribution=row["attribution"],
        )

    def get_assertion_evidence_for_ids(
        self, evidence_ids: Iterable[str]
    ) -> tuple[RecallEvidence, ...]:
        ids = tuple(dict.fromkeys(evidence_ids))
        if not ids:
            return ()
        placeholders = ",".join("?" for _ in ids)
        evidence_visibility, evidence_visibility_params = self._genesis_visibility("e")
        link_visibility, link_visibility_params = self._genesis_visibility("ae")
        namespace_clause = ""
        namespace_params: list[object] = []
        if getattr(self, "elfie_id", None) is not None:
            namespace_clause = (
                " AND ((e.source_type='episode' AND EXISTS ("
                "SELECT 1 FROM episodes AS source_e "
                "WHERE source_e.episode_id=e.source_id "
                "AND json_extract(source_e.metadata_json, '$.elfie_id')=?))"
                " OR (e.source_type<>'episode' AND EXISTS ("
                "SELECT 1 FROM assertion_evidence AS source_ae "
                "JOIN assertions AS source_a ON source_a.assertion_id=source_ae.assertion_id "
                "JOIN nodes AS source_n ON source_n.node_id=source_a.subject_node_id "
                "WHERE source_ae.evidence_id=e.evidence_id "
                "AND json_extract(source_n.properties_json, '$.elfie_id')=?)))"
            )
            namespace_params.extend([str(self.elfie_id), str(self.elfie_id)])
        with self._lock:
            rows = self.conn.execute(
                f"""SELECT e.evidence_id, e.source_type, e.source_id, e.source_version,
                          e.excerpt, e.media_locator, e.modality, e.span_start,
                          e.span_end, e.speaker, e.viewpoint, e.captured_at, e.attribution,
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
                       AND {evidence_visibility}
                       AND {link_visibility}
                       {namespace_clause}
                     GROUP BY e.evidence_id, e.source_type, e.source_id, e.source_version,
                              e.excerpt, e.media_locator, e.modality, e.span_start,
                              e.span_end, e.speaker, e.viewpoint, e.captured_at, e.attribution
                     ORDER BY e.evidence_id""",
                list(ids)
                + evidence_visibility_params
                + link_visibility_params
                + namespace_params,
            ).fetchall()
        return tuple(
            RecallEvidence(
                evidence_id=str(row["evidence_id"]),
                source_type=str(row["source_type"]),
                source_id=str(row["source_id"]),
                source_version=row["source_version"],
                excerpt=row["excerpt"],
                media_locator=row["media_locator"],
                stance=str(row["stance"]),
                modality=str(row["modality"]),
                span_start=row["span_start"],
                span_end=row["span_end"],
                speaker=row["speaker"],
                viewpoint=row["viewpoint"],
                captured_at=row["captured_at"],
                attribution=row["attribution"],
            )
            for row in rows
        )

    def get_edges(self, node_id: str, direction: str = "outgoing") -> list[Edge]:
        resolved_node_id = self.resolve_graph_node_id(node_id)
        if resolved_node_id is None:
            return []
        assertion_visibility, assertion_visibility_params = self._genesis_visibility(
            "a"
        )
        clauses = ""
        params: list[Any] = [resolved_node_id]
        if direction == "incoming":
            clauses = "a.object_node_id=?"
        elif direction == "outgoing":
            clauses = "a.subject_node_id=?"
        else:
            clauses = "(a.subject_node_id=? OR a.object_node_id=?)"
            params.append(resolved_node_id)
        namespace_clause = ""
        namespace_params: list[object] = []
        if getattr(self, "elfie_id", None) is not None:
            namespace_clause = (
                " AND EXISTS (SELECT 1 FROM nodes AS ns WHERE ns.node_id="
                "a.subject_node_id AND json_extract(ns.properties_json, '$.elfie_id')=?)"
            )
            namespace_params.append(str(self.elfie_id))
            namespace_clause += (
                " AND (a.object_node_id IS NULL OR EXISTS ("
                "SELECT 1 FROM nodes AS no WHERE no.node_id=a.object_node_id "
                "AND json_extract(no.properties_json, '$.elfie_id')=?))"
            )
            namespace_params.append(str(self.elfie_id))
        with self._lock:
            rows = self.conn.execute(
                f"""SELECT a.subject_node_id, a.object_node_id, a.predicate,
                           a.importance, a.confidence FROM assertions AS a
                    WHERE a.lifecycle='active' AND {clauses}
                      {namespace_clause}
                      AND {assertion_visibility}
                    ORDER BY a.assertion_id""",
                [*params, *namespace_params, *assertion_visibility_params],
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
                weight=float(row["importance"]),
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
            importance=bounded_score(weight),
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
            owns = self._begin_write_transaction()
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
                self._commit_write_transaction(owns)
            except Exception:
                self._rollback_write_transaction(owns)
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
                supersedes_assertion_id=assertion.supersedes_assertion_id,
                evidence_ids=tuple(assertion.evidence_ids) + (evidence.evidence_id,),
                assertion_id=assertion.assertion_id,
                importance=assertion.importance,
                object_literal_type=assertion.object_literal_type,
                predicate_registry_version=assertion.predicate_registry_version,
                policy_version=assertion.policy_version,
                genesis_submission_id=assertion.genesis_submission_id,
            )
        with self._lock:
            now = utc_now()
            owns = self._begin_write_transaction()
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
                self._commit_write_transaction(owns)
            except Exception:
                self._rollback_write_transaction(owns)
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
                    importance=node.importance,
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
            namespace_clause = ""
            namespace_params: tuple[object, ...] = ()
            if getattr(self, "elfie_id", None) is not None:
                namespace_clause = (
                    " AND json_extract(n.properties_json, '$.elfie_id')=?"
                )
                namespace_params = (str(self.elfie_id),)
            rows = self.conn.execute(
                """SELECT n.node_id FROM nodes AS n
                   WHERE normalized_label=? AND node_type=? AND scope=?
                     AND status <> 'forgotten' AND merged_into IS NULL
                     """
                + namespace_clause
                + """
                   ORDER BY node_id LIMIT 2""",
                (normalized, node.node_type, node.scope, *namespace_params),
            ).fetchall()
            alias_rows = self.conn.execute(
                """SELECT DISTINCT n.node_id FROM node_aliases AS a
                   JOIN nodes AS n ON n.node_id=a.node_id
                  WHERE a.normalized_alias=? AND a.scope=?
                    AND n.node_type=? AND n.status <> 'forgotten'
                    AND n.merged_into IS NULL
                    """
                + namespace_clause
                + """
                  ORDER BY n.node_id LIMIT 2""",
                (normalized, node.scope, node.node_type, *namespace_params),
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
                        importance=node.importance,
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
            "SELECT node_type, normalized_label, scope, properties_json, description, "
            "first_seen_at, genesis_submission_id FROM nodes WHERE node_id=?",
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
        configured_elfie = getattr(self, "elfie_id", None)
        if configured_elfie is not None:
            existing_elfie = properties.get("elfie_id")
            if existing is not None and existing_elfie is None:
                raise ValueError(
                    "Node belongs to an unbound namespace and cannot be reused"
                )
            if existing_elfie is not None and str(existing_elfie) != str(
                configured_elfie
            ):
                raise ValueError("Node belongs to a different Elfie namespace")
            properties.setdefault("elfie_id", str(configured_elfie))
        active_submission = getattr(self, "_active_genesis_submission_id", None)
        supplied_properties = dict(node.properties)
        if (
            configured_elfie is not None
            and supplied_properties.get("elfie_id") is not None
        ):
            if str(supplied_properties["elfie_id"]) != str(configured_elfie):
                raise ValueError("Node belongs to a different Elfie namespace")
        supplied_submission = supplied_properties.get("genesis_submission_id")
        if (
            active_submission is not None
            and supplied_submission is not None
            and str(supplied_submission) != active_submission
        ):
            raise ValueError(
                "Node genesis submission does not match the active submission"
            )
        properties.update(supplied_properties)
        if configured_elfie is not None:
            # The adapter-owned namespace cannot be overwritten by caller
            # metadata, even when the caller supplies an ``elfie_id`` field.
            properties["elfie_id"] = str(configured_elfie)
        existing_submission = (
            None if existing is None else existing["genesis_submission_id"]
        )
        if active_submission is not None:
            # A Genesis package cannot smuggle an output into another
            # submission by supplying row metadata directly.  Conversely,
            # reusing a row committed by an earlier submission must not retag
            # it, otherwise that earlier package would become unreadable.
            properties["genesis_submission_id"] = (
                active_submission
                if existing_submission is None
                else str(existing_submission)
            )
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
                   description, scope, status, confidence, importance, properties_json,
                   first_seen_at, last_seen_at, updated_at, privacy_scope,
                   genesis_submission_id
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(node_id) DO UPDATE SET
                   node_type=excluded.node_type,
                   canonical_label=excluded.canonical_label,
                   normalized_label=excluded.normalized_label,
                   description=COALESCE(excluded.description, nodes.description),
                   scope=excluded.scope,
                   status=excluded.status,
                   confidence=MAX(nodes.confidence, excluded.confidence),
                   importance=MAX(nodes.importance, excluded.importance),
                   properties_json=excluded.properties_json,
                   last_seen_at=excluded.last_seen_at,
                   updated_at=excluded.updated_at,
                   privacy_scope=excluded.privacy_scope,
                   genesis_submission_id=CASE
                       WHEN nodes.genesis_submission_id IS NOT NULL
                           THEN nodes.genesis_submission_id
                       ELSE excluded.genesis_submission_id
                   END""",
            (
                node.node_id,
                node.node_type,
                label,
                normalize_text(label),
                description,
                node.scope,
                node.status,
                bounded_score(node.confidence),
                bounded_score(node.importance),
                canonical_json(properties),
                first_seen,
                now,
                now,
                str(properties.get("privacy_scope", "private")),
                properties.get("genesis_submission_id") or active_submission,
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
                   evidence_id, confidence, genesis_submission_id, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                getattr(self, "_active_genesis_submission_id", None),
                now,
            ),
        )
        self._refresh_node_text_projection(alias.node_id)

    def _insert_description(self, description: DescriptionInput, now: str) -> None:
        digest = content_hash(description.text)
        self.conn.execute(
            """INSERT OR IGNORE INTO node_descriptions (
                   description_id, node_id, text, language, kind,
                   content_sha256, evidence_id, confidence, genesis_submission_id,
                   created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                getattr(self, "_active_genesis_submission_id", None),
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
                   surface_text, span_start, span_end, confidence,
                   genesis_submission_id, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                getattr(self, "_active_genesis_submission_id", None),
                now,
            ),
        )

    def _insert_evidence(self, evidence: EvidenceInput, now: str) -> None:
        if evidence.source_type == "episode":
            source_scope = ""
            source_params: list[object] = [evidence.source_id]
            if getattr(self, "elfie_id", None) is not None:
                source_scope = (
                    " AND json_extract(source_e.metadata_json, '$.elfie_id')=?"
                )
                source_params.append(str(self.elfie_id))
            source_visibility, source_visibility_params = self._genesis_visibility(
                "source_e"
            )
            source_params.extend(source_visibility_params)
            source_row = self.conn.execute(
                "SELECT source_e.content_sha256, source_e.source_version "
                "FROM episodes AS source_e WHERE source_e.episode_id=?"
                + source_scope
                + " AND "
                + source_visibility,
                source_params,
            ).fetchone()
            if source_row is None:
                raise ValueError(
                    f"Episode evidence points to an unknown source: {evidence.source_id}"
                )
            if evidence.source_sha256 is not None and evidence.source_sha256 != str(
                source_row["content_sha256"]
            ):
                raise ValueError(
                    "Episode evidence source hash does not match the source Episode"
                )
            if (
                evidence.source_version is not None
                and source_row["source_version"] is not None
                and evidence.source_version != str(source_row["source_version"])
            ):
                raise ValueError(
                    "Episode evidence source version does not match the source Episode"
                )
        existing = self.conn.execute(
            """SELECT source_type, source_id, excerpt, media_locator, modality,
                              span_start, span_end, speaker, viewpoint,
                              captured_at, extraction_run_id, source_sha256,
                              source_version, attribution, genesis_submission_id
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
            or existing["source_version"] != evidence.source_version
            or existing["attribution"] != evidence.attribution
        ):
            raise ValueError(
                f"evidence ID is already bound to different source data: {evidence.evidence_id}"
            )
        active_submission = getattr(self, "_active_genesis_submission_id", None)
        if (
            active_submission is not None
            and evidence.genesis_submission_id is not None
            and evidence.genesis_submission_id != active_submission
        ):
            raise ValueError(
                "Evidence genesis submission does not match the active submission"
            )
        self.conn.execute(
            """INSERT OR IGNORE INTO evidence (
                   evidence_id, source_type, source_id, excerpt, media_locator,
                   modality, span_start, span_end, speaker, viewpoint,
                   captured_at, extraction_run_id, source_sha256, source_version,
                   attribution, genesis_submission_id, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                evidence.source_version,
                evidence.attribution,
                active_submission or evidence.genesis_submission_id,
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
        canonical_predicate = resolve_predicate(assertion.predicate)
        if canonical_predicate != assertion.predicate:
            assertion = replace(assertion, predicate=canonical_predicate)
        if assertion.predicate_registry_version != PREDICATE_REGISTRY_VERSION:
            raise ValueError(
                "assertion predicate registry version is not supported: "
                + assertion.predicate_registry_version
            )
        configured_elfie = getattr(self, "elfie_id", None)
        if configured_elfie is not None:
            node_ids = tuple(
                dict.fromkeys(
                    node_id
                    for node_id in (assertion.subject_id, assertion.object_node_id)
                    if node_id is not None
                )
            )
            placeholders = ",".join("?" for _ in node_ids)
            rows = self.conn.execute(
                "SELECT node_id, properties_json FROM nodes WHERE node_id IN ("
                + placeholders
                + ")",
                node_ids,
            ).fetchall()
            owners = {
                str(row["node_id"]): json_object(row["properties_json"]).get("elfie_id")
                for row in rows
            }
            if any(
                owners.get(node_id) is None
                or str(owners[node_id]) != str(configured_elfie)
                for node_id in node_ids
            ):
                raise ValueError("Assertion references a different Elfie namespace")
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
        # Importance is the lifecycle/retrieval score. Keep it independent
        # from the compatibility support score: strong evidence does not by
        # itself make a routine claim important.
        effective_importance = bounded_score(assertion.importance)
        active_submission = getattr(self, "_active_genesis_submission_id", None)
        if (
            active_submission is not None
            and assertion.genesis_submission_id is not None
            and assertion.genesis_submission_id != active_submission
        ):
            raise ValueError(
                "Assertion genesis submission does not match the active submission"
            )
        self.conn.execute(
            """INSERT INTO assertions (
                   assertion_id, subject_node_id, predicate, object_node_id,
                   object_literal_json, object_literal_type, object_unit, polarity,
                   epistemic_status, viewpoint, context, valid_from, valid_to,
                   confidence, importance, support_score, conflict_group, fingerprint,
                   lifecycle, supersedes_assertion_id, predicate_registry_version,
                   policy_version, genesis_submission_id, created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)
               ON CONFLICT(fingerprint) DO UPDATE SET
                   confidence=MAX(assertions.confidence, excluded.confidence),
                   importance=MAX(assertions.importance, excluded.importance),
                   support_score=MAX(assertions.support_score, excluded.support_score),
                   updated_at=excluded.updated_at,
                   predicate_registry_version=excluded.predicate_registry_version,
                   policy_version=excluded.policy_version""",
            (
                assertion_id,
                assertion.subject_id,
                assertion.predicate,
                assertion.object_node_id,
                literal,
                assertion.object_literal_type
                or _literal_type(assertion.object_literal),
                assertion.object_unit,
                assertion.polarity,
                assertion.epistemic_status,
                assertion.viewpoint,
                assertion.context,
                assertion.valid_from,
                assertion.valid_to,
                bounded_score(assertion.confidence),
                effective_importance,
                bounded_score(assertion.support_score),
                conflict_group,
                fingerprint,
                assertion.supersedes_assertion_id,
                assertion.predicate_registry_version,
                assertion.policy_version,
                active_submission or assertion.genesis_submission_id,
                now,
                now,
            ),
        )
        row = self.conn.execute(
            "SELECT assertion_id FROM assertions WHERE fingerprint=? AND "
            + self._assertion_namespace_predicate("assertions"),
            (fingerprint, *self._assertion_namespace_params()),
        ).fetchone()
        if row is None:
            raise RuntimeError("assertion write did not return an ID")
        return str(row["assertion_id"])

    def _insert_assertion_evidence(
        self, link: AssertionEvidenceInput, assertion_id: str, now: str
    ) -> None:
        existing = self.conn.execute(
            "SELECT stance FROM assertion_evidence WHERE assertion_id=? AND evidence_id=?",
            (assertion_id, link.evidence_id),
        ).fetchone()
        if existing is not None:
            # A replay of the same sourced link is a semantic no-op.  If two
            # projections disagree about its stance, retain the conservative
            # context marker but never apply a second score contribution.
            if str(existing["stance"]) != link.stance:
                self.conn.execute(
                    "UPDATE assertion_evidence SET stance='context' "
                    "WHERE assertion_id=? AND evidence_id=?",
                    (assertion_id, link.evidence_id),
                )
            return
        prior_evidence = self.conn.execute(
            "SELECT 1 FROM assertion_evidence WHERE assertion_id=? LIMIT 1",
            (assertion_id,),
        ).fetchone()
        self.conn.execute(
            """INSERT INTO assertion_evidence (
                   assertion_id, evidence_id, stance, genesis_submission_id, created_at
               ) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(assertion_id, evidence_id) DO UPDATE SET
                   stance=CASE
                       WHEN assertion_evidence.stance=excluded.stance
                           THEN assertion_evidence.stance
                       ELSE 'context'
                   END""",
            (
                assertion_id,
                link.evidence_id,
                link.stance,
                getattr(self, "_active_genesis_submission_id", None),
                now,
            ),
        )
        if prior_evidence is not None:
            self._apply_evidence_score(
                assertion_id=assertion_id,
                stance=link.stance,
                now=now,
            )

    def _apply_evidence_score(
        self,
        *,
        assertion_id: str,
        stance: EvidenceStance,
        now: str,
    ) -> None:
        """Apply one distinct evidence contribution to a claim and its nodes."""
        row = self.conn.execute(
            "SELECT subject_node_id, object_node_id, confidence, importance "
            "FROM assertions WHERE assertion_id=?",
            (assertion_id,),
        ).fetchone()
        if row is None:
            return
        update = MemoryScorePolicy.evidence_update(
            confidence=float(row["confidence"]),
            importance=float(row["importance"]),
            stance=stance,
        )
        self.conn.execute(
            """UPDATE assertions SET confidence=?, importance=?,
                   last_reinforced_at=?, policy_version=?, updated_at=?
               WHERE assertion_id=?""",
            (
                update.confidence,
                update.importance,
                now,
                MemoryScorePolicy.version,
                now,
                assertion_id,
            ),
        )
        node_ids = tuple(
            dict.fromkeys(
                str(node_id)
                for node_id in (row["subject_node_id"], row["object_node_id"])
                if node_id is not None
            )
        )
        for node_id in node_ids:
            node = self.conn.execute(
                "SELECT confidence, importance FROM nodes WHERE node_id=?",
                (node_id,),
            ).fetchone()
            if node is None:
                continue
            node_update = MemoryScorePolicy.evidence_update(
                confidence=float(node["confidence"]),
                importance=float(node["importance"]),
                stance=stance,
            )
            self.conn.execute(
                """UPDATE nodes SET confidence=?, importance=?,
                       last_reinforced_at=?, policy_version=?, updated_at=?
                   WHERE node_id=?""",
                (
                    node_update.confidence,
                    node_update.importance,
                    now,
                    MemoryScorePolicy.version,
                    now,
                    node_id,
                ),
            )

    def _assertion_exists(self, assertion_id: str) -> bool:
        return (
            self.conn.execute(
                "SELECT 1 FROM assertions WHERE assertion_id=? AND "
                + self._assertion_namespace_predicate("assertions"),
                (assertion_id, *self._assertion_namespace_params()),
            ).fetchone()
            is not None
        )

    def _assertion_namespace_predicate(self, alias: str) -> str:
        if getattr(self, "elfie_id", None) is None:
            return "1=1"
        if not alias.replace("_", "").isalnum():
            raise ValueError("invalid SQL alias")
        return (
            "EXISTS (SELECT 1 FROM nodes AS assertion_node "
            f"WHERE assertion_node.node_id={alias}.subject_node_id "
            "AND json_extract(assertion_node.properties_json, '$.elfie_id')=?)"
        )

    def _assertion_namespace_params(self) -> tuple[object, ...]:
        if getattr(self, "elfie_id", None) is None:
            return ()
        return (str(self.elfie_id),)

    def _record_projection_diagnostic(
        self, projection: ConsolidationProjection, *, reason: str
    ) -> None:
        """Persist a bounded rejection record outside the failed fact UoW."""
        diagnostic_id = stable_id(
            "diagnostic:",
            projection.episode_id,
            projection.source_sha256,
            reason,
            tuple(assertion.predicate for assertion in projection.assertions),
            length=32,
        )
        owns = self._begin_write_transaction()
        try:
            self.conn.execute(
                """INSERT OR IGNORE INTO projection_diagnostics(
                       diagnostic_id, elfie_id, episode_id, predicate, reason,
                       payload_json, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    diagnostic_id,
                    str(getattr(self, "elfie_id", "") or ""),
                    projection.episode_id,
                    ",".join(
                        assertion.predicate for assertion in projection.assertions
                    )[:512],
                    reason,
                    canonical_json({"assertion_count": len(projection.assertions)}),
                    utc_now(),
                ),
            )
            self._commit_write_transaction(owns)
        except Exception:
            self._rollback_write_transaction(owns)

    def _latest_active_claim(
        self,
        *,
        subject_id: str,
        predicate: str,
        object_node_id: str | None,
        object_literal: object | None,
        object_literal_type: str | None,
    ) -> str | None:
        """Find a prior value for an explicit correction, never a conflict."""
        rows = self.conn.execute(
            """SELECT assertion_id, object_node_id, object_literal_json,
                              object_literal_type
                 FROM assertions
                WHERE subject_node_id=? AND predicate=? AND lifecycle='active'
                ORDER BY updated_at DESC, assertion_id DESC""",
            (subject_id, predicate),
        ).fetchall()
        desired_literal = (
            None if object_literal is None else canonical_json(object_literal)
        )
        desired_literal_type = object_literal_type or _literal_type(object_literal)
        for row in rows:
            if (
                row["object_node_id"] == object_node_id
                and row["object_literal_json"] == desired_literal
                and (
                    object_literal is None
                    or row["object_literal_type"] == desired_literal_type
                )
            ):
                continue
            return str(row["assertion_id"])
        return None

    def _ensure_compat_node(self, node_id: str, now: str) -> None:
        properties: dict[str, object] = {"compat_placeholder": True}
        configured_elfie = getattr(self, "elfie_id", None)
        if configured_elfie is not None:
            properties["elfie_id"] = str(configured_elfie)
            existing = self.conn.execute(
                "SELECT properties_json FROM nodes WHERE node_id=?", (node_id,)
            ).fetchone()
            if existing is not None:
                existing_properties = json_object(existing["properties_json"])
                existing_elfie = existing_properties.get("elfie_id")
                if existing_elfie is None:
                    raise ValueError(
                        "Node belongs to an unbound namespace and cannot be reused"
                    )
                if str(existing_elfie) != str(configured_elfie):
                    raise ValueError("Node belongs to a different Elfie namespace")
        self.conn.execute(
            """INSERT OR IGNORE INTO nodes (
                   node_id, node_type, canonical_label, normalized_label,
                   confidence, properties_json, first_seen_at, last_seen_at, updated_at
               ) VALUES (?, 'entity', ?, ?, 0.5, ?, ?, ?, ?)""",
            (
                node_id,
                node_id,
                normalize_text(node_id),
                canonical_json(properties),
                now,
                now,
                now,
            ),
        )


def _assertion_base(assertion: AssertionInput) -> str:
    object_value = (
        f"node:{assertion.object_node_id}"
        if assertion.object_node_id is not None
        else "|".join(
            (
                "literal",
                assertion.object_literal_type
                or _literal_type(assertion.object_literal)
                or "json",
                canonical_json(assertion.object_literal),
            )
        )
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
        importance=bounded_score(row["importance"]),
        object_literal_type=row["object_literal_type"],
        predicate_registry_version=str(
            row["predicate_registry_version"] or "memory.predicates.v1"
        ),
        policy_version=str(row["policy_version"] or "memory.v1"),
        genesis_submission_id=row["genesis_submission_id"],
    )


def _row_to_assertion(row: sqlite3.Row) -> RecallAssertion:
    literal = None
    if row["object_literal_json"] is not None:
        literal = json.loads(row["object_literal_json"])
    qualifiers = {
        key: row[key]
        for key in (
            "object_unit",
            "object_literal_type",
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
        relevance=float(row["importance"]),
        importance=float(row["importance"]),
        confidence=float(row["confidence"]),
    )


def _literal_type(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    return "json"


def _projection_revision(projection: ConsolidationProjection) -> str:
    payload = {
        "episode_id": projection.episode_id,
        "source_version": projection.source_version,
        "source_sha256": projection.source_sha256,
        "nodes": [
            {
                "node_id": node.node_id,
                "node_type": node.node_type,
                "label": node.canonical_label,
                "description": node.description,
                "scope": node.scope,
                "status": node.status,
                "confidence": node.confidence,
                "importance": node.importance,
                "properties": dict(node.properties),
            }
            for node in projection.nodes
        ],
        "aliases": [
            {
                "node_id": alias.node_id,
                "alias": alias.alias,
                "scope": alias.scope,
                "evidence_id": alias.evidence_id,
                "confidence": alias.confidence,
            }
            for alias in projection.aliases
        ],
        "descriptions": [
            {
                "node_id": description.node_id,
                "text": description.text,
                "language": description.language,
                "kind": description.kind,
                "evidence_id": description.evidence_id,
                "confidence": description.confidence,
            }
            for description in projection.descriptions
        ],
        "mentions": [
            {
                "episode_id": mention.episode_id,
                "surface_text": mention.surface_text,
                "node_id": mention.node_id,
                "resolution_state": mention.resolution_state,
                "role": mention.role,
                "span_start": mention.span_start,
                "span_end": mention.span_end,
                "confidence": mention.confidence,
            }
            for mention in projection.mentions
        ],
        "assertions": [
            {
                "id": assertion.assertion_id or _assertion_fingerprint(assertion),
                "subject_id": assertion.subject_id,
                "predicate": assertion.predicate,
                "object_node_id": assertion.object_node_id,
                "object_literal": assertion.object_literal,
                "object_unit": assertion.object_unit,
                "polarity": assertion.polarity,
                "epistemic_status": assertion.epistemic_status,
                "viewpoint": assertion.viewpoint,
                "context": assertion.context,
                "valid_from": assertion.valid_from,
                "valid_to": assertion.valid_to,
                "confidence": assertion.confidence,
                "importance": assertion.importance,
                "support_score": assertion.support_score,
                "conflict_group": assertion.conflict_group,
                "supersedes_assertion_id": assertion.supersedes_assertion_id,
                "evidence_ids": list(assertion.evidence_ids),
                "object_literal_type": assertion.object_literal_type,
                "predicate_registry_version": assertion.predicate_registry_version,
                "policy_version": assertion.policy_version,
                "genesis_submission_id": assertion.genesis_submission_id,
            }
            for assertion in projection.assertions
        ],
        "evidence": [
            {
                "evidence_id": evidence.evidence_id,
                "source_type": evidence.source_type,
                "source_id": evidence.source_id,
                "excerpt": evidence.excerpt,
                "media_locator": evidence.media_locator,
                "modality": evidence.modality,
                "span_start": evidence.span_start,
                "span_end": evidence.span_end,
                "speaker": evidence.speaker,
                "viewpoint": evidence.viewpoint,
                "captured_at": evidence.captured_at,
                "extraction_run_id": evidence.extraction_run_id,
                "source_sha256": evidence.source_sha256,
                "source_version": evidence.source_version,
                "attribution": evidence.attribution,
                "genesis_submission_id": evidence.genesis_submission_id,
            }
            for evidence in projection.evidence
        ],
        "assertion_evidence": [
            {
                "assertion_id": link.assertion_id,
                "evidence_id": link.evidence_id,
                "stance": link.stance,
            }
            for link in projection.assertion_evidence
        ],
        "extraction_run_id": projection.extraction_run_id,
    }
    return (
        "projection:"
        + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    )


def _episode_facet_conditions(
    *,
    person_node_ids: Iterable[str],
    place_node_ids: Iterable[str],
    emotion_labels: Iterable[str],
    topic_labels: Iterable[str],
    cause_labels: Iterable[str],
    privacy_scope: str | None,
) -> tuple[list[str], list[Any]]:
    """Build positive AND-across-family/OR-within-family source filters."""
    conditions: list[str] = []
    params: list[Any] = []
    for node_type, values, _label in (
        ("person", tuple(dict.fromkeys(person_node_ids)), "person"),
        ("place", tuple(dict.fromkeys(place_node_ids)), "place"),
    ):
        if values:
            placeholders = ",".join("?" for _ in values)
            conditions.append(
                "EXISTS (SELECT 1 FROM episode_mentions AS fm "
                "JOIN nodes AS fn ON fn.node_id=fm.node_id "
                "WHERE fm.episode_id=p.episode_id AND fm.node_id IN ("
                + placeholders
                + ") AND fn.node_type=? AND fm.resolution_state='resolved')"
            )
            params.extend(values)
            params.append(node_type)
    if emotion_labels:
        values = tuple(dict.fromkeys(str(item).casefold() for item in emotion_labels))
        placeholders = ",".join("?" for _ in values)
        conditions.append(
            "lower(COALESCE(json_extract(p.metadata_json, '$.emotion'), '')) IN ("
            + placeholders
            + ")"
        )
        params.extend(values)
    for raw_values, column in (
        (topic_labels, "topic"),
        (cause_labels, "cause"),
    ):
        normalized = tuple(dict.fromkeys(str(item).casefold() for item in raw_values))
        if normalized:
            conditions.append(
                "("
                + " OR ".join(
                    "lower(COALESCE(json_extract(p.metadata_json, '$."
                    + column
                    + "'), '')) LIKE ?"
                    for _ in normalized
                )
                + ")"
            )
            params.extend("%" + value + "%" for value in normalized)
    if privacy_scope is not None:
        conditions.append("p.privacy_scope=?")
        params.append(privacy_scope)
    return conditions, params


__all__ = ["SQLiteGraphStoreMixin"]
