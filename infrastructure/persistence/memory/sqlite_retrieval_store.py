"""Bounded deterministic hybrid retrieval for the SQLite Memory adapter."""

from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from threading import Lock
from time import perf_counter
from typing import Iterable, Mapping, cast

from elfie.brain.memory.memory_records import (
    KinshipQuery,
    OccurrencePrecision,
    RecallAssertion,
    RecallBundle,
    RecallConflict,
    RecallEpisode,
    RecallLimits,
    RecallNode,
    RecallPath,
    RecallRequest,
    RecallSense,
)
from elfie.brain.memory.observation_payloads import (
    RecallCandidateScored,
    RecallSelectionSummary,
)
from elfie.brain.memory.score_policy import MemoryScorePolicy
from elfie.brain.observation import (
    BrainObservation,
    BrainObservationSink,
    ObservationStatus,
)

from .sqlite_mixin_base import SQLiteMemoryMixinBase
from .sqlite_utils import normalize_text, normalized_tokens, utc_now

_RECALL_SELECTION_BOUNDARY = "memory.recall.selection"
# Two matching Chinese bigrams in a six-term question are a meaningful
# phrase, even though their exact coverage is 1/3.  Keep the floor at that
# boundary so a relevant phrase is not dropped for a rounding-sized margin;
# incidental single-term matches in the existing recall contract remain below
# it.
_MIN_TERM_COVERAGE = 1.0 / 3.0
_LEXICAL_QUESTION_TERMS = frozenset(
    {
        "什么",
        "一个",
        "问题",
        "记得",
        "之前",
        "以前",
        "说过",
        "好吗",
    }
)


@dataclass(frozen=True)
class _LexicalHit:
    record_kind: str
    record_id: str
    searchable_text: str
    score: float
    bm25_rank: float
    exact_alias: bool = False
    distinctive_match: bool = False
    sense_score: float = 0.0


@dataclass(frozen=True)
class _LexicalSearchResult:
    hits: tuple[_LexicalHit, ...]
    truncated: bool = False


