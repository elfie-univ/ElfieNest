"""Bounded deterministic hybrid retrieval for the SQLite Memory adapter."""

from __future__ import annotations

import sqlite3
from collections import defaultdict, deque
from typing import Iterable

from elfie.brain.memory.memory_records import (
    RecallAssertion,
    RecallBundle,
    RecallConflict,
    RecallEpisode,
    RecallLimits,
    RecallNode,
    RecallPath,
    RecallRequest,
)

from .sqlite_mixin_base import SQLiteMemoryMixinBase


class SQLiteRecallStoreMixin(SQLiteMemoryMixinBase):
    """Run lexical source search followed by a bounded local graph walk."""

    conn: sqlite3.Connection

    def recall(self, request: RecallRequest) -> RecallBundle:
        if not request.text.strip() and not request.seed_node_ids:
            return self._empty_bundle(request)

        lexical_candidates = self.search_by_content(
            request.text,
            request.lexical_limit + 1 if request.lexical_limit > 0 else 0,
        )
        lexical_truncated = len(lexical_candidates) > request.lexical_limit
        lexical = lexical_candidates[: request.lexical_limit]
        lexical_scores = dict(lexical)
        allowed_types = set(request.node_types)
        seed_ids: list[str] = []
        for node_id in request.seed_node_ids:
            resolved = self.resolve_graph_node_id(node_id)
            if resolved is None:
                continue
            node = self.get_graph_node(resolved)
            # Explicit seeds are traversal anchors.  ``node_types`` filters
            # returned focus nodes/neighbors, but must not make a caller's
            # person seed unusable when it asks for related animal/concept
            # nodes.
            if node is not None:
                seed_ids.append(resolved)
        episode_scores: dict[str, float] = {}
        for node_id, score in lexical:
            graph_node = self.get_graph_node(node_id)
            if graph_node is not None:
                if not allowed_types or graph_node.node_type in allowed_types:
                    seed_ids.append(graph_node.node_id)
            else:
                episode_scores[node_id] = score
        if episode_scores and (request.occurred_from or request.occurred_to):
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
                node = self.get_graph_node(resolved)
                if node is not None and (
                    not allowed_types or node.node_type in allowed_types
                ):
                    seed_ids.append(resolved)
        unique_seed_ids = list(dict.fromkeys(seed_ids))
        seeds_truncated = len(unique_seed_ids) > request.seed_limit
        seed_ids = unique_seed_ids[: request.seed_limit]

        assertions: dict[str, RecallAssertion] = {}
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
                )
                if len(local_candidates) > request.neighbors_per_node:
                    assertions_truncated = True
                for assertion in local_candidates[: request.neighbors_per_node]:
                    if len(assertions) >= request.assertion_limit:
                        assertions_truncated = True
                        break
                    assertions[assertion.assertion_id] = assertion
                    neighbor = _neighbor(current, assertion)
                    if neighbor is None:
                        continue
                    neighbor_node = self.get_graph_node(neighbor)
                    if neighbor_node is None:
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
            )
            if len(basic_candidates) > request.assertion_limit:
                assertions_truncated = True
            for assertion in basic_candidates[: request.assertion_limit]:
                assertions[assertion.assertion_id] = assertion

        focus_ids = list(visited)
        focus_nodes = self._focus_nodes(focus_ids, lexical_scores, request)
        assertions_tuple = tuple(
            sorted(
                assertions.values(),
                key=lambda item: (-item.relevance, item.assertion_id),
            )[: request.assertion_limit]
        )
        evidence_candidates = self.get_assertion_evidence(
            (assertion.assertion_id for assertion in assertions_tuple),
            request.evidence_limit + 1 if request.evidence_limit > 0 else 0,
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
            source_ids, episode_scores, request
        )
        conflicts = self._conflicts(assertions_tuple)
        paths = paths[: request.node_limit]
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
    ) -> tuple[RecallNode, ...]:
        nodes: list[RecallNode] = []
        allowed = set(request.node_types)
        for node_id in node_ids:
            node = self.get_graph_node(node_id)
            if node is None or (allowed and node.node_type not in allowed):
                continue
            score = max(lexical_scores.get(node_id, 0.0), node.relevance * 0.5)
            nodes.append(
                RecallNode(
                    node_id=node.node_id,
                    node_type=node.node_type,
                    label=node.label,
                    description=node.description,
                    relevance=min(1.0, score),
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
        clauses = [f"episode_id IN ({placeholders})", "lifecycle <> 'forgotten'"]
        params: list[str] = list(ids)
        if request.occurred_from is not None:
            clauses.append("occurred_from >= ?")
            params.append(request.occurred_from)
        if request.occurred_to is not None:
            clauses.append("occurred_from <= ?")
            params.append(request.occurred_to)
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
    ) -> tuple[tuple[RecallEpisode, ...], bool]:
        episode_ids = tuple(dict.fromkeys(source_ids))
        if not episode_ids:
            return (), False
        fetch_limit = request.episode_limit + 1 if request.episode_limit > 0 else 0
        if fetch_limit == 0:
            return (), bool(episode_ids)
        with self._lock:
            placeholders = ",".join("?" for _ in episode_ids)
            time_clauses: list[str] = []
            time_params: list[str] = []
            if request.occurred_from is not None:
                time_clauses.append("occurred_from >= ?")
                time_params.append(request.occurred_from)
            if request.occurred_to is not None:
                time_clauses.append("occurred_from <= ?")
                time_params.append(request.occurred_to)
            where = " AND " + " AND ".join(time_clauses) if time_clauses else ""
            rows = self.conn.execute(
                f"""SELECT episode_id, occurred_from, occurred_to,
                           content_text, summary_text, detail_level
                      FROM episodes
                     WHERE episode_id IN ({placeholders})
                       AND lifecycle <> 'forgotten'
                       {where}
                     ORDER BY occurred_from, episode_id LIMIT ?""",
                list(episode_ids) + time_params + [fetch_limit],
            ).fetchall()
        result: list[RecallEpisode] = []
        for row in rows:
            episode_id = str(row["episode_id"])
            excerpt = str(row["summary_text"] or row["content_text"])
            result.append(
                RecallEpisode(
                    episode_id=episode_id,
                    occurred_from=str(row["occurred_from"]),
                    occurred_to=row["occurred_to"],
                    excerpt=excerpt,
                    detail_level=str(row["detail_level"]),
                    relevance=direct_scores.get(episode_id, 0.5),
                )
            )
        ordered = sorted(result, key=lambda item: (-item.relevance, item.episode_id))
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
            limits=RecallLimits(
                requested=bundle.limits.requested,
                returned=dict.fromkeys(bundle.limits.returned, 0),
                truncated=bundle.limits.truncated or has_payload,
            )
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
        limits=limits,
    )


__all__ = ["SQLiteRecallStoreMixin"]
