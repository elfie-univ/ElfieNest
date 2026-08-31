"""Bounded deterministic hybrid retrieval for the SQLite Memory adapter."""

from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict, deque
from dataclasses import replace
from typing import Iterable, cast

from elfie.brain.memory.memory_records import (
    OccurrencePrecision,
    RecallAssertion,
    RecallBundle,
    RecallConflict,
    RecallEpisode,
    RecallLimits,
    RecallNode,
    RecallPath,
    RecallRequest,
)
from elfie.brain.memory.score_policy import MemoryScorePolicy

from .sqlite_mixin_base import SQLiteMemoryMixinBase
from .sqlite_utils import normalize_text, normalized_tokens, utc_now


class SQLiteRecallStoreMixin(SQLiteMemoryMixinBase):
    """Run lexical source search followed by a bounded local graph walk."""

    conn: sqlite3.Connection

    def search_text(
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
                       WHERE e.lifecycle='active' AND ("""
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
                       WHERE n.status IN ('active', 'candidate', 'unresolved') AND n.merged_into IS NULL
                         AND COALESCE(json_extract(n.properties_json, '$.recall_eligible'), 1) <> 0
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
                          AND n.status IN ('active', 'candidate', 'unresolved')
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
            score = 0.65 * (hits / max(1, len(terms)))
            if query_normalized in normalized:
                score += 0.15
            # Exact aliases are stronger evidence than an incidental mention
            # buried in an Episode or a long description.  Keep a small
            # canonical-label density bonus so a direct knowledge label stays
            # in the bounded seed set when a short place term matches many
            # unrelated Episodes.
            if identifier in exact_alias_ids:
                score += 0.10
            label_normalized = _lexical_normalize(canonical_label)
            if query_normalized and query_normalized in label_normalized:
                score += min(
                    0.05,
                    len(query_normalized) / max(1, len(label_normalized)) * 0.05,
                )
            if kind == "knowledge":
                score += 0.05
            scored[identifier] = max(scored.get(identifier, 0.0), score)
        return sorted(scored.items(), key=lambda item: (-item[1], item[0]))[:top_k]

    def recall(self, request: RecallRequest) -> RecallBundle:
        request = _bounded_request(request)
        # Freeze one read boundary for every derived freshness value in this
        # bundle.  A long graph walk must not observe a moving clock.
        now = utc_now()
        if not request.text.strip() and not request.seed_node_ids:
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
        lexical_candidates = self.search_text(
            request.text,
            lexical_fetch_limit,
            privacy_scope=request.privacy_scope,
        )
        lexical_truncated = len(lexical_candidates) > request.lexical_limit
        # Keep oversampled candidates through graph expansion and the v2 score
        # pass; slicing at the lexical stage would discard rows before F/I/C
        # can participate in ranking.
        lexical = lexical_candidates
        lexical_scores = dict(lexical)
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
        for node_id, score in lexical:
            graph_node = self.get_graph_node(
                node_id, privacy_scope=request.privacy_scope, now=now
            )
            if graph_node is not None and _recall_eligible(graph_node):
                if not allowed_types or graph_node.node_type in allowed_types:
                    seed_ids.append(graph_node.node_id)
            else:
                episode_scores[node_id] = score
        if episode_scores and _has_episode_filters(request):
            episode_scores = self._filter_episode_window(episode_scores, request)

        # An exact/rare term may first hit an Episode. Mentions promote its
        # resolved nodes into the graph seed set without inventing entities.
        if episode_scores:
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
        if len(unique_seed_ids) > request.seed_limit:

            def seed_rank(node_id: str) -> tuple[int, float, str]:
                if node_id in explicit_order:
                    return (0, float(explicit_order[node_id]), node_id)
                node = self.get_graph_node(
                    node_id, privacy_scope=request.privacy_scope, now=now
                )
                if node is None:
                    return (1, 0.0, node_id)
                score = MemoryScorePolicy.recall_score(
                    relevance=lexical_scores.get(node_id, 0.25),
                    freshness=node.freshness,
                    importance=node.importance,
                    confidence=node.confidence,
                )
                return (1, -score.rank, node_id)

            unique_seed_ids = sorted(unique_seed_ids, key=seed_rank)
        seeds_truncated = len(unique_seed_ids) > request.seed_limit
        seed_ids = unique_seed_ids[: request.seed_limit]

        assertions: dict[str, RecallAssertion] = {}
        assertion_hops: dict[str, int] = {}
        paths: list[RecallPath] = []
        assertions_truncated = False
        visited: set[str] = set(seed_ids)
        frontier: deque[tuple[str, tuple[str, ...], tuple[str, ...], int]] = deque(
            (node_id, (node_id,), (), 0) for node_id in seed_ids
        )
        if request.mode in ("local", "basic_local") and request.hop_limit > 0:
            while frontier and len(visited) < request.node_limit:
                current, node_path, assertion_path, depth = frontier.popleft()
                if depth >= request.hop_limit:
                    continue
                local_candidates = self.graph_assertions_for(
                    (current,),
                    relation_types=request.relation_types,
                    limit=request.neighbors_per_node + 1,
                    occurred_from=request.occurred_from,
                    occurred_to=request.occurred_to,
                    person_node_ids=request.person_node_ids,
                    place_node_ids=request.place_node_ids,
                    emotion_labels=request.emotion_labels,
                    topic_labels=request.topic_labels,
                    cause_labels=request.cause_labels,
                    privacy_scope=request.privacy_scope,
                    include_unknown_time=request.include_unknown_time,
                    now=now,
                )
                if len(local_candidates) > request.neighbors_per_node:
                    assertions_truncated = True
                for assertion in local_candidates[: request.neighbors_per_node]:
                    if len(assertions) >= request.assertion_limit:
                        assertions_truncated = True
                        break
                    assertions[assertion.assertion_id] = assertion
                    assertion_hops[assertion.assertion_id] = min(
                        assertion_hops.get(assertion.assertion_id, depth + 1),
                        depth + 1,
                    )
                    neighbor = _neighbor(current, assertion)
                    if neighbor is None:
                        continue
                    neighbor_node = self.get_graph_node(
                        neighbor,
                        privacy_scope=request.privacy_scope,
                        now=now,
                    )
                    if neighbor_node is None or not _recall_eligible(neighbor_node):
                        continue
                    if allowed_types and neighbor_node.node_type not in allowed_types:
                        continue
                    neighbor = neighbor_node.node_id
                    new_node_path = node_path + (neighbor,)
                    new_assertion_path = assertion_path + (assertion.assertion_id,)
                    if neighbor not in visited and len(visited) < request.node_limit:
                        visited.add(neighbor)
                        frontier.append(
                            (neighbor, new_node_path, new_assertion_path, depth + 1)
                        )
                        paths.append(
                            RecallPath(
                                node_ids=new_node_path,
                                assertion_ids=new_assertion_path,
                                hop_count=depth + 1,
                            )
                        )
            # Explicit seeds should still return their direct facts when the
            # node limit is zero only if the caller asked for no graph payload.
        if request.mode == "basic" and request.assertion_limit > 0 and seed_ids:
            basic_candidates = self.graph_assertions_for(
                seed_ids,
                relation_types=request.relation_types,
                limit=request.assertion_limit + 1,
                occurred_from=request.occurred_from,
                occurred_to=request.occurred_to,
                person_node_ids=request.person_node_ids,
                place_node_ids=request.place_node_ids,
                emotion_labels=request.emotion_labels,
                topic_labels=request.topic_labels,
                cause_labels=request.cause_labels,
                privacy_scope=request.privacy_scope,
                include_unknown_time=request.include_unknown_time,
                now=now,
            )
            if len(basic_candidates) > request.assertion_limit:
                assertions_truncated = True
            for assertion in basic_candidates[: request.assertion_limit]:
                assertions[assertion.assertion_id] = assertion
                assertion_hops[assertion.assertion_id] = 0

        focus_ids = list(visited)
        focus_nodes = self._focus_nodes(focus_ids, lexical_scores, request, now=now)
        assertions_tuple = tuple(
            sorted(
                assertions.values(),
                key=lambda item: _assertion_rank(
                    item,
                    hop_count=assertion_hops.get(
                        item.assertion_id, request.hop_limit + 1
                    ),
                    seed_ids=seed_ids,
                    lexical_scores=lexical_scores,
                    request=request,
                ),
            )[: request.assertion_limit]
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
            source_ids, episode_scores, request, now=now
        )
        conflicts = self._conflicts(assertions_tuple)
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
        return _bound_bundle(bundle, request.character_limit)

    def _focus_nodes(
        self,
        node_ids: Iterable[str],
        lexical_scores: dict[str, float],
        request: RecallRequest,
        *,
        now: str,
    ) -> tuple[RecallNode, ...]:
        nodes: list[RecallNode] = []
        allowed = set(request.node_types)
        for node_id in node_ids:
            node = self.get_graph_node(
                node_id, privacy_scope=request.privacy_scope, now=now
            )
            if node is None or (allowed and node.node_type not in allowed):
                continue
            base_score = (
                1.0
                if node_id in request.seed_node_ids
                else lexical_scores.get(node_id, 0.0)
            )
            score = MemoryScorePolicy.recall_score(
                relevance=base_score,
                freshness=node.freshness,
                importance=node.importance,
                confidence=node.confidence,
            )
            nodes.append(
                RecallNode(
                    node_id=node.node_id,
                    node_type=node.node_type,
                    label=node.label,
                    description=node.description,
                    relevance=score.rank,
                    importance=node.importance,
                    confidence=node.confidence,
                    freshness=node.freshness,
                    half_life_days=node.half_life_days,
                    properties=node.properties,
                )
            )
        return tuple(
            sorted(nodes, key=lambda item: (-item.relevance, item.node_id))[
                : request.node_limit
            ]
        )

    def _filter_episode_window(
        self, scores: dict[str, float], request: RecallRequest
    ) -> dict[str, float]:
        ids = tuple(scores)
        placeholders = ",".join("?" for _ in ids)
        clauses = [f"episode_id IN ({placeholders})", "lifecycle='active'"]
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

    def _episodes_for_recall(
        self,
        source_ids: Iterable[str],
        direct_scores: dict[str, float],
        request: RecallRequest,
        *,
        now: str,
    ) -> tuple[tuple[RecallEpisode, ...], bool]:
        episode_ids = tuple(dict.fromkeys(source_ids))
        if not episode_ids:
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
            where = " AND " + " AND ".join(time_clauses) if time_clauses else ""
            rows = self.conn.execute(
                f"""SELECT episode_id, occurred_from, occurred_to,
                           occurrence_precision, life_stage, temporal_label,
                           content_text, summary_text, detail_level, importance,
                           half_life_days, last_reinforced_at, updated_at,
                           source_event_ids_json
                      FROM episodes
                     WHERE episode_id IN ({placeholders})
                       AND lifecycle='active'
                       {namespace_clause}{where}
                     ORDER BY occurred_from IS NULL, occurred_from, episode_id LIMIT ?""",
                list(episode_ids) + namespace_params + time_params + [fetch_limit],
            ).fetchall()
        result: list[RecallEpisode] = []
        for row in rows:
            episode_id = str(row["episode_id"])
            excerpt = str(row["summary_text"] or row["content_text"])
            half_life_days = float(row["half_life_days"] or 2.0)
            anchor = row["last_reinforced_at"] or row["updated_at"] or now
            freshness = MemoryScorePolicy.freshness(now, str(anchor), half_life_days)
            score = MemoryScorePolicy.recall_score(
                relevance=direct_scores.get(episode_id, 0.0),
                freshness=freshness,
                importance=float(row["importance"]),
                confidence=None,
            )
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
                    detail_level=str(row["detail_level"]),
                    relevance=score.rank,
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
                )
            )
        ordered = sorted(
            result,
            key=lambda item: (
                -item.relevance,
                -item.importance,
                -_episode_time_relevance(item, request),
                0 if item.occurred_from is not None else 1,
                item.occurred_from or "",
                item.episode_id,
            ),
        )
        return tuple(ordered[: request.episode_limit]), len(
            ordered
        ) > request.episode_limit

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


def _neighbor(current: str, assertion: RecallAssertion) -> str | None:
    if assertion.subject_id == current:
        return assertion.object_node_id
    if assertion.object_node_id == current:
        return assertion.subject_id
    return None


def _assertion_rank(
    assertion: RecallAssertion,
    *,
    hop_count: int,
    seed_ids: Iterable[str],
    lexical_scores: dict[str, float],
    request: RecallRequest,
) -> tuple[float, int, float, float, float, str]:
    """Return the contract's lexicographic assertion ranking tuple."""
    seeds = set(seed_ids)
    match_strength = max(
        (
            1.0 if node_id in seeds else lexical_scores.get(node_id, 0.0)
            for node_id in (assertion.subject_id, assertion.object_node_id)
            if node_id is not None
        ),
        default=0.0,
    )
    # A superseded claim is historical context, not a current fact.  It stays
    # recallable for conflict explanation, but its confidence must not hide a
    # current candidate merely because the old source had a high C.
    quality_confidence = assertion.confidence if assertion.status == "active" else None
    score = MemoryScorePolicy.recall_score(
        relevance=match_strength,
        freshness=assertion.freshness,
        importance=assertion.importance,
        confidence=quality_confidence,
    )
    return (
        -score.rank,
        hop_count,
        -assertion.importance,
        -(quality_confidence or 0.0),
        -_assertion_time_relevance(assertion, request),
        assertion.assertion_id,
    )


def _assertion_time_relevance(
    assertion: RecallAssertion, request: RecallRequest
) -> float:
    if request.occurred_from is None and request.occurred_to is None:
        return 0.0
    valid_from = assertion.qualifiers.get("valid_from")
    valid_to = assertion.qualifiers.get("valid_to")
    if request.occurred_from is not None and valid_to is not None:
        if str(valid_to) < request.occurred_from:
            return 0.0
    if request.occurred_to is not None and valid_from is not None:
        if str(valid_from) > request.occurred_to:
            return 0.0
    return 1.0


def _episode_time_relevance(episode: RecallEpisode, request: RecallRequest) -> float:
    if request.occurred_from is None and request.occurred_to is None:
        return 0.0
    if episode.occurred_from is None:
        return 0.0
    if (
        request.occurred_from is not None
        and episode.occurred_from < request.occurred_from
    ):
        return 0.0
    if request.occurred_to is not None and episode.occurred_from > request.occurred_to:
        return 0.0
    return 1.0


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
                detail_level=episode.detail_level,
                relevance=episode.relevance,
                occurrence_precision=episode.occurrence_precision,
                life_stage=episode.life_stage,
                temporal_label=episode.temporal_label,
                importance=episode.importance,
                freshness=episode.freshness,
                half_life_days=episode.half_life_days,
                source_event_ids=episode.source_event_ids,
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
        limits=limits,
    )


def _lexical_normalize(value: str) -> str:
    """Normalize searchable text without weakening semantic identity rules."""
    cleaned = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9\s]", "", value.casefold())
    return " ".join(cleaned.split())


def _recall_eligible(node: RecallNode) -> bool:
    """Honor the explicit projection visibility flag during traversal."""
    return node.properties.get("recall_eligible", True) is not False


def _lexical_like_patterns(query: str, terms: list[str]) -> list[str]:
    """Build SQL prefilters while retaining the deterministic Python scorer."""
    patterns = [f"%{term}%" for term in terms]
    ascii_parts = re.findall(r"[a-z0-9]+", query.casefold())
    if len(ascii_parts) > 1:
        patterns.append("%" + "%".join(ascii_parts) + "%")
    return list(dict.fromkeys(patterns))


__all__ = ["SQLiteRecallStoreMixin"]


_HARD_LIMITS = {
    "lexical_limit": 20,
    "seed_limit": 8,
    "hop_limit": 2,
    "neighbors_per_node": 12,
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