class SQLiteRecallStoreMixin(SQLiteMemoryMixinBase):
    """Run lexical source search followed by a bounded local graph walk."""

    conn: sqlite3.Connection
    _observation_sink: BrainObservationSink | None
    _recall_observation_sequence: int
    _recall_observation_lock: Lock

    def _next_recall_observation_sequence(self) -> int:
        with self._recall_observation_lock:
            self._recall_observation_sequence += 1
            return self._recall_observation_sequence

    def _emit_recall_candidate_scored(
        self,
        *,
        recall_id: str | None,
        query_terms: tuple[str, ...],
        candidate_id: str,
        candidate_kind: str,
        score: float,
        matched_terms: tuple[str, ...],
        kept: bool,
        exclusion_reason: str | None,
    ) -> None:
        sink = self._observation_sink
        if sink is None:
            return
        sink.emit(
            BrainObservation[RecallCandidateScored](
                boundary=_RECALL_SELECTION_BOUNDARY,
                kind="candidate_scored",
                sequence=self._next_recall_observation_sequence(),
                captured_at=datetime.now(timezone.utc),
                # Storage holds no causal context; frame correlation lives
                # on the bridge's recall_started/recall_result pair.
                turn_id="",
                frame_id="",
                cause_event_ids=(),
                duration_ms=0.0,
                status=ObservationStatus.completed,
                payload=RecallCandidateScored(
                    recall_id=recall_id,
                    query_terms=query_terms,
                    candidate_id=candidate_id,
                    candidate_kind=candidate_kind,
                    score=score,
                    matched_terms=matched_terms,
                    kept=kept,
                    exclusion_reason=exclusion_reason,
                ),
            )
        )

    def _emit_recall_selection_summary(
        self,
        *,
        recall_id: str | None,
        candidates_seen: int,
        kept: int,
        truncated: bool,
        character_budget_used: int,
        character_budget_limit: int,
        request: RecallRequest,
        duration_ms: float = 0.0,
    ) -> None:
        sink = self._observation_sink
        if sink is None:
            return
        sink.emit(
            BrainObservation[RecallSelectionSummary](
                boundary=_RECALL_SELECTION_BOUNDARY,
                kind="selection_summary",
                sequence=self._next_recall_observation_sequence(),
                captured_at=datetime.now(timezone.utc),
                turn_id="",
                frame_id="",
                cause_event_ids=(),
                duration_ms=duration_ms,
                status=ObservationStatus.completed,
                payload=RecallSelectionSummary(
                    recall_id=recall_id,
                    candidates_seen=candidates_seen,
                    kept=kept,
                    truncated=truncated,
                    character_budget_used=character_budget_used,
                    character_budget_limit=character_budget_limit,
                    assertion_limit=request.assertion_limit,
                    episode_limit=request.episode_limit,
                    node_limit=request.node_limit,
                    seed_limit=request.seed_limit,
                ),
            )
        )

    def search_text(
        self,
        query: str,
        top_k: int = 5,
        node_type: str | None = None,
        *,
        privacy_scope: str | None = None,
        recall_id: str | None = None,
    ) -> list[tuple[str, float]]:
        """Run bounded FTS5/BM25 retrieval over Episodes and graph records."""
        result = self._search_fts_candidates(
            query,
            top_k,
            node_type=node_type,
            privacy_scope=privacy_scope,
            recall_id=recall_id,
        )
        return [(hit.record_id, hit.score) for hit in result.hits]

    def _search_fts_candidates(
        self,
        query: str,
        top_k: int,
        *,
        node_type: str | None = None,
        privacy_scope: str | None = None,
        recall_id: str | None = None,
        request: RecallRequest | None = None,
    ) -> _LexicalSearchResult:
        """Search each typed corpus with filters pushed ahead of its FTS cap."""
        if top_k < 1 or not query.strip():
            return _LexicalSearchResult(())
        terms = _lexical_search_terms(query)
        match_expression = " OR ".join(f'"{term}"' for term in terms)
        if not terms or not match_expression:
            return _LexicalSearchResult(())
        candidate_limit = max(512, min(4096, top_k * 64))
        raw_candidates: list[tuple[str, str, str, float]] = []
        candidate_pool_truncated = False
        requested_kinds = (
            set(request.record_kinds)
            if request is not None and request.record_kinds
            else {"episode", "node", "assertion"}
        )
        if node_type == "episodic":
            requested_kinds &= {"episode"}
        elif node_type is not None:
            requested_kinds &= {"node"}

        def fetch(
            kind: str, from_sql: str, conditions: list[str], params: list[object]
        ) -> None:
            nonlocal candidate_pool_truncated
            if kind not in requested_kinds:
                return
            rows = self.conn.execute(
                "SELECT f.record_id, f.normalized_text, "
                "bm25(memory_search_fts) AS bm25_rank "
                "FROM memory_search_fts AS f "
                + from_sql
                + " WHERE memory_search_fts MATCH ? AND f.record_kind=? AND "
                + " AND ".join(conditions)
                + " ORDER BY bm25(memory_search_fts), f.record_id LIMIT ?",
                [match_expression, kind, *params, candidate_limit + 1],
            ).fetchall()
            if len(rows) > candidate_limit:
                candidate_pool_truncated = True
                rows = rows[:candidate_limit]
            raw_candidates.extend(
                (kind, str(row[0]), str(row[1]), float(row[2])) for row in rows
            )

        with self._lock:
            if "episode" in requested_kinds:
                episode_conditions = [
                    "e.lifecycle='active'",
                    _episode_recall_eligibility("e"),
                ]
                episode_params: list[object] = []
                if getattr(self, "elfie_id", None) is not None:
                    episode_conditions.append(
                        "json_extract(e.metadata_json, '$.elfie_id')=?"
                    )
                    episode_params.append(str(self.elfie_id))
                if privacy_scope is not None:
                    episode_conditions.append("e.privacy_scope=?")
                    episode_params.append(privacy_scope)
                if request is not None:
                    if request.minimum_importance is not None:
                        episode_conditions.append("e.importance>=?")
                        episode_params.append(request.minimum_importance)
                    time_conditions, time_params = _episode_time_conditions(
                        request, "e"
                    )
                    facet_conditions, facet_params = (
                        _episode_facet_conditions_for_alias(request, "e")
                    )
                    episode_conditions.extend(time_conditions + facet_conditions)
                    episode_params.extend(time_params + facet_params)
                episode_visibility, episode_visibility_params = (
                    self._genesis_visibility("e")
                )
                episode_conditions.append(episode_visibility)
                episode_params.extend(episode_visibility_params)
                fetch(
                    "episode",
                    "JOIN episodes AS e ON e.episode_id=f.record_id",
                    episode_conditions,
                    episode_params,
                )

            if "node" in requested_kinds:
                node_conditions = [
                    "n.status IN ('active', 'candidate', 'unresolved')",
                    "n.merged_into IS NULL",
                    "COALESCE(json_extract(n.properties_json, '$.recall_eligible'), 1) <> 0",
                ]
                node_params = []
                if getattr(self, "elfie_id", None) is not None:
                    node_conditions.append(
                        "json_extract(n.properties_json, '$.elfie_id')=?"
                    )
                    node_params.append(str(self.elfie_id))
                if privacy_scope is not None:
                    node_conditions.append("n.privacy_scope=?")
                    node_params.append(privacy_scope)
                if request is not None:
                    if request.node_types:
                        node_conditions.append(
                            "n.node_type IN ("
                            + ",".join("?" for _ in request.node_types)
                            + ")"
                        )
                        node_params.extend(request.node_types)
                    if request.minimum_importance is not None:
                        node_conditions.append("n.importance>=?")
                        node_params.append(request.minimum_importance)
                if node_type is not None:
                    node_conditions.append("n.node_type=?")
                    node_params.append(node_type)
                node_visibility, node_visibility_params = self._genesis_visibility("n")
                node_conditions.append(node_visibility)
                node_params.extend(node_visibility_params)
                fetch(
                    "node",
                    "JOIN nodes AS n ON n.node_id=f.record_id",
                    node_conditions,
                    node_params,
                )

            if "assertion" in requested_kinds:
                assertion_conditions = [
                    "a.lifecycle IN ('active', 'superseded')",
                    "NOT (a.predicate IN ('knows', 'knows_boundary') "
                    "AND a.subject_node_id LIKE 'genesis:self:%' "
                    "AND a.object_node_id LIKE 'genesis:knowledge:%')",
                    "EXISTS (SELECT 1 FROM nodes AS rs WHERE rs.node_id=a.subject_node_id "
                    "AND COALESCE(json_extract(rs.properties_json, '$.recall_eligible'), 1)<>0)",
                    "(a.object_node_id IS NULL OR EXISTS (SELECT 1 FROM nodes AS ro "
                    "WHERE ro.node_id=a.object_node_id "
                    "AND COALESCE(json_extract(ro.properties_json, '$.recall_eligible'), 1)<>0))",
                ]
                assertion_params: list[object] = []
                endpoint_conditions = ["subject_node.node_id=a.subject_node_id"]
                if getattr(self, "elfie_id", None) is not None:
                    endpoint_conditions.append(
                        "json_extract(subject_node.properties_json, '$.elfie_id')=?"
                    )
                    assertion_params.append(str(self.elfie_id))
                if privacy_scope is not None:
                    endpoint_conditions.append("subject_node.privacy_scope=?")
                    assertion_params.append(privacy_scope)
                assertion_conditions.append(
                    "EXISTS (SELECT 1 FROM nodes AS subject_node WHERE "
                    + " AND ".join(endpoint_conditions)
                    + ")"
                )
                object_conditions = ["object_node.node_id=a.object_node_id"]
                if getattr(self, "elfie_id", None) is not None:
                    object_conditions.append(
                        "json_extract(object_node.properties_json, '$.elfie_id')=?"
                    )
                    assertion_params.append(str(self.elfie_id))
                if privacy_scope is not None:
                    object_conditions.append("object_node.privacy_scope=?")
                    assertion_params.append(privacy_scope)
                assertion_conditions.append(
                    "(a.object_node_id IS NULL OR EXISTS (SELECT 1 FROM nodes AS object_node WHERE "
                    + " AND ".join(object_conditions)
                    + "))"
                )
                if request is not None:
                    if request.relation_types:
                        assertion_conditions.append(
                            "a.predicate IN ("
                            + ",".join("?" for _ in request.relation_types)
                            + ")"
                        )
                        assertion_params.extend(request.relation_types)
                    if request.minimum_importance is not None:
                        assertion_conditions.append("a.importance>=?")
                        assertion_params.append(request.minimum_importance)
                    if request.node_types:
                        type_placeholders = ",".join("?" for _ in request.node_types)
                        assertion_conditions.append(
                            "(EXISTS (SELECT 1 FROM nodes AS st WHERE "
                            "st.node_id=a.subject_node_id AND st.node_type IN ("
                            + type_placeholders
                            + ")) OR EXISTS (SELECT 1 FROM nodes AS ot WHERE "
                            "ot.node_id=a.object_node_id AND ot.node_type IN ("
                            + type_placeholders
                            + ")))"
                        )
                        assertion_params.extend(request.node_types)
                        assertion_params.extend(request.node_types)
                    if _has_episode_filters(request):
                        source_conditions = [
                            "ep.lifecycle='active'",
                            _episode_recall_eligibility("ep"),
                        ]
                        source_params: list[object] = []
                        if request.privacy_scope is not None:
                            source_conditions.append("ep.privacy_scope=?")
                            source_params.append(request.privacy_scope)
                        source_time, source_time_params = _episode_time_conditions(
                            request, "ep"
                        )
                        source_facets, source_facet_params = (
                            _episode_facet_conditions_for_alias(request, "ep")
                        )
                        source_conditions.extend(source_time + source_facets)
                        source_params.extend(source_time_params + source_facet_params)
                        assertion_conditions.append(
                            "EXISTS (SELECT 1 FROM assertion_evidence AS sae "
                            "JOIN evidence AS se ON se.evidence_id=sae.evidence_id "
                            "JOIN episodes AS ep ON ep.episode_id=se.source_id "
                            "WHERE sae.assertion_id=a.assertion_id "
                            "AND se.source_type='episode' AND "
                            + " AND ".join(source_conditions)
                            + ")"
                        )
                        assertion_params.extend(source_params)
                assertion_visibility, assertion_visibility_params = (
                    self._genesis_visibility("a")
                )
                assertion_conditions.append(assertion_visibility)
                assertion_params.extend(assertion_visibility_params)
                fetch(
                    "assertion",
                    "JOIN assertions AS a ON a.assertion_id=f.record_id",
                    assertion_conditions,
                    assertion_params,
                )

            alias_visibility, alias_visibility_params = self._genesis_visibility("n")
            exact_alias_ids = {
                str(row[0])
                for row in self.conn.execute(
                    """SELECT DISTINCT n.node_id FROM nodes AS n
                       LEFT JOIN node_aliases AS a ON a.node_id=n.node_id
                       WHERE (n.normalized_label=? OR a.normalized_alias=?)
                         AND n.status IN ('active', 'candidate', 'unresolved')
                         AND n.merged_into IS NULL
                         AND COALESCE(json_extract(n.properties_json, '$.recall_eligible'), 1)<>0"""
                    + (
                        " AND json_extract(n.properties_json, '$.elfie_id')=?"
                        if getattr(self, "elfie_id", None) is not None
                        else ""
                    )
                    + (" AND n.privacy_scope=?" if privacy_scope is not None else "")
                    + " AND "
                    + alias_visibility,
                    [
                        normalize_text(query),
                        normalize_text(query),
                        *(
                            [str(self.elfie_id)]
                            if getattr(self, "elfie_id", None) is not None
                            else []
                        ),
                        *([privacy_scope] if privacy_scope is not None else []),
                        *alias_visibility_params,
                    ],
                ).fetchall()
            }

        scored: list[_LexicalHit] = []
        sense_scores = (
            self._sense_scores_for_ids(
                request.sense,
                (
                    identifier
                    for kind, identifier, _text, _rank in raw_candidates
                    if kind == "episode"
                ),
                request,
            )
            if request is not None and request.sense is not None
            else {}
        )
        matched_by_key: dict[tuple[str, str], tuple[str, ...]] = {}
        for kind, identifier, text, bm25_rank in raw_candidates:
            normalized = _lexical_normalize(text)
            if not normalized:
                continue
            searchable_terms = set(normalized.split())
            matched = tuple(term for term in terms if term in searchable_terms)
            if not matched:
                continue
            score = len(matched) / len(terms)
            exact_alias = kind == "node" and identifier in exact_alias_ids
            distinctive_match = any(
                _is_distinctive_query_term(term) for term in matched
            )
            matched_by_key[(kind, identifier)] = matched
            scored.append(
                _LexicalHit(
                    record_kind=kind,
                    record_id=identifier,
                    searchable_text=text,
                    score=score,
                    bm25_rank=bm25_rank,
                    exact_alias=exact_alias,
                    distinctive_match=distinctive_match,
                    sense_score=sense_scores.get(identifier, 0.0)
                    if kind == "episode"
                    else 0.0,
                )
            )
        filtered = [
            item
            for item in scored
            if item.exact_alias
            or item.distinctive_match
            or item.score >= _MIN_TERM_COVERAGE
        ]
        text_ordered = sorted(
            filtered,
            key=lambda item: (
                0 if item.exact_alias else 1,
                -item.score,
                item.bm25_rank,
                item.record_kind,
                item.record_id,
            ),
        )
        # Freeze the Query pool before applying Sense. Emotion may only order
        # equally relevant Query matches; it cannot admit or displace a hit.
        query_pool = text_ordered[:top_k]
        result = sorted(
            query_pool,
            key=lambda item: (
                0 if item.exact_alias else 1,
                -item.score,
                -item.sense_score,
                item.bm25_rank,
                item.record_kind,
                item.record_id,
            ),
        )
        sink = self._observation_sink
        if sink is not None:
            kept_keys = {(item.record_kind, item.record_id) for item in result}
            for item in scored:
                key = (item.record_kind, item.record_id)
                if key in kept_keys:
                    exclusion_reason = None
                elif (
                    item.score < _MIN_TERM_COVERAGE
                    and not item.exact_alias
                    and not item.distinctive_match
                ):
                    exclusion_reason = "score_below_floor"
                else:
                    exclusion_reason = "ranked_out_of_top_k"
                self._emit_recall_candidate_scored(
                    recall_id=recall_id,
                    query_terms=tuple(terms),
                    candidate_id=item.record_id,
                    candidate_kind=item.record_kind,
                    score=item.score,
                    matched_terms=matched_by_key.get(key, ()),
                    kept=exclusion_reason is None,
                    exclusion_reason=exclusion_reason,
                )
        return _LexicalSearchResult(
            tuple(result),
            truncated=candidate_pool_truncated or len(filtered) > top_k,
        )

    def _sense_scores_for_ids(
        self,
        sense: RecallSense,
        episode_ids: Iterable[str],
        request: RecallRequest,
    ) -> dict[str, float]:
        """Score only sourced, self-attributed historical affect on query hits."""
        ids = tuple(dict.fromkeys(episode_ids))
        if not ids:
            return {}
        result: dict[str, float] = {}
        for start in range(0, len(ids), 400):
            chunk = ids[start : start + 400]
            placeholders = ",".join("?" for _ in chunk)
            conditions = [
                f"e.episode_id IN ({placeholders})",
                "e.lifecycle='active'",
                "e.attribution='felt'",
                "lower(COALESCE(json_extract(e.metadata_json, '$.emotion'),''))=?",
                "json_array_length(e.source_refs_json)>0",
                _episode_recall_eligibility("e"),
            ]
            params: list[object] = [*chunk, sense.emotion_label]
            if getattr(self, "elfie_id", None) is not None:
                conditions.append("json_extract(e.metadata_json, '$.elfie_id')=?")
                params.append(str(self.elfie_id))
            if request.privacy_scope is not None:
                conditions.append("e.privacy_scope=?")
                params.append(request.privacy_scope)
            if request.minimum_importance is not None:
                conditions.append("e.importance>=?")
                params.append(request.minimum_importance)
            time_conditions, time_params = _episode_time_conditions(request, "e")
            facet_conditions, facet_params = _episode_facet_conditions_for_alias(
                request, "e"
            )
            conditions.extend(time_conditions + facet_conditions)
            params.extend(time_params + facet_params)
            visibility, visibility_params = self._genesis_visibility("e")
            conditions.append(visibility)
            params.extend(visibility_params)
            with self._lock:
                rows = self.conn.execute(
                    "SELECT e.episode_id, json_extract(e.metadata_json, "
                    "'$.emotion_intensity') AS intensity FROM episodes AS e WHERE "
                    + " AND ".join(conditions),
                    params,
                ).fetchall()
            for row in rows:
                historical = row["intensity"]
                score = 0.5
                if sense.intensity is not None and historical is not None:
                    delta = abs(float(historical) - sense.intensity)
                    if delta > 0.25:
                        continue
                    score = 1.0 - delta
                result[str(row["episode_id"])] = score
        return result

    def _sense_episode_candidates(self, request: RecallRequest) -> dict[str, float]:
        """Return at most one sourced Episode for a Sense-only request."""
        sense = request.sense
        if sense is None or (
            request.record_kinds and "episode" not in request.record_kinds
        ):
            return {}
        conditions = [
            "e.lifecycle='active'",
            "e.attribution='felt'",
            "lower(COALESCE(json_extract(e.metadata_json, '$.emotion'),''))=?",
            "json_array_length(e.source_refs_json)>0",
            _episode_recall_eligibility("e"),
        ]
        params: list[object] = [sense.emotion_label]
        if sense.intensity is not None:
            conditions.append(
                "(json_extract(e.metadata_json, '$.emotion_intensity') IS NULL OR "
                "ABS(CAST(json_extract(e.metadata_json, '$.emotion_intensity') "
                "AS REAL)-?)<=0.25)"
            )
            params.append(sense.intensity)
        if getattr(self, "elfie_id", None) is not None:
            conditions.append("json_extract(e.metadata_json, '$.elfie_id')=?")
            params.append(str(self.elfie_id))
        if request.privacy_scope is not None:
            conditions.append("e.privacy_scope=?")
            params.append(request.privacy_scope)
        if request.minimum_importance is not None:
            conditions.append("e.importance>=?")
            params.append(request.minimum_importance)
        time_conditions, time_params = _episode_time_conditions(request, "e")
        facet_conditions, facet_params = _episode_facet_conditions_for_alias(
            request, "e"
        )
        conditions.extend(time_conditions + facet_conditions)
        params.extend(time_params + facet_params)
        visibility, visibility_params = self._genesis_visibility("e")
        conditions.append(visibility)
        params.extend(visibility_params)
        order = "e.occurred_from DESC, e.episode_id"
        if sense.intensity is not None:
            order = (
                "CASE WHEN json_extract(e.metadata_json, '$.emotion_intensity') "
                "IS NULL THEN 1 ELSE 0 END, "
                "ABS(CAST(json_extract(e.metadata_json, '$.emotion_intensity') "
                "AS REAL)-?), e.occurred_from DESC, e.episode_id"
            )
            params.append(sense.intensity)
        with self._lock:
            rows = self.conn.execute(
                "SELECT e.episode_id, json_extract(e.metadata_json, "
                "'$.emotion_intensity') AS intensity FROM episodes AS e WHERE "
                + " AND ".join(conditions)
                + " ORDER BY "
                + order
                + " LIMIT 1",
                params,
            ).fetchall()
        if not rows:
            return {}
        historical = rows[0]["intensity"]
        score = 0.5
        if sense.intensity is not None and historical is not None:
            delta = abs(float(historical) - sense.intensity)
            if delta > 0.25:
                return {}
            score = 1.0 - delta
        return {str(rows[0]["episode_id"]): score}

    def _recall_sense_only(self, request: RecallRequest, *, now: str) -> RecallBundle:
        episode_scores = self._sense_episode_candidates(request)
        episodes, episodes_truncated = self._episodes_for_recall(
            episode_scores,
            episode_scores,
            request,
            now=now,
            primary_episode_ids=episode_scores,
        )
        returned = {
            "nodes": 0,
            "assertions": 0,
            "paths": 0,
            "episodes": len(episodes),
            "evidence": 0,
        }
        bundle = RecallBundle(
            episodes=episodes,
            status="partial" if episodes_truncated else "complete",
            notices=("no_sourced_emotion_match",) if not episodes else (),
            limits=RecallLimits(
                requested={
                    "lexical": request.lexical_limit,
                    "seeds": request.seed_limit,
                    "nodes": request.node_limit,
                    "assertions": request.assertion_limit,
                    "episodes": min(1, request.episode_limit),
                    "evidence": request.evidence_limit,
                    "characters": request.character_limit,
                },
                returned=returned,
                truncated=episodes_truncated,
            ),
        )
        return _bound_bundle(bundle, request.character_limit)

    def _recall_kinship(
        self,
        request: RecallRequest,
        kinship: KinshipQuery,
        *,
        now: str,
    ) -> RecallBundle:
        if request.record_kinds and "assertion" not in request.record_kinds:
            return RecallBundle(
                status="unsupported",
                notices=("kinship_requires_assertion_records",),
            )
        anchor_id = self.resolve_graph_node_id(kinship.anchor_node_id or "")
        if kinship.anchor_name is not None:
            normalized = normalize_text(kinship.anchor_name)
            visibility, visibility_params = self._genesis_visibility("n")
            clauses = [
                "(n.normalized_label=? OR a.normalized_alias=?)",
                "n.status IN ('active', 'candidate')",
                "n.merged_into IS NULL",
                "COALESCE(json_extract(n.properties_json, '$.recall_eligible'), 1)<>0",
                visibility,
            ]
            params: list[object] = [normalized, normalized, *visibility_params]
            if getattr(self, "elfie_id", None) is not None:
                clauses.append("json_extract(n.properties_json, '$.elfie_id')=?")
                params.append(str(self.elfie_id))
            if request.privacy_scope is not None:
                clauses.append("n.privacy_scope=?")
                params.append(request.privacy_scope)
            with self._lock:
                rows = self.conn.execute(
                    "SELECT DISTINCT n.node_id FROM nodes AS n "
                    "LEFT JOIN node_aliases AS a ON a.node_id=n.node_id WHERE "
                    + " AND ".join(clauses)
                    + " ORDER BY n.node_id LIMIT 3",
                    params,
                ).fetchall()
            anchor_ids = tuple(str(row[0]) for row in rows)
            if len(anchor_ids) != 1:
                status = "ambiguous" if anchor_ids else "partial"
                notice = (
                    "kinship_anchor_ambiguous"
                    if anchor_ids
                    else "kinship_anchor_not_found"
                )
                return RecallBundle(status=status, notices=(notice,))
            anchor_id = anchor_ids[0]
        if anchor_id is None:
            return RecallBundle(status="partial", notices=("kinship_anchor_not_found",))
        anchor = self.get_graph_node(
            anchor_id,
            privacy_scope=request.privacy_scope,
            now=now,
        )
        if anchor is None:
            return RecallBundle(status="partial", notices=("kinship_anchor_not_found",))
        if (
            not _recall_eligible(anchor)
            or self.ontology.group_for_node_type(anchor.node_type) != "social_relations"
        ):
            return RecallBundle(
                status="unsupported", notices=("kinship_anchor_not_person",)
            )

        relations = {
            "parents": ("parent_of", "child_of"),
            "children": ("parent_of", "child_of"),
            "siblings": ("sibling_of",),
        }[kinship.relation]
        if request.relation_types:
            relations = tuple(
                relation for relation in relations if relation in request.relation_types
            )
        candidate_limit = min(
            800,
            max(request.assertion_limit + 1, request.assertion_limit * 4),
        )
        candidates = (
            self.graph_assertions_for(
                (anchor_id,),
                relation_types=relations,
                limit=candidate_limit,
                minimum_importance=request.minimum_importance,
                occurred_from=request.occurred_from,
                occurred_to=request.occurred_to,
                person_node_ids=request.person_node_ids,
                place_node_ids=request.place_node_ids,
                emotion_labels=request.emotion_labels,
                topic_labels=request.topic_labels,
                cause_labels=request.cause_labels,
                privacy_scope=request.privacy_scope,
                include_unknown_time=request.include_unknown_time,
                recall_eligible_only=True,
                now=now,
            )
            if request.assertion_limit > 0 and relations
            else ()
        )
        selected: list[RecallAssertion] = []
        for assertion in candidates:
            if kinship.relation == "parents":
                follows = (
                    assertion.predicate == "parent_of"
                    and assertion.object_node_id == anchor_id
                ) or (
                    assertion.predicate == "child_of"
                    and assertion.subject_id == anchor_id
                )
            elif kinship.relation == "children":
                follows = (
                    assertion.predicate == "parent_of"
                    and assertion.subject_id == anchor_id
                ) or (
                    assertion.predicate == "child_of"
                    and assertion.object_node_id == anchor_id
                )
            else:
                follows = assertion.predicate == "sibling_of" and anchor_id in (
                    assertion.subject_id,
                    assertion.object_node_id,
                )
            if follows:
                selected.append(assertion)
        selected.sort(
            key=lambda item: (
                item.subject_id,
                item.object_node_id or "",
                item.assertion_id,
            )
        )
        assertions_truncated = len(selected) > request.assertion_limit or bool(
            candidate_limit and len(candidates) >= candidate_limit
        )
        selected = selected[: request.assertion_limit]
        related_ids = tuple(
            dict.fromkeys(
                node_id
                for assertion in selected
                for node_id in (assertion.subject_id, assertion.object_node_id)
                if node_id is not None
            )
        )
        focus_nodes = self._focus_nodes(
            (anchor_id, *related_ids),
            {anchor_id: 1.0},
            request,
            now=now,
            primary_node_ids=(),
        )
        assertions_tuple = tuple(
            replace(item, relevance=1.0, role="primary") for item in selected
        )
        paths = tuple(
            RecallPath(
                node_ids=(item.subject_id, item.object_node_id),
                assertion_ids=(item.assertion_id,),
                hop_count=1,
            )
            for item in selected
            if item.status == "active"
            and item.object_node_id is not None
            and item.qualifiers.get("polarity", "positive") == "positive"
        )
        evidence_candidates = self.get_assertion_evidence(
            (item.assertion_id for item in assertions_tuple),
            request.evidence_limit + 1 if request.evidence_limit > 0 else 0,
            privacy_scope=request.privacy_scope,
        )
        evidence_truncated = len(evidence_candidates) > request.evidence_limit
        evidence = evidence_candidates[: request.evidence_limit]
        source_ids = tuple(item.source_id for item in evidence if item.source_id)
        source_scores = dict.fromkeys(source_ids, 0.7)
        episodes, episodes_truncated = self._episodes_for_recall(
            source_ids,
            source_scores,
            request,
            now=now,
            primary_episode_ids=(),
        )
        conflicts = self._conflicts(assertions_tuple)
        truncated = any((assertions_truncated, evidence_truncated, episodes_truncated))
        notices: tuple[str, ...] = ()
        status = "partial" if truncated else "complete"
        if not selected:
            status = "partial"
            notices = ("no_recorded_kinship_edge_absence_not_established",)
        elif truncated:
            notices = ("kinship_results_truncated",)
        bundle = RecallBundle(
            focus_nodes=focus_nodes,
            assertions=assertions_tuple,
            paths=paths[: request.node_limit],
            episodes=episodes,
            evidence=evidence,
            conflicts=conflicts,
            status=status,
            notices=notices,
            limits=RecallLimits(
                requested={
                    "lexical": request.lexical_limit,
                    "seeds": request.seed_limit,
                    "nodes": request.node_limit,
                    "assertions": request.assertion_limit,
                    "episodes": request.episode_limit,
                    "evidence": request.evidence_limit,
                    "characters": request.character_limit,
                },
                returned={
                    "nodes": len(focus_nodes),
                    "assertions": len(assertions_tuple),
                    "paths": min(len(paths), request.node_limit),
                    "episodes": len(episodes),
                    "evidence": len(evidence),
                },
                truncated=truncated,
            ),
        )
        return _bound_bundle(bundle, request.character_limit)

    def recall(self, request: RecallRequest) -> RecallBundle:
        request = _bounded_request(request)
        sink = self._observation_sink
        recall_started = perf_counter() if sink is not None else 0.0
        # Freeze one read boundary for every derived freshness value in this
        # bundle.  A long graph walk must not observe a moving clock.
        now = utc_now()
        if request.kinship is not None:
            return self._recall_kinship(request, request.kinship, now=now)
        if not request.text.strip() and request.sense is not None:
            return self._recall_sense_only(request, now=now)
        if not request.text.strip() and not request.seed_node_ids:
            # Documented empty-recall path: no selection stage runs, so no
            # memory.recall.selection events are emitted for this request.
            return self._empty_bundle(request)

        lexical_fetch_limit = (
            min(
                200,
                max(
                    request.lexical_limit + 1,
                    request.seed_limit * 4,
                    request.node_limit * 2,
                    32,
                ),
            )
            if request.lexical_limit > 0
            else 0
        )
        lexical_search = self._search_fts_candidates(
            request.text,
            lexical_fetch_limit,
            request=request,
            privacy_scope=request.privacy_scope,
            recall_id=request.recall_id,
        )
        lexical_hits = lexical_search.hits
        lexical_truncated = (
            lexical_search.truncated or len(lexical_hits) > request.lexical_limit
        )
        lexical = [
            (hit.record_id, hit.score)
            for hit in lexical_hits
            if hit.record_kind in {"episode", "node"}
        ]
        lexical_scores = dict(lexical)
        assertion_hit_scores = {
            hit.record_id: hit.score
            for hit in lexical_hits
            if hit.record_kind == "assertion"
        }
        allowed_types = set(request.node_types)
        seed_ids: list[str] = []
        explicit_seed_ids: list[str] = []
        for node_id in request.seed_node_ids:
            resolved = self.resolve_graph_node_id(node_id)
            if resolved is None:
                continue
            node = self.get_graph_node(
                resolved, privacy_scope=request.privacy_scope, now=now
            )
            # Explicit seeds are traversal anchors.  ``node_types`` filters
            # returned focus nodes/neighbors, but must not make a caller's
            # person seed unusable when it asks for related animal/concept
            # nodes.
            if node is not None and _recall_eligible(node):
                seed_ids.append(resolved)
                explicit_seed_ids.append(resolved)
        episode_scores: dict[str, float] = {}
        direct_graph_ids: list[str] = []
        exact_graph_ids: list[str] = []
        for hit in lexical_hits:
            node_id, score = hit.record_id, hit.score
            if hit.record_kind == "node":
                graph_node = self.get_graph_node(
                    node_id, privacy_scope=request.privacy_scope, now=now
                )
                if graph_node is None or not _recall_eligible(graph_node):
                    continue
                if not allowed_types or graph_node.node_type in allowed_types:
                    direct_graph_ids.append(graph_node.node_id)
                    if _node_matches_query_label(graph_node, request.text):
                        exact_graph_ids.append(graph_node.node_id)
            elif hit.record_kind == "episode":
                episode_scores[node_id] = score
        # A direct label hit is already the user's requested graph subject.
        # Keep matching Episodes as sources, but do not promote every entity
        # mentioned by those Episodes into unrelated search seeds.
        seed_ids.extend(dict.fromkeys(exact_graph_ids or direct_graph_ids))
        # Explicit Node seeds must also work as a reverse lookup into the
        # Episodes that mention them. This is the same source-first Episode
        # path used by lexical hits; it does not introduce a second ranking
        # system or manufacture an Assertion.
        for episode_id, score in self._episode_scores_for_nodes(
            explicit_seed_ids,
            privacy_scope=request.privacy_scope,
        ).items():
            episode_scores[episode_id] = max(episode_scores.get(episode_id, 0.0), score)
        if episode_scores and _has_episode_filters(request):
            episode_scores = self._filter_episode_window(episode_scores, request)

        # An Episode can be the only lexical anchor even when its graph
        # mentions were not materialized (for example after a restart).  Use
        # the source evidence links to recover the subject node, then let the
        # existing graph owner return the complete current/superseded claim
        # set.  This keeps corrections and their two sources together without
        # reintroducing every weak lexical candidate as a seed.
        if not exact_graph_ids:
            for subject_id in self._assertion_subjects_for_episodes(
                episode_scores,
                privacy_scope=request.privacy_scope,
            ):
                resolved = self.resolve_graph_node_id(subject_id)
                if resolved is None:
                    continue
                node = self.get_graph_node(
                    resolved,
                    privacy_scope=request.privacy_scope,
                    now=now,
                )
                if (
                    node is not None
                    and _recall_eligible(node)
                    and (not allowed_types or node.node_type in allowed_types)
                ):
                    seed_ids.append(resolved)

        # An exact/rare term may first hit an Episode. Mentions promote its
        # resolved nodes into the graph seed set without inventing entities.
        if episode_scores and not exact_graph_ids:
            episode_ids = tuple(episode_scores)
            placeholders = ",".join("?" for _ in episode_ids)
            with self._lock:
                rows = self.conn.execute(
                    f"""SELECT DISTINCT node_id FROM episode_mentions
                        WHERE episode_id IN ({placeholders}) AND node_id IS NOT NULL
                          AND resolution_state='resolved'""",
                    list(episode_ids),
                ).fetchall()
            for row in rows:
                resolved = self.resolve_graph_node_id(str(row[0]))
                if resolved is None:
                    continue
                node = self.get_graph_node(
                    resolved, privacy_scope=request.privacy_scope, now=now
                )
                if (
                    node is not None
                    and _recall_eligible(node)
                    and (not allowed_types or node.node_type in allowed_types)
                ):
                    seed_ids.append(resolved)
        unique_seed_ids = list(dict.fromkeys(seed_ids))
        explicit_order = {
            node_id: index
            for index, node_id in enumerate(dict.fromkeys(explicit_seed_ids))
        }
        exact_order = {
            node_id: index
            for index, node_id in enumerate(dict.fromkeys(exact_graph_ids))
        }
        if len(unique_seed_ids) > request.seed_limit:

            def seed_rank(node_id: str) -> tuple[int, float, str]:
                if node_id in explicit_order:
                    return (0, float(explicit_order[node_id]), node_id)
                if node_id in exact_order:
                    return (1, float(exact_order[node_id]), node_id)
                node = self.get_graph_node(
                    node_id, privacy_scope=request.privacy_scope, now=now
                )
                if node is None:
                    return (2, 0.0, node_id)
                # Episode-linked subjects have no direct text match; use the
                # query score if present and a stable ID as the final tie-break.
                return (2, -lexical_scores.get(node_id, 0.0), node_id)

            unique_seed_ids = sorted(unique_seed_ids, key=seed_rank)
        seeds_truncated = len(unique_seed_ids) > request.seed_limit
        seed_ids = unique_seed_ids[: request.seed_limit]

        assertions: dict[str, RecallAssertion] = {}
        assertion_relevance: dict[str, float] = {}
        paths: list[RecallPath] = []
        assertions_truncated = False
        visited: set[str] = set(seed_ids)
        if (
            request.assertion_limit > 0
            and seed_ids
            and (not request.record_kinds or "assertion" in request.record_kinds)
        ):
            basic_candidates = self.graph_assertions_for(
                seed_ids,
                relation_types=request.relation_types,
                limit=request.assertion_limit + 1,
                minimum_importance=request.minimum_importance,
                occurred_from=request.occurred_from,
                occurred_to=request.occurred_to,
                person_node_ids=request.person_node_ids,
                place_node_ids=request.place_node_ids,
                emotion_labels=request.emotion_labels,
                topic_labels=request.topic_labels,
                cause_labels=request.cause_labels,
                privacy_scope=request.privacy_scope,
                include_unknown_time=request.include_unknown_time,
                recall_eligible_only=True,
                now=now,
            )
            if len(basic_candidates) > request.assertion_limit:
                assertions_truncated = True
            for assertion in basic_candidates[: request.assertion_limit]:
                assertions[assertion.assertion_id] = assertion
                assertion_relevance[assertion.assertion_id] = max(
                    lexical_scores.get(assertion.subject_id, 0.0),
                    lexical_scores.get(assertion.object_node_id or "", 0.0),
                    1.0 if assertion.subject_id in explicit_seed_ids else 0.0,
                    1.0 if assertion.object_node_id in explicit_seed_ids else 0.0,
                )
        if assertion_hit_scores:
            for assertion in self.get_graph_assertions_by_ids(
                assertion_hit_scores,
                privacy_scope=request.privacy_scope,
            ):
                if (
                    request.minimum_importance is not None
                    and assertion.importance < request.minimum_importance
                ):
                    continue
                if (
                    request.relation_types
                    and assertion.predicate not in request.relation_types
                ):
                    continue
                assertions[assertion.assertion_id] = assertion
                assertion_relevance[assertion.assertion_id] = assertion_hit_scores.get(
                    assertion.assertion_id, 0.0
                )
        # Query results may attach only the endpoints of selected direct facts;
        # general language never turns into an arbitrary graph walk.
        for assertion in assertions.values():
            for node_id in (assertion.subject_id, assertion.object_node_id):
                if node_id is None:
                    continue
                node = self.get_graph_node(
                    node_id, privacy_scope=request.privacy_scope, now=now
                )
                if node is not None and _recall_eligible(node):
                    if not allowed_types or node.node_type in allowed_types:
                        visited.add(node.node_id)
                        lexical_scores[node.node_id] = max(
                            lexical_scores.get(node.node_id, 0.0),
                            assertion_relevance.get(assertion.assertion_id, 0.0),
                        )
            if assertion.object_node_id is not None:
                if (
                    assertion.status == "active"
                    and assertion.qualifiers.get("polarity", "positive") == "positive"
                ):
                    paths.append(
                        RecallPath(
                            node_ids=(assertion.subject_id, assertion.object_node_id),
                            assertion_ids=(assertion.assertion_id,),
                            hop_count=1,
                            role=(
                                "primary"
                                if assertion.assertion_id in assertion_hit_scores
                                else "support"
                            ),
                        )
                    )

        focus_ids = list(visited)
        primary_node_ids = set(explicit_seed_ids) | set(
            exact_graph_ids or direct_graph_ids
        )
        focus_nodes = self._focus_nodes(
            focus_ids,
            lexical_scores,
            request,
            now=now,
            primary_node_ids=primary_node_ids,
        )
        ranked_assertions = sorted(
            assertions.values(),
            key=lambda item: (
                -assertion_relevance.get(item.assertion_id, 0.0),
                0 if item.status == "active" else 1,
                item.assertion_id,
            ),
        )[: request.assertion_limit]
        assertions_tuple = tuple(
            replace(
                item,
                relevance=assertion_relevance.get(item.assertion_id, 0.0),
                role=(
                    "primary"
                    if item.assertion_id in assertion_hit_scores
                    else "support"
                ),
            )
            for item in ranked_assertions
        )
        evidence_candidates = self.get_assertion_evidence(
            (assertion.assertion_id for assertion in assertions_tuple),
            request.evidence_limit + 1 if request.evidence_limit > 0 else 0,
            privacy_scope=request.privacy_scope,
        )
        evidence_truncated = len(evidence_candidates) > request.evidence_limit
        evidence = evidence_candidates[: request.evidence_limit]
        source_ids = tuple(
            dict.fromkeys(
                [item.source_id for item in evidence if item.source_id]
                + list(episode_scores)
            )
        )
        episodes, episodes_truncated = self._episodes_for_recall(
            source_ids,
            episode_scores,
            request,
            now=now,
            primary_episode_ids=episode_scores,
        )
        conflicts = self._conflicts(assertions_tuple)
        if request.record_kinds:
            if "node" not in request.record_kinds:
                focus_nodes = ()
            if "assertion" not in request.record_kinds:
                assertions_tuple = ()
                paths = []
                evidence = ()
                conflicts = ()
            if "episode" not in request.record_kinds:
                episodes = ()
        paths = sorted(
            paths,
            key=lambda path: (path.hop_count, path.node_ids, path.assertion_ids),
        )[: request.node_limit]
        truncated = any(
            (
                lexical_truncated,
                seeds_truncated,
                len(focus_ids) > request.node_limit,
                assertions_truncated or len(assertions) > request.assertion_limit,
                evidence_truncated,
                episodes_truncated,
            )
        )
        bundle = RecallBundle(
            focus_nodes=focus_nodes,
            assertions=assertions_tuple,
            paths=tuple(paths),
            episodes=episodes,
            evidence=evidence,
            conflicts=conflicts,
            status="partial" if truncated else "complete",
            notices=("no_relevant_candidates",)
            if not (focus_nodes or assertions_tuple or episodes)
            else (),
            limits=RecallLimits(
                requested={
                    "lexical": request.lexical_limit,
                    "seeds": request.seed_limit,
                    "nodes": request.node_limit,
                    "assertions": request.assertion_limit,
                    "episodes": request.episode_limit,
                    "evidence": request.evidence_limit,
                    "characters": request.character_limit,
                },
                returned={
                    "nodes": len(focus_nodes),
                    "assertions": len(assertions_tuple),
                    "paths": len(paths),
                    "episodes": len(episodes),
                    "evidence": len(evidence),
                },
                truncated=truncated,
            ),
        )
        bounded = _bound_bundle(bundle, request.character_limit)
        if sink is not None:
            self._emit_recall_selection_summary(
                recall_id=request.recall_id,
                candidates_seen=len(lexical_hits) + len(request.seed_node_ids),
                kept=(
                    len(bounded.focus_nodes)
                    + len(bounded.assertions)
                    + len(bounded.episodes)
                    + len(bounded.evidence)
                ),
                truncated=bool(bounded.limits.truncated),
                character_budget_used=sum(
                    len(item.excerpt) for item in bounded.episodes
                ),
                character_budget_limit=request.character_limit,
                request=request,
                duration_ms=round((perf_counter() - recall_started) * 1000.0, 2),
            )
        return bounded

    def _focus_nodes(
        self,
        node_ids: Iterable[str],
        lexical_scores: dict[str, float],
        request: RecallRequest,
        *,
        now: str,
        primary_node_ids: Iterable[str],
    ) -> tuple[RecallNode, ...]:
        nodes: list[RecallNode] = []
        allowed = set(request.node_types)
        primary = set(primary_node_ids)
        if request.record_kinds and "node" not in request.record_kinds:
            return ()
        for node_id in node_ids:
            node = self.get_graph_node(
                node_id, privacy_scope=request.privacy_scope, now=now
            )
            if node is None or (allowed and node.node_type not in allowed):
                continue
            if (
                request.minimum_importance is not None
                and node.importance < request.minimum_importance
            ):
                continue
            base_score = (
                1.0
                if node_id in request.seed_node_ids
                else lexical_scores.get(node_id, 0.0)
            )
            nodes.append(
                RecallNode(
                    node_id=node.node_id,
                    node_type=node.node_type,
                    label=node.label,
                    description=node.description,
                    relevance=base_score,
                    importance=node.importance,
                    confidence=node.confidence,
                    freshness=node.freshness,
                    half_life_days=node.half_life_days,
                    properties=node.properties,
                    role="primary" if node_id in primary else "support",
                )
            )
        return tuple(
            sorted(nodes, key=lambda item: (-item.relevance, item.node_id))[
                : request.node_limit
            ]
        )

    def _assertion_subjects_for_episodes(
        self,
        episode_scores: Mapping[str, float],
        *,
        privacy_scope: str | None,
    ) -> tuple[str, ...]:
        """Return visible graph subjects linked to recalled Episode sources."""
        del privacy_scope  # source rows already carry the request scope
        episode_ids = tuple(episode_scores)
        if not episode_ids:
            return ()
        placeholders = ",".join("?" for _ in episode_ids)
        params: list[object] = list(episode_ids)
        scope = ""
        if getattr(self, "elfie_id", None) is not None:
            scope = " AND json_extract(n.properties_json, '$.elfie_id')=?"
            params.append(str(self.elfie_id))
        with self._lock:
            rows = self.conn.execute(
                f"""SELECT DISTINCT a.subject_node_id
                       FROM assertion_evidence AS ae
                       JOIN assertions AS a ON a.assertion_id=ae.assertion_id
                       JOIN evidence AS e ON e.evidence_id=ae.evidence_id
                       JOIN nodes AS n ON n.node_id=a.subject_node_id
                      WHERE e.source_type='episode'
                        AND e.source_id IN ({placeholders})
                        AND a.lifecycle IN ('active', 'superseded')
                        AND n.status IN ('active', 'candidate', 'unresolved')
                        AND n.merged_into IS NULL"""
                + scope,
                params,
            ).fetchall()
        return tuple(str(row[0]) for row in rows if row[0])

    def _filter_episode_window(
        self, scores: dict[str, float], request: RecallRequest
    ) -> dict[str, float]:
        ids = tuple(scores)
        placeholders = ",".join("?" for _ in ids)
        clauses = [
            f"episode_id IN ({placeholders})",
            "lifecycle='active'",
            _episode_recall_eligibility("episodes"),
        ]
        params: list[object] = list(ids)
        if getattr(self, "elfie_id", None) is not None:
            clauses.append("json_extract(metadata_json, '$.elfie_id')=?")
            params.append(str(self.elfie_id))
        time_conditions, time_params = _episode_time_conditions(request, "episodes")
        clauses.extend(time_conditions)
        params.extend(time_params)
        facet_conditions, facet_params = _episode_facet_conditions_for_alias(
            request, "episodes"
        )
        clauses.extend(facet_conditions)
        params.extend(facet_params)
        with self._lock:
            rows = self.conn.execute(
                "SELECT episode_id FROM episodes WHERE " + " AND ".join(clauses),
                params,
            ).fetchall()
        return {str(row[0]): scores[str(row[0])] for row in rows}

    def _episode_scores_for_nodes(
        self,
        node_ids: Iterable[str],
        *,
        privacy_scope: str | None,
    ) -> dict[str, float]:
        """Return bounded direct Episode relevance for explicit Node seeds."""

        del privacy_scope  # namespace and source visibility are applied below
        ids = tuple(dict.fromkeys(node_ids))
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        params: list[object] = list(ids)
        namespace_clause = ""
        if getattr(self, "elfie_id", None) is not None:
            namespace_clause = " AND json_extract(ep.metadata_json, '$.elfie_id')=?"
            params.append(str(self.elfie_id))
        with self._lock:
            rows = self.conn.execute(
                f"""SELECT em.episode_id, MAX(COALESCE(em.confidence, 0.5)) AS confidence
                      FROM episode_mentions AS em
                      JOIN episodes AS ep ON ep.episode_id=em.episode_id
                     WHERE em.node_id IN ({placeholders})
                       AND em.resolution_state='resolved'
                       AND ep.lifecycle='active'
                       AND {_episode_recall_eligibility("ep")}
                       {namespace_clause}
                     GROUP BY em.episode_id""",
                params,
            ).fetchall()
        return {
            str(row["episode_id"]): max(0.0, min(1.0, float(row["confidence"] or 0.5)))
            * 0.75
            for row in rows
        }

    def _episodes_for_recall(
        self,
        source_ids: Iterable[str],
        direct_scores: dict[str, float],
        request: RecallRequest,
        *,
        now: str,
        primary_episode_ids: Iterable[str],
    ) -> tuple[tuple[RecallEpisode, ...], bool]:
        episode_ids = tuple(dict.fromkeys(source_ids))
        primary = set(primary_episode_ids)
        if not episode_ids or (
            request.record_kinds and "episode" not in request.record_kinds
        ):
            return (), False
        fetch_limit = request.episode_limit + 1 if request.episode_limit > 0 else 0
        if fetch_limit == 0:
            return (), bool(episode_ids)
        with self._lock:
            placeholders = ",".join("?" for _ in episode_ids)
            time_clauses, time_params = _episode_time_conditions(request, "episodes")
            facet_conditions, facet_params = _episode_facet_conditions_for_alias(
                request, "episodes"
            )
            time_clauses.extend(facet_conditions)
            time_params.extend(facet_params)
            namespace_clause = ""
            namespace_params: list[str] = []
            if getattr(self, "elfie_id", None) is not None:
                namespace_clause = " AND json_extract(metadata_json, '$.elfie_id')=?"
                namespace_params.append(str(self.elfie_id))
            importance_clause = ""
            importance_params: list[object] = []
            if request.minimum_importance is not None:
                importance_clause = " AND importance>=?"
                importance_params.append(request.minimum_importance)
            where = " AND " + " AND ".join(time_clauses) if time_clauses else ""
            direct_rows = self.conn.execute(
                f"""SELECT episode_id, occurred_from, occurred_to,
                           occurrence_precision, life_stage, temporal_label,
                           content_text, summary_text, detail_level, importance,
                           half_life_days, last_reinforced_at, updated_at,
                           source_event_ids_json, metadata_json
                     FROM episodes
                     WHERE episode_id IN ({placeholders})
                       AND lifecycle='active'
                       AND {_episode_recall_eligibility("episodes")}
                       {importance_clause}{namespace_clause}{where}
                     ORDER BY episode_id""",
                list(episode_ids) + importance_params + namespace_params + time_params,
            ).fetchall()
            topic_buckets = tuple(
                sorted(
                    {
                        str(metadata.get("topic_bucket"))
                        for row in direct_rows
                        for metadata in (_json_object(row["metadata_json"]),)
                        if metadata.get("knowledge_id")
                        and str(metadata.get("topic_bucket", "")).strip()
                    }
                )
            )
            if topic_buckets and request.sense is None:
                bucket_placeholders = ",".join("?" for _ in topic_buckets)
                topic_rows = self.conn.execute(
                    f"""SELECT episode_id, occurred_from, occurred_to,
                               occurrence_precision, life_stage, temporal_label,
                               content_text, summary_text, detail_level, importance,
                               half_life_days, last_reinforced_at, updated_at,
                               source_event_ids_json, metadata_json
                          FROM episodes
                         WHERE lifecycle='active'
                           AND {_episode_recall_eligibility("episodes")}
                           AND json_extract(episodes.metadata_json, '$.knowledge_id') IS NOT NULL
                           AND json_extract(episodes.metadata_json, '$.topic_bucket')
                               IN ({bucket_placeholders})
                           {importance_clause}{namespace_clause}{where}
                         ORDER BY json_extract(episodes.metadata_json, '$.topic_member_index'),
                                  occurred_from IS NULL, occurred_from, episode_id
                         LIMIT ?""",
                    list(topic_buckets)
                    + importance_params
                    + namespace_params
                    + time_params
                    + [max(64, min(512, request.episode_limit * 8))],
                ).fetchall()
                direct_ids = {str(row["episode_id"]) for row in direct_rows}
                rows = tuple(
                    list(direct_rows)
                    + [
                        row
                        for row in topic_rows
                        if str(row["episode_id"]) not in direct_ids
                    ]
                )
            else:
                rows = tuple(direct_rows)
        result: list[RecallEpisode] = []
        row_metadata = {
            str(row["episode_id"]): _json_object(row["metadata_json"]) for row in rows
        }
        topic_anchors: dict[str, float] = {}
        topic_available: dict[str, int] = defaultdict(int)
        for row in rows:
            metadata = row_metadata[str(row["episode_id"])]
            bucket = str(metadata.get("topic_bucket", "")).strip()
            if not bucket or not metadata.get("knowledge_id"):
                continue
            topic_available[bucket] += 1
            topic_anchors[bucket] = max(
                topic_anchors.get(bucket, 0.0),
                max(
                    (
                        float(direct_scores.get(str(candidate["episode_id"]), 0.0))
                        for candidate in rows
                        if str(
                            row_metadata[str(candidate["episode_id"])].get(
                                "topic_bucket", ""
                            )
                        )
                        == bucket
                        and str(candidate["episode_id"]) in direct_scores
                    ),
                    default=0.25,
                ),
            )
        for row in rows:
            episode_id = str(row["episode_id"])
            metadata = row_metadata[episode_id]
            topic_bucket = str(metadata.get("topic_bucket", "")).strip() or None
            excerpt = str(row["content_text"])
            summary_text = (
                None if row["summary_text"] is None else str(row["summary_text"])
            )
            half_life_days = float(row["half_life_days"] or 2.0)
            anchor = row["last_reinforced_at"] or row["updated_at"] or now
            freshness = MemoryScorePolicy.freshness(now, str(anchor), half_life_days)
            relevance = direct_scores.get(episode_id)
            if relevance is None and topic_bucket is not None:
                relevance = max(0.10, topic_anchors.get(topic_bucket, 0.25) * 0.80)
            result.append(
                RecallEpisode(
                    episode_id=episode_id,
                    occurred_from=(
                        None
                        if row["occurred_from"] is None
                        else str(row["occurred_from"])
                    ),
                    occurred_to=row["occurred_to"],
                    excerpt=excerpt,
                    summary_text=summary_text,
                    detail_level=str(row["detail_level"]),
                    relevance=(relevance or 0.0),
                    occurrence_precision=cast(
                        OccurrencePrecision,
                        str(row["occurrence_precision"] or "exact"),
                    ),
                    life_stage=row["life_stage"],
                    temporal_label=row["temporal_label"],
                    importance=float(row["importance"]),
                    freshness=freshness,
                    half_life_days=half_life_days,
                    source_event_ids=tuple(
                        str(value) for value in _json_list(row["source_event_ids_json"])
                    ),
                    topic_bucket=topic_bucket,
                    topic_member_index=(
                        int(metadata["topic_member_index"])
                        if isinstance(metadata.get("topic_member_index"), int)
                        else None
                    ),
                    topic_member_count=(
                        topic_available.get(topic_bucket, 0)
                        if topic_bucket is not None
                        else 0
                    ),
                    role="primary" if episode_id in primary else "support",
                )
            )
        ordered = sorted(
            result,
            key=lambda item: (
                -item.relevance,
                item.episode_id,
            ),
        )
        limited = list(ordered[: request.episode_limit])
        returned_by_topic: dict[str, int] = defaultdict(int)
        for item in limited:
            if item.topic_bucket is not None:
                returned_by_topic[item.topic_bucket] += 1
        materialized = [
            replace(
                item,
                topic_omitted_count=(
                    max(
                        0,
                        topic_available[item.topic_bucket]
                        - returned_by_topic[item.topic_bucket],
                    )
                    if item.topic_bucket is not None
                    else 0
                ),
                topic_continuation=(
                    f"topic:{item.topic_bucket}"
                    if item.topic_bucket is not None
                    and topic_available[item.topic_bucket]
                    > returned_by_topic[item.topic_bucket]
                    else None
                ),
            )
            for item in limited
        ]
        return tuple(materialized), len(ordered) > request.episode_limit

    @staticmethod
    def _conflicts(
        assertions: Iterable[RecallAssertion],
    ) -> tuple[RecallConflict, ...]:
        groups: defaultdict[str, list[str]] = defaultdict(list)
        for assertion in assertions:
            group = assertion.qualifiers.get("conflict_group")
            if isinstance(group, str) and group:
                groups[group].append(assertion.assertion_id)
        return tuple(
            RecallConflict(
                assertion_ids=tuple(ids),
                reason="qualified claims share a conflict group",
            )
            for _group, ids in sorted(groups.items())
            if len(ids) > 1
        )

    @staticmethod
    def _empty_bundle(request: RecallRequest) -> RecallBundle:
        return RecallBundle(
            limits=RecallLimits(
                requested={
                    "lexical": request.lexical_limit,
                    "seeds": request.seed_limit,
                    "nodes": request.node_limit,
                    "assertions": request.assertion_limit,
                    "episodes": request.episode_limit,
                    "evidence": request.evidence_limit,
                    "characters": request.character_limit,
                },
                returned={
                    "nodes": 0,
                    "assertions": 0,
                    "paths": 0,
                    "episodes": 0,
                    "evidence": 0,
                },
            )
        )


def _bound_bundle(bundle: RecallBundle, character_limit: int) -> RecallBundle:
    """Bound source excerpts without dropping their identity or provenance."""
    if character_limit < 1:
        has_payload = any(
            (
                bundle.focus_nodes,
                bundle.assertions,
                bundle.paths,
                bundle.episodes,
                bundle.evidence,
                bundle.conflicts,
            )
        )
        return RecallBundle(
            recall_revision=bundle.recall_revision,
            status=bundle.status,
            notices=bundle.notices,
            limits=RecallLimits(
                requested=bundle.limits.requested,
                returned=dict.fromkeys(bundle.limits.returned, 0),
                truncated=bundle.limits.truncated or has_payload,
            ),
        )
    used = 0
    episodes: list[RecallEpisode] = []
    excerpt_truncated = False
    for episode in bundle.episodes:
        remaining = character_limit - used
        if remaining <= 0:
            break
        excerpt = episode.excerpt[:remaining]
        if excerpt != episode.excerpt:
            excerpt_truncated = True
        used += len(excerpt)
        episodes.append(
            RecallEpisode(
                episode_id=episode.episode_id,
                occurred_from=episode.occurred_from,
                occurred_to=episode.occurred_to,
                excerpt=excerpt,
                summary_text=episode.summary_text,
                detail_level=episode.detail_level,
                relevance=episode.relevance,
                occurrence_precision=episode.occurrence_precision,
                life_stage=episode.life_stage,
                temporal_label=episode.temporal_label,
                importance=episode.importance,
                freshness=episode.freshness,
                half_life_days=episode.half_life_days,
                source_event_ids=episode.source_event_ids,
                topic_bucket=episode.topic_bucket,
                topic_member_index=episode.topic_member_index,
                topic_member_count=episode.topic_member_count,
                topic_omitted_count=episode.topic_omitted_count,
                topic_continuation=episode.topic_continuation,
                role=episode.role,
            )
        )
    truncated = (
        bundle.limits.truncated
        or excerpt_truncated
        or len(episodes) != len(bundle.episodes)
    )
    limits = RecallLimits(
        requested=bundle.limits.requested,
        returned={**bundle.limits.returned, "episodes": len(episodes)},
        truncated=truncated,
    )
    return RecallBundle(
        focus_nodes=bundle.focus_nodes,
        assertions=bundle.assertions,
        paths=bundle.paths,
        episodes=tuple(episodes),
        evidence=bundle.evidence,
        conflicts=bundle.conflicts,
        recall_revision=bundle.recall_revision,
        status=bundle.status,
        notices=bundle.notices,
        limits=limits,
    )


def _lexical_normalize(value: str) -> str:
    """Normalize searchable text without weakening semantic identity rules."""
    cleaned = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9\s]", "", value.casefold())
    return " ".join(cleaned.split())


def _node_matches_query_label(node: RecallNode, query: str) -> bool:
    """Return whether a graph hit names the requested subject directly.

    Episode text is intentionally broader than a graph label.  This small
    distinction lets Recall keep matching Episodes as sources while avoiding
    promotion of every entity co-mentioned by those Episodes.
    """
    normalized_query = _lexical_normalize(query)
    if not normalized_query:
        return False
    labels = [node.label]
    aliases = node.properties.get("aliases")
    if isinstance(aliases, (list, tuple, set, frozenset)):
        labels.extend(str(alias) for alias in aliases)
    return any(
        normalized_query in _lexical_normalize(label) for label in labels if label
    )


def _lexical_search_terms(query: str) -> list[str]:
    """Use discriminating bigrams, with a single-character fallback for names."""
    terms = list(dict.fromkeys(normalized_tokens(query)))
    meaningful = [
        term for term in terms if len(term) > 1 and term not in _LEXICAL_QUESTION_TERMS
    ]
    if meaningful:
        return meaningful
    return [term for term in terms if term not in _LEXICAL_QUESTION_TERMS]


def _is_distinctive_query_term(term: str) -> bool:
    """Recognize a long exact token that is independently high-signal.

    A mixed-language query can contain several Chinese bigrams from the
    question itself plus one unique identifier or token from the memory.  The
    identifier should not be discarded merely because the question bigrams do
    not occur in the stored Episode.  Ordinary words and Chinese terms still
    use the normal coverage floor.
    """
    return len(term) >= 8 and term.isascii() and term.isalnum()


def _recall_eligible(node: RecallNode) -> bool:
    """Honor the explicit projection visibility flag during traversal."""
    return node.properties.get("recall_eligible", True) is not False


def _episode_recall_eligibility(alias: str) -> str:
    """Hide reserved host-failure Episodes from user-facing Recall.

    Older databases may already contain a host-generated failure notice in a
    topic Episode.  The source row remains inspectable and recoverable, but
    its reserved ``fallback-intent`` provenance must not compete with real
    conversation facts during lexical Recall.
    """
    return (
        "NOT EXISTS ("
        "SELECT 1 FROM json_each(COALESCE("
        + alias
        + ".source_event_ids_json, '[]')) AS source_event "
        "WHERE lower(CAST(source_event.value AS TEXT)) LIKE '%fallback-intent-%'"
        ")"
    )


__all__ = ["SQLiteRecallStoreMixin"]


_HARD_LIMITS = {
    "lexical_limit": 20,
    "seed_limit": 8,
    "node_limit": 40,
    "assertion_limit": 80,
    "episode_limit": 8,
    "evidence_limit": 24,
    "character_limit": 12000,
}


def _bounded_request(request: RecallRequest) -> RecallRequest:
    """Apply the Memory contract's hard caps before touching storage."""
    updates = {
        name: min(getattr(request, name), cap)
        for name, cap in _HARD_LIMITS.items()
        if getattr(request, name) > cap
    }
    return replace(request, **updates) if updates else request


def _has_episode_filters(request: RecallRequest) -> bool:
    return bool(
        request.occurred_from
        or request.occurred_to
        or request.person_node_ids
        or request.place_node_ids
        or request.emotion_labels
        or request.topic_labels
        or request.cause_labels
        or request.minimum_importance is not None
        or request.privacy_scope is not None
    )


def _episode_time_conditions(
    request: RecallRequest, alias: str
) -> tuple[list[str], list[object]]:
    """Build interval-aware time predicates without inventing a date for unknown time."""
    conditions: list[str] = []
    params: list[object] = []
    if request.occurred_from is not None:
        condition = (
            f"({alias}.occurred_from >= ? OR "
            f"({alias}.occurrence_precision='range' AND {alias}.occurred_to >= ?))"
        )
        if request.include_unknown_time:
            condition = f"({alias}.occurred_from IS NULL OR {condition})"
        conditions.append(condition)
        params.extend((request.occurred_from, request.occurred_from))
    if request.occurred_to is not None:
        condition = f"{alias}.occurred_from <= ?"
        if request.include_unknown_time:
            condition = f"({alias}.occurred_from IS NULL OR {condition})"
        conditions.append(condition)
        params.append(request.occurred_to)
    return conditions, params


def _json_list(value: object) -> list[object]:
    if not isinstance(value, str):
        return []
    try:
        result = json.loads(value)
    except (TypeError, ValueError):
        return []
    return result if isinstance(result, list) else []


def _json_object(value: object) -> dict[str, object]:
    if not isinstance(value, str):
        return {}
    try:
        result = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return result if isinstance(result, dict) else {}


def _episode_facet_conditions_for_alias(
    request: RecallRequest, alias: str
) -> tuple[list[str], list[object]]:
    conditions: list[str] = []
    params: list[object] = []
    for node_type, values in (
        ("person", request.person_node_ids),
        ("place", request.place_node_ids),
    ):
        unique = tuple(dict.fromkeys(values))
        if unique:
            placeholders = ",".join("?" for _ in unique)
            conditions.append(
                "EXISTS (SELECT 1 FROM episode_mentions AS fm "
                "JOIN nodes AS fn ON fn.node_id=fm.node_id "
                f"WHERE fm.episode_id={alias}.episode_id AND fm.node_id IN ({placeholders}) "
                "AND fn.node_type=? AND fm.resolution_state='resolved')"
            )
            params.extend(unique)
            params.append(node_type)
    if request.emotion_labels:
        unique = tuple(
            dict.fromkeys(str(value).casefold() for value in request.emotion_labels)
        )
        conditions.append(
            "lower(COALESCE(json_extract("
            + alias
            + ".metadata_json, '$.emotion'), '')) IN ("
            + ",".join("?" for _ in unique)
            + ")"
        )
        params.extend(unique)
    for values, key in (
        (request.topic_labels, "topic"),
        (request.cause_labels, "cause"),
    ):
        unique = tuple(dict.fromkeys(str(value).casefold() for value in values))
        if unique:
            conditions.append(
                "("
                + " OR ".join(
                    "lower(COALESCE(json_extract("
                    + alias
                    + ".metadata_json, '$."
                    + key
                    + "'), '')) LIKE ?"
                    for _ in unique
                )
                + ")"
            )
            params.extend("%" + value + "%" for value in unique)
    if request.privacy_scope is not None:
        conditions.append(alias + ".privacy_scope=?")
        params.append(request.privacy_scope)
    return conditions, params
