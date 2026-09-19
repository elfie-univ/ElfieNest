"""Read-only Memory inspection and graph export for developer experiments.

The command reads a SQLite Memory database through the typed adapter.  The
source database is first copied with SQLite's online backup API, so inspecting
an open database cannot write to it or observe a torn WAL snapshot.

The generated graph files are disposable projections.  They are intended for
Neo4j Bloom or Memgraph Lab exploration and never become a second Memory
authority.
"""

from __future__ import annotations

import argparse
import binascii
import csv
import json
import re
import sqlite3
import sys
import tempfile
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import fields, is_dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Iterable, Iterator, Mapping, Sequence, Tuple
from uuid import uuid4

from elfie.brain.memory import MemorySystem, RecallRequest, render_recall_bundle
from elfie.brain.memory.memory_records import (
    ClosedEpisode,
    ConsolidationRequest,
    RecallAssertion,
    RecallEvidence,
    RecallNode,
)
from elfie.brain.observation import BrainObservation
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from infrastructure.persistence.memory.schema import SCHEMA_VERSION

DEFAULT_READ_LIMIT = 10_000
DEFAULT_SHOW_LIMIT = 50
MAX_READ_LIMIT = 100_000
MAX_EVIDENCE_PER_ASSERTION = 24
MAX_PREVIEW_AFFECTED_RECORDS = 200
_DISAMBIGUATED_LABEL = re.compile(r"^(.*?)-[0-9]+$")


class MemoryInspectionStaleError(RuntimeError):
    """Raised when a pagination cursor crosses a changed Memory boundary."""


def _encode_inspection_cursor(values: Mapping[str, str]) -> str:
    """Encode stable per-collection IDs for a read-only inspection page."""
    raw = json.dumps(dict(values), ensure_ascii=False, sort_keys=True).encode("utf-8")
    import base64

    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_inspection_cursor(value: str | None) -> dict[str, str]:
    if not value:
        return {}
    import base64

    padded = value + "=" * (-len(value) % 4)
    try:
        decoded = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
        raise ValueError("invalid memory inspection cursor") from exc
    if not isinstance(decoded, dict) or any(
        not isinstance(key, str) or not isinstance(item, str)
        for key, item in decoded.items()
    ):
        raise ValueError("invalid memory inspection cursor")
    return dict(decoded)


def _record_id(record: Any, field: str) -> str:
    value = getattr(record, field, None)
    if value is None and isinstance(record, Mapping):
        value = record.get(field)
    return str(value or "")


def _inspection_page(
    records: Sequence[Any],
    *,
    field: str,
    after: str | None,
    limit: int,
) -> tuple[tuple[Any, ...], str | None]:
    ordered = tuple(sorted(records, key=lambda item: _record_id(item, field)))
    start = 0
    if after:
        start = next(
            (
                index
                for index, item in enumerate(ordered)
                if _record_id(item, field) > after
            ),
            len(ordered),
        )
    page = ordered[start : start + limit]
    if start + len(page) >= len(ordered) or not page:
        return page, None
    return page, _record_id(page[-1], field)


def _plain(value: Any) -> Any:
    """Convert typed records into JSON-compatible values without leaking rows."""
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _plain(model_dump(mode="json"))
    if is_dataclass(value):
        return {item.name: _plain(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


class _MemoryAuditObservationSink:
    """Collect bounded Memory observations for one disposable audit request."""

    def __init__(self) -> None:
        self._events: list[BrainObservation[Any]] = []
        self._lock = RLock()

    def emit(self, event: BrainObservation[Any]) -> None:
        """Collect without allowing diagnostics to affect Memory behavior."""
        try:
            with self._lock:
                self._events.append(event)
        except Exception:
            # Developer diagnostics must never turn an otherwise valid Recall
            # into a failed Memory operation.
            return

    def snapshot(self) -> tuple[BrainObservation[Any], ...]:
        with self._lock:
            return tuple(self._events)


def _snapshot_metadata(*, generated_at: str, consistency_token: str) -> dict[str, Any]:
    """Describe this request's read boundary without inventing a revision."""
    return {
        "snapshot_id": f"memory-audit:{uuid4().hex}",
        "generated_at": generated_at,
        "consistency": "single_request",
        "source": "typed_memory_read_boundary",
        "schema_version": SCHEMA_VERSION,
        "semantic_revision": None,
        "semantic_revision_status": "unavailable",
        "read_consistency_token": consistency_token,
    }


def _recall_selection_projection(
    events: Sequence[BrainObservation[Any]],
    bundle: Any,
) -> dict[str, Any]:
    """Project the scorer's own candidate decisions for one Recall."""
    candidates: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for event in events:
        if event.boundary != "memory.recall.selection":
            continue
        if event.kind == "candidate_scored":
            candidates.append(_plain(event.payload))
        elif event.kind == "selection_summary":
            summaries.append(_plain(event.payload))
    return {
        "candidate_boundary": "scored_candidates_only",
        "candidates": candidates,
        "summaries": summaries,
        "returned_ids": {
            "nodes": [item.node_id for item in bundle.focus_nodes],
            "assertions": [item.assertion_id for item in bundle.assertions],
            "episodes": [item.episode_id for item in bundle.episodes],
            "evidence": [item.evidence_id for item in bundle.evidence],
        },
    }


def _json_text(value: Any) -> str:
    return json.dumps(
        _plain(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _csv_values(values: Iterable[str]) -> Tuple[str, ...]:
    result: list[str] = []
    for value in values:
        result.extend(part.strip() for part in value.split(","))
    return tuple(dict.fromkeys(value for value in result if value))


def _text_matches(value: str | None, query: str | None) -> bool:
    if not query:
        return True
    return query.casefold() in (value or "").casefold()


def _node_source(node: RecallNode) -> str | None:
    value = node.properties.get("genesis_submission_id")
    return str(value) if value is not None and str(value).strip() else None


def _episode_source(episode: ClosedEpisode) -> str | None:
    value = episode.genesis_submission_id
    return str(value) if value is not None and value.strip() else None


def _node_matches(
    node: RecallNode,
    *,
    node_types: Sequence[str],
    contains: str | None,
    genesis_submission: str | None,
) -> bool:
    if node_types and node.node_type not in node_types:
        return False
    if genesis_submission is not None and _node_source(node) != genesis_submission:
        return False
    if contains:
        haystack = " ".join(
            (node.label, node.description or "", _json_text(node.properties))
        )
        if contains.casefold() not in haystack.casefold():
            return False
    return True


def _episode_matches(
    episode: ClosedEpisode,
    *,
    contains: str | None,
    genesis_submission: str | None,
) -> bool:
    if (
        genesis_submission is not None
        and _episode_source(episode) != genesis_submission
    ):
        return False
    if not contains:
        return True
    haystack = " ".join(
        (
            episode.episode_id,
            episode.content_text,
            episode.summary_text or "",
            _json_text(episode.metadata),
        )
    )
    return contains.casefold() in haystack.casefold()


def _filter_graph(
    nodes: Sequence[RecallNode],
    assertions: Sequence[RecallAssertion],
    *,
    node_types: Sequence[str],
    contains: str | None,
    genesis_submission: str | None,
) -> tuple[tuple[RecallNode, ...], tuple[RecallNode, ...], tuple[RecallAssertion, ...]]:
    """Return focus nodes, one-hop context nodes and visible assertions.

    A type or text filter selects the user's focus nodes.  Their one-hop graph
    context is retained so filtering to people still shows the Elfie and the
    connected places/knowledge needed to understand the relationship.
    """
    focus = tuple(
        node
        for node in nodes
        if _node_matches(
            node,
            node_types=node_types,
            contains=contains,
            genesis_submission=genesis_submission,
        )
    )
    filtered = bool(node_types or contains or genesis_submission)
    if not filtered:
        graph_nodes = tuple(nodes)
    else:
        focus_ids = {node.node_id for node in focus}
        graph_ids = set(focus_ids)
        for assertion in assertions:
            # Expand from the original focus only.  Expanding from the
            # growing set would turn a central Elfie node into a graph-wide
            # wildcard and defeat a filter such as ``--node-type person``.
            if assertion.subject_id in focus_ids:
                if assertion.object_node_id is not None:
                    graph_ids.add(assertion.object_node_id)
            elif assertion.object_node_id in focus_ids:
                graph_ids.add(assertion.subject_id)
        graph_nodes = tuple(node for node in nodes if node.node_id in graph_ids)
    graph_ids = {node.node_id for node in graph_nodes}
    visible_assertions = tuple(
        assertion
        for assertion in assertions
        if assertion.subject_id in graph_ids
        and (assertion.object_node_id is None or assertion.object_node_id in graph_ids)
    )
    return focus, graph_nodes, visible_assertions


def _duplicate_labels(nodes: Sequence[RecallNode]) -> list[dict[str, Any]]:
    groups: dict[str, list[RecallNode]] = defaultdict(list)
    for node in nodes:
        groups[node.label.casefold()].append(node)
    duplicates = []
    for normalized, values in sorted(groups.items()):
        if len(values) < 2:
            continue
        duplicates.append(
            {
                "normalized_label": normalized,
                "nodes": [
                    {
                        "id": node.node_id,
                        "label": node.label,
                        "node_type": node.node_type,
                    }
                    for node in values
                ],
            }
        )
    return duplicates


def _possible_disambiguated_labels(nodes: Sequence[RecallNode]) -> list[dict[str, Any]]:
    """Flag labels that differ only by a numeric suffix for human review."""
    groups: dict[str, list[RecallNode]] = defaultdict(list)
    for node in nodes:
        match = _DISAMBIGUATED_LABEL.match(node.label.strip())
        if match is not None and match.group(1).strip():
            groups[match.group(1).casefold()].append(node)
        else:
            groups[node.label.casefold()].append(node)
    possible = []
    for base, values in sorted(groups.items()):
        labels = {node.label for node in values}
        if len(values) < 2 or len(labels) < 2:
            continue
        possible.append(
            {
                "base_label": base,
                "nodes": [
                    {
                        "id": node.node_id,
                        "label": node.label,
                        "node_type": node.node_type,
                    }
                    for node in values
                ],
            }
        )
    return possible


def _inspection_checks(
    *,
    integrity: Mapping[str, Any],
    nodes: Sequence[RecallNode],
    assertions: Sequence[RecallAssertion],
    episodes: Sequence[ClosedEpisode],
    confidence_threshold: float,
) -> dict[str, Any]:
    node_ids = {node.node_id for node in nodes}
    orphan_assertions = [
        {
            "id": assertion.assertion_id,
            "subject_id": assertion.subject_id,
            "object_node_id": assertion.object_node_id,
        }
        for assertion in assertions
        if assertion.subject_id not in node_ids
        or (
            assertion.object_node_id is not None
            and assertion.object_node_id not in node_ids
        )
    ]
    nodes_without_description = [
        {
            "id": node.node_id,
            "label": node.label,
            "node_type": node.node_type,
        }
        for node in nodes
        if node.node_type
        in {"elfie", "event", "knowledge", "person", "place", "self_model"}
        if not node.description or not node.description.strip()
    ]
    low_confidence_nodes = [
        {
            "id": node.node_id,
            "label": node.label,
            "node_type": node.node_type,
            "confidence": node.confidence,
        }
        for node in nodes
        if node.confidence < confidence_threshold
    ]
    no_evidence_assertions = [
        assertion.assertion_id for assertion in assertions if not assertion.evidence_ids
    ]
    duplicate_labels = _duplicate_labels(nodes)
    possible_disambiguated_labels = _possible_disambiguated_labels(nodes)
    pending_ids = [
        episode.episode_id
        for episode in episodes
        if episode.projection_revision is None
    ]

    checks = [
        {
            "name": "sqlite_integrity",
            "status": "pass"
            if bool(integrity.get("all_assertions_grounded"))
            else "warn",
            "detail": dict(integrity),
        },
        {
            "name": "assertion_endpoints",
            "status": "pass" if not orphan_assertions else "warn",
            "count": len(orphan_assertions),
            "detail": "没有悬空关系"
            if not orphan_assertions
            else "存在关系引用不存在的节点",
        },
        {
            "name": "assertion_evidence",
            "status": "pass" if not no_evidence_assertions else "warn",
            "count": len(no_evidence_assertions),
            "detail": "所有关系都有证据"
            if not no_evidence_assertions
            else "存在没有证据的关系",
        },
        {
            "name": "empty_descriptions",
            "status": "pass" if not nodes_without_description else "review",
            "count": len(nodes_without_description),
            "detail": "所有节点都有描述"
            if not nodes_without_description
            else "这些节点需要人工看看是否应该补描述",
        },
        {
            "name": "low_confidence_nodes",
            "status": "pass" if not low_confidence_nodes else "review",
            "count": len(low_confidence_nodes),
            "threshold": confidence_threshold,
            "detail": "没有低于阈值的节点"
            if not low_confidence_nodes
            else "低置信度不等于错误，先列出来人工复核",
        },
        {
            "name": "duplicate_labels",
            "status": "pass" if not duplicate_labels else "review",
            "count": len(duplicate_labels),
            "detail": "没有完全相同的标签"
            if not duplicate_labels
            else "存在同名节点，需要确认是同一个人还是两个人",
        },
        {
            "name": "possible_disambiguated_labels",
            "status": "pass" if not possible_disambiguated_labels else "review",
            "count": len(possible_disambiguated_labels),
            "detail": "没有发现数字后缀导致的疑似重名"
            if not possible_disambiguated_labels
            else "这些标签可能是同名实体的自动消歧结果，需要人工确认",
        },
        {
            "name": "episodes_without_projection_revision",
            "status": "pass" if not pending_ids else "review",
            "count": len(pending_ids),
            "detail": "所有 Episode 都有整理版本"
            if not pending_ids
            else "这些 Episode 还没有 projection_revision",
        },
    ]
    return {
        "checks": checks,
        "orphan_assertions": orphan_assertions,
        "assertions_without_evidence": no_evidence_assertions,
        "nodes_without_description": nodes_without_description,
        "low_confidence_nodes": low_confidence_nodes,
        "duplicate_labels": duplicate_labels,
        "possible_disambiguated_labels": possible_disambiguated_labels,
        "episodes_without_projection_revision": pending_ids,
    }


def build_inspection_report(
    store: SQLiteMemoryStoreAdapter,
    *,
    database: str,
    node_types: Sequence[str] = (),
    contains: str | None = None,
    genesis_submission: str | None = None,
    confidence_threshold: float = 0.6,
    limit: int = DEFAULT_READ_LIMIT,
    cursor: str | None = None,
) -> dict[str, Any]:
    """Build a typed, disposable inspection report from one Memory database."""
    generated_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    bounded_limit = max(1, min(int(limit), MAX_READ_LIMIT))
    cursor_values = _decode_inspection_cursor(cursor)
    consistency_token = store.read_consistency_token()
    expected_consistency_token = cursor_values.get("snapshot_token")
    if (
        expected_consistency_token is not None
        and expected_consistency_token != consistency_token
    ):
        raise MemoryInspectionStaleError(
            "Memory 在分页期间发生变化；当前读取边界已过期，请重新加载"
        )
    all_episodes = store.list_episodes(limit=MAX_READ_LIMIT, include_forgotten=True)
    all_nodes = store.list_graph_nodes(limit=MAX_READ_LIMIT)
    all_assertions = store.list_graph_assertions(limit=MAX_READ_LIMIT)
    all_evidence = store.list_memory_evidence(limit=MAX_READ_LIMIT)
    focus_nodes, graph_nodes, visible_assertions = _filter_graph(
        all_nodes,
        all_assertions,
        node_types=tuple(node_types),
        contains=contains,
        genesis_submission=genesis_submission,
    )
    episodes = tuple(
        episode
        for episode in all_episodes
        if _episode_matches(
            episode,
            contains=contains,
            genesis_submission=genesis_submission,
        )
    )
    evidence: tuple[RecallEvidence, ...] = ()
    if visible_assertions:
        evidence = store.get_assertion_evidence(
            (assertion.assertion_id for assertion in visible_assertions),
            limit=min(
                MAX_READ_LIMIT,
                max(1, len(visible_assertions) * MAX_EVIDENCE_PER_ASSERTION),
            ),
        )

    page_episodes, next_episode_cursor = _inspection_page(
        episodes,
        field="episode_id",
        after=cursor_values.get("episodes"),
        limit=bounded_limit,
    )
    page_nodes, next_node_cursor = _inspection_page(
        graph_nodes,
        field="node_id",
        after=cursor_values.get("nodes"),
        limit=bounded_limit,
    )
    page_assertions, next_assertion_cursor = _inspection_page(
        visible_assertions,
        field="assertion_id",
        after=cursor_values.get("assertions"),
        limit=bounded_limit,
    )
    page_evidence, next_evidence_cursor = _inspection_page(
        all_evidence,
        field="evidence_id",
        after=cursor_values.get("evidence"),
        limit=bounded_limit,
    )
    page_node_ids = {node.node_id for node in page_nodes}
    context_node_ids = {
        endpoint
        for assertion in page_assertions
        for endpoint in (assertion.subject_id, assertion.object_node_id)
        if endpoint is not None and endpoint not in page_node_ids
    }
    context_nodes = tuple(
        node for node in graph_nodes if node.node_id in context_node_ids
    )
    next_cursor_values = {
        key: value
        for key, value in (
            ("episodes", next_episode_cursor),
            ("nodes", next_node_cursor),
            ("assertions", next_assertion_cursor),
            ("evidence", next_evidence_cursor),
        )
        if value is not None
    }
    if next_cursor_values:
        next_cursor_values["snapshot_token"] = consistency_token
    next_cursor = (
        _encode_inspection_cursor(next_cursor_values) if next_cursor_values else None
    )

    integrity = store.integrity_report()
    total_counts = {
        "episodes": store.count_episodes(include_forgotten=True),
        "nodes": store.count_graph_nodes(),
        "assertions": store.count_graph_assertions(),
        "evidence": store.count_memory_evidence(),
    }
    loaded_counts = {
        "episodes": len(page_episodes),
        "nodes": len(page_nodes),
        "assertions": len(page_assertions),
        "evidence": len(page_evidence),
        "evidence_for_visible_assertions": len(evidence),
    }
    filters_applied = bool(node_types or contains or genesis_submission)
    matched_counts = {
        "episodes": len(episodes),
        "nodes": len(focus_nodes) if filters_applied else len(graph_nodes),
        "assertions": len(visible_assertions),
        "evidence": len(all_evidence),
    }
    truncated = {
        key: key in next_cursor_values
        for key in ("episodes", "nodes", "assertions", "evidence")
    }
    coverage = (
        "partial"
        if next_cursor is not None
        else ("filtered" if filters_applied else "complete")
    )
    snapshot = _snapshot_metadata(
        generated_at=generated_at,
        consistency_token=consistency_token,
    )
    snapshot.update(
        {
            "coverage": coverage,
            "read_limit": bounded_limit,
            "filters_applied": filters_applied,
            "next_cursor": next_cursor,
        }
    )
    source_counts = Counter(_node_source(node) or "<none>" for node in all_nodes)
    episode_source_counts = Counter(
        _episode_source(episode) or "<none>" for episode in all_episodes
    )
    report: dict[str, Any] = {
        "format": "elfienest.memory-audit.v1",
        "generated_at": generated_at,
        "snapshot": snapshot,
        "database": database,
        "elfie_id": store.elfie_id,
        "schema_version": SCHEMA_VERSION,
        "filters": {
            "node_types": list(node_types),
            "contains": contains,
            "genesis_submission": genesis_submission,
            "confidence_threshold": confidence_threshold,
            "read_limit": bounded_limit,
        },
        "counts": {
            **total_counts,
            "evidence_for_visible_assertions": len(evidence),
            "focus_nodes": len(focus_nodes),
            "graph_nodes": len(graph_nodes),
            "visible_assertions": len(visible_assertions),
            "integrity": dict(integrity),
        },
        "loaded_counts": loaded_counts,
        "matched_counts": matched_counts,
        "coverage": {
            "status": coverage,
            "truncated": truncated,
            "filters_applied": filters_applied,
            "read_limit": bounded_limit,
        },
        "pagination": {
            "page_size": bounded_limit,
            "next_cursor": next_cursor,
            "cursor": cursor,
        },
        "node_type_counts": dict(
            sorted(Counter(node.node_type for node in all_nodes).items())
        ),
        "predicate_counts": dict(
            sorted(Counter(assertion.predicate for assertion in all_assertions).items())
        ),
        "source_submission_counts": dict(sorted(source_counts.items())),
        "episode_source_submission_counts": dict(sorted(episode_source_counts.items())),
        "focus_node_ids": [node.node_id for node in focus_nodes],
        "checks": _inspection_checks(
            integrity=integrity,
            nodes=all_nodes,
            assertions=all_assertions,
            episodes=all_episodes,
            confidence_threshold=confidence_threshold,
        ),
        "data": {
            "nodes": [_plain(node) for node in page_nodes],
            "context_nodes": [_plain(node) for node in context_nodes],
            "assertions": [_plain(assertion) for assertion in page_assertions],
            "episodes": [_plain(episode) for episode in page_episodes],
            "evidence": [_plain(item) for item in page_evidence],
        },
    }
    return report


def _literal_target(assertion: Mapping[str, Any]) -> str:
    return "literal:" + str(assertion["assertion_id"])


def _graph_rows(
    report: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    data = report["data"]
    focus_ids = set(report["focus_node_ids"])
    nodes = list(data["nodes"])
    node_ids = {str(node["node_id"]) for node in nodes}
    edges: list[dict[str, Any]] = []
    literals: list[dict[str, Any]] = []
    for assertion in data["assertions"]:
        object_id = assertion.get("object_node_id")
        target = str(object_id) if object_id is not None else _literal_target(assertion)
        if target not in node_ids and object_id is None:
            literal = {
                "node_id": target,
                "node_type": "literal",
                "label": str(assertion.get("object_literal")),
                "description": None,
                "relevance": 0.0,
                "importance": assertion.get("importance", 0.5),
                "confidence": assertion.get("confidence", 0.5),
                "freshness": 1.0,
                "half_life_days": 30.0,
                "properties": {"literal": assertion.get("object_literal")},
                "focus": False,
            }
            literals.append(literal)
            node_ids.add(target)
        if str(assertion["subject_id"]) not in node_ids:
            continue
        edges.append(
            {
                "id": assertion["assertion_id"],
                "source": assertion["subject_id"],
                "target": target,
                "predicate": assertion["predicate"],
                "status": assertion.get("status"),
                "confidence": assertion.get("confidence"),
                "importance": assertion.get("importance"),
                "evidence_ids": assertion.get("evidence_ids", []),
                "object_literal": assertion.get("object_literal"),
            }
        )
    for node in nodes:
        node["focus"] = str(node["node_id"]) in focus_ids or not focus_ids
    return nodes + literals, edges


def _write_csv(
    path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: _json_text(value)
                    if isinstance(value, (dict, list, tuple))
                    else ""
                    if value is None
                    else value
                    for key, value in row.items()
                }
            )


def _cypher_string(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _write_graph_cypher(
    path: Path, nodes: Sequence[Mapping[str, Any]], edges: Sequence[Mapping[str, Any]]
) -> None:
    lines = [
        "// Disposable projection generated by developer memory_audit.",
        "// Run in Neo4j Browser or Memgraph Lab; Memory remains authoritative in SQLite.",
    ]
    for node in nodes:
        properties = {
            "id": node["node_id"],
            "node_type": node["node_type"],
            "label": node["label"],
            "description": node.get("description"),
            "importance": node.get("importance"),
            "confidence": node.get("confidence"),
            "focus": node.get("focus", False),
            "properties_json": _json_text(node.get("properties", {})),
        }
        assignments = ", ".join(
            f"n.{key} = {_cypher_string(value)}"
            for key, value in properties.items()
            if value is not None
        )
        lines.append(
            f"MERGE (n:MemoryNode {{id: {_cypher_string(node['node_id'])}}}) "
            f"SET {assignments};"
        )
    for edge in edges:
        source = _cypher_string(edge["source"])
        target = _cypher_string(edge["target"])
        properties = {
            "id": edge["id"],
            "predicate": edge["predicate"],
            "status": edge.get("status"),
            "confidence": edge.get("confidence"),
            "importance": edge.get("importance"),
            "evidence_ids_json": _json_text(edge.get("evidence_ids", [])),
            "object_literal_json": _json_text(edge.get("object_literal")),
        }
        assignments = ", ".join(
            f"r.{key} = {_cypher_string(value)}"
            for key, value in properties.items()
            if value is not None
        )
        lines.append(
            f"MATCH (s:MemoryNode {{id: {source}}}), (o:MemoryNode {{id: {target}}}) "
            f"MERGE (s)-[r:ASSERTION {{id: {_cypher_string(edge['id'])}}}]->(o) "
            f"SET {assignments};"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_inspection_bundle(report: Mapping[str, Any], output_dir: Path) -> Path:
    """Write JSON/CSV/Cypher projections under a caller-selected disposable dir."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    nodes, edges = _graph_rows(report)
    _write_csv(
        output_dir / "nodes.csv",
        (
            "id",
            "node_type",
            "label",
            "description",
            "importance",
            "confidence",
            "relevance",
            "focus",
            "properties_json",
        ),
        (
            {
                "id": node["node_id"],
                "node_type": node["node_type"],
                "label": node["label"],
                "description": node.get("description"),
                "importance": node.get("importance"),
                "confidence": node.get("confidence"),
                "relevance": node.get("relevance"),
                "focus": node.get("focus", False),
                "properties_json": node.get("properties", {}),
            }
            for node in nodes
        ),
    )
    _write_csv(
        output_dir / "edges.csv",
        (
            "id",
            "source",
            "target",
            "predicate",
            "status",
            "confidence",
            "importance",
            "evidence_ids",
            "object_literal_json",
        ),
        edges,
    )
    _write_csv(
        output_dir / "episodes.csv",
        (
            "id",
            "occurred_from",
            "occurred_to",
            "event_kind",
            "summary",
            "content",
            "importance",
            "attribution",
            "source_submission",
            "metadata_json",
        ),
        (
            {
                "id": episode["episode_id"],
                "occurred_from": episode.get("occurred_from"),
                "occurred_to": episode.get("occurred_to"),
                "event_kind": episode.get("event_kind"),
                "summary": episode.get("summary_text"),
                "content": episode.get("content_text"),
                "importance": episode.get("importance"),
                "attribution": episode.get("attribution"),
                "source_submission": episode.get("genesis_submission_id"),
                "metadata_json": episode.get("metadata", {}),
            }
            for episode in report["data"]["episodes"]
        ),
    )
    _write_csv(
        output_dir / "evidence.csv",
        (
            "id",
            "source_id",
            "source_type",
            "excerpt",
            "stance",
            "source_version",
            "captured_at",
            "attribution",
            "reliability",
        ),
        (
            {
                "id": item["evidence_id"],
                "source_id": item.get("source_id"),
                "source_type": item.get("source_type"),
                "excerpt": item.get("excerpt"),
                "stance": item.get("stance"),
                "source_version": item.get("source_version"),
                "captured_at": item.get("captured_at"),
                "attribution": item.get("attribution"),
                "reliability": item.get("source_reliability_class"),
            }
            for item in report["data"]["evidence"]
        ),
    )
    _write_graph_cypher(output_dir / "graph.cypher", nodes, edges)
    (output_dir / "README.txt").write_text(
        "This is a disposable projection of SQLite Memory.\n"
        "- Neo4j: run graph.cypher, then open the imported graph in Bloom.\n"
        "- Memgraph: run graph.cypher in Lab.\n"
        "- SQLite remains the only Memory authority; do not write edits back from the graph tool.\n",
        encoding="utf-8",
    )
    return output_dir


@contextmanager
def _read_only_store(
    database: Path,
    *,
    elfie_id: str | None = None,
) -> Iterator[SQLiteMemoryStoreAdapter]:
    """Open a temporary adapter copy while keeping the source database read-only."""
    source_path = database.expanduser().resolve()
    if not source_path.is_file():
        raise ValueError(f"Memory database does not exist: {source_path}")
    with tempfile.TemporaryDirectory(prefix="elfienest-memory-audit-") as temp_dir:
        # The macOS default temp root may itself be a symlink (for example
        # ``/var`` -> ``/private/var``); the production SQLite path guard
        # intentionally rejects symlinked directory components.
        target_path = Path(temp_dir).resolve() / "knowledge.sqlite"
        source_uri = source_path.as_uri() + "?mode=ro"
        with sqlite3.connect(source_uri, uri=True) as source:
            with sqlite3.connect(str(target_path)) as target:
                source.backup(target)
        with SQLiteMemoryStoreAdapter(target_path, elfie_id=elfie_id) as store:
            yield store


@contextmanager
def _sandbox_store(
    database: Path,
    *,
    elfie_id: str | None = None,
) -> Iterator[SQLiteMemoryStoreAdapter]:
    """Open an explicitly disposable writable copy for developer previews."""
    source_path = database.expanduser().resolve()
    if not source_path.is_file():
        raise ValueError(f"Memory database does not exist: {source_path}")
    with tempfile.TemporaryDirectory(prefix="elfienest-memory-sandbox-") as temp_dir:
        target_path = Path(temp_dir).resolve() / "knowledge.sqlite"
        source_uri = source_path.as_uri() + "?mode=ro"
        with sqlite3.connect(source_uri, uri=True) as source:
            with sqlite3.connect(str(target_path)) as target:
                source.backup(target)
        with SQLiteMemoryStoreAdapter(target_path, elfie_id=elfie_id) as store:
            yield store


def _print_inspection(report: Mapping[str, Any], show_limit: int) -> None:
    counts = report["counts"]
    print(f"Memory 总览: {report['database']}")
    print(
        "总量: "
        f"Episode {counts['episodes']} | 节点 {counts['nodes']} | "
        f"关系 {counts['assertions']} | 证据 {counts['integrity'].get('evidence', 0)}"
    )
    print(
        "节点类型: "
        + ", ".join(
            f"{key}={value}" for key, value in report["node_type_counts"].items()
        )
    )
    print(
        "筛选后: "
        f"焦点节点 {counts['focus_nodes']} | 图节点 {counts['graph_nodes']} | "
        f"关系 {counts['visible_assertions']}"
    )
    print("检查:")
    for check in report["checks"]["checks"]:
        print(f"- [{check['status']}] {check['name']}: {check.get('detail', '')}")
    focus_ids = set(report["focus_node_ids"])
    shown = 0
    if focus_ids:
        print("焦点节点:")
        for node in report["data"]["nodes"]:
            if node["node_id"] not in focus_ids:
                continue
            print(
                f"- [{node['node_type']}] {node['label']} "
                f"(confidence={node['confidence']:.2f}, importance={node['importance']:.2f})"
            )
            shown += 1
            if shown >= show_limit:
                break
    if counts["focus_nodes"] > shown:
        print(f"... 其余 {counts['focus_nodes'] - shown} 个焦点节点见 report.json")


def build_recall_report(
    store: SQLiteMemoryStoreAdapter,
    request: RecallRequest,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    request = (
        request
        if request.recall_id is not None
        else replace(request, recall_id=f"memory-audit-recall:{uuid4().hex}")
    )
    observation_sink = _MemoryAuditObservationSink()
    binder = getattr(store, "bind_observation_sink", None)
    if callable(binder):
        binder(observation_sink)
    started = time.perf_counter()
    bundle = store.recall(request)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    return {
        "format": "elfienest.memory-recall-audit.v1",
        "generated_at": generated_at,
        "snapshot": _snapshot_metadata(
            generated_at=generated_at,
            consistency_token=store.read_consistency_token(),
        ),
        "request": _plain(request),
        "elapsed_ms": elapsed_ms,
        "counts": {
            "focus_nodes": len(bundle.focus_nodes),
            "assertions": len(bundle.assertions),
            "paths": len(bundle.paths),
            "episodes": len(bundle.episodes),
            "evidence": len(bundle.evidence),
            "conflicts": len(bundle.conflicts),
            "truncated": bundle.limits.truncated,
        },
        "bundle": _plain(bundle),
        "selection": _recall_selection_projection(
            observation_sink.snapshot(),
            bundle,
        ),
        "rendered": render_recall_bundle(bundle),
    }


class _DeterministicMemoryPreviewModel:
    """Return an empty grounded proposal so Consolidation uses its local extractor."""

    def ask_with_food(
        self,
        prompt: str,
        *,
        food_key: str | None,
        elfie_id: str | None,
        scene: str,
        semantic_role: str,
        energy: float,
        task_complexity: int,
        allowed_tools: list[str] | None,
    ) -> str:
        del (
            prompt,
            food_key,
            elfie_id,
            scene,
            semantic_role,
            energy,
            task_complexity,
            allowed_tools,
        )
        return '{"nodes":[],"mentions":[],"assertions":[]}'


def _preview_record_ids(report: Mapping[str, Any]) -> dict[str, set[str]]:
    data = report.get("data", {})
    return {
        "episodes": {str(item["episode_id"]) for item in data.get("episodes", [])},
        "nodes": {str(item["node_id"]) for item in data.get("nodes", [])},
        "assertions": {
            str(item["assertion_id"]) for item in data.get("assertions", [])
        },
        "evidence": {str(item["evidence_id"]) for item in data.get("evidence", [])},
    }


def _preview_counts(report: Mapping[str, Any]) -> dict[str, int]:
    counts = report.get("counts", {})
    return {
        key: int(counts.get(key, 0))
        for key in (
            "episodes",
            "nodes",
            "assertions",
            "evidence_for_visible_assertions",
        )
    }


def build_add_episode_preview(
    store: SQLiteMemoryStoreAdapter,
    *,
    content_text: str,
    summary_text: str | None = None,
    mode: str = "deterministic_local",
) -> dict[str, Any]:
    """Run the real Episode -> Consolidation path against a disposable store copy."""
    operation_id = f"memory-audit-add:{uuid4().hex}"
    started_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    started = time.perf_counter()
    before = build_inspection_report(
        store,
        database="sandbox",
        limit=DEFAULT_READ_LIMIT,
    )
    episode_id = f"preview-episode:{uuid4().hex}"
    episode = ClosedEpisode(
        episode_id=episode_id,
        idempotency_key=f"{operation_id}:episode",
        occurred_from=started_at,
        content_text=content_text,
        summary_text=summary_text.strip()
        if summary_text and summary_text.strip()
        else None,
        event_kind="developer_preview",
        metadata={"developer_preview": True, "operation_id": operation_id},
    )
    status = "failed"
    receipt: dict[str, Any] = {}
    error: dict[str, str] | None = None
    try:
        memory = MemorySystem(store, elfie_id=store.elfie_id)
        episode_receipt = memory.record_closed_episode(episode)
        consolidation_receipt = memory.run_consolidation_batch(
            ConsolidationRequest(
                max_episodes=1,
                worker_id=operation_id,
            ),
            model_port=_DeterministicMemoryPreviewModel(),
        )
        receipt = {
            "episode": _plain(episode_receipt),
            "consolidation": _plain(consolidation_receipt),
        }
        status = (
            "completed" if consolidation_receipt.consolidated_episode_ids else "failed"
        )
        if (
            consolidation_receipt.consolidated_episode_ids
            and consolidation_receipt.errors
        ):
            status = "partial"
    except Exception as exc:  # noqa: BLE001 - preview reports the real failure
        error = {"type": type(exc).__name__, "message": str(exc)}

    after = build_inspection_report(
        store,
        database="sandbox",
        limit=DEFAULT_READ_LIMIT,
    )
    before_ids = _preview_record_ids(before)
    after_ids = _preview_record_ids(after)
    added = {
        key: sorted(after_ids[key] - before_ids[key])[:MAX_PREVIEW_AFFECTED_RECORDS]
        for key in before_ids
    }
    affected: dict[str, list[dict[str, Any]]] = {}
    for key, id_field in (
        ("episodes", "episode_id"),
        ("nodes", "node_id"),
        ("assertions", "assertion_id"),
        ("evidence", "evidence_id"),
    ):
        wanted = set(added[key])
        affected[key] = [
            _plain(item)
            for item in after["data"][key]
            if str(item.get(id_field)) in wanted
        ][:MAX_PREVIEW_AFFECTED_RECORDS]
    return {
        "format": "elfienest.memory-audit.add-episode-preview.v1",
        "operation": {
            "operation_id": operation_id,
            "started_at": started_at,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "status": status,
            "mode": mode,
            "sandbox": True,
            "production_mutated": False,
            "cleanup": "automatic",
        },
        "input": {
            "episode_id": episode_id,
            "content_chars": len(content_text),
            "summary": episode.summary_text,
        },
        "before": {"counts": _preview_counts(before)},
        "after": {"counts": _preview_counts(after)},
        "changes": {"added_ids": added, "affected": affected},
        "receipt": receipt,
        "error": error,
    }


def _print_recall(report: Mapping[str, Any]) -> None:
    counts = report["counts"]
    print(
        f"召回耗时: {report['elapsed_ms']} ms | "
        f"节点 {counts['focus_nodes']} | 关系 {counts['assertions']} | "
        f"路径 {counts['paths']} | Episode {counts['episodes']} | "
        f"证据 {counts['evidence']} | 截断={counts['truncated']}"
    )
    for node in report["bundle"]["focus_nodes"]:
        print(
            f"- [{node['node_type']}] {node['label']} relevance={node['relevance']:.3f}"
        )
    if report["rendered"]:
        print("\n--- 可供模型使用的有来源文本 ---")
        print(report["rendered"])


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m devtools.memory_audit",
        description="只读检查 Elfie Memory，并导出 Neo4j/Memgraph 图数据。",
    )
    subparsers = parser.add_subparsers(dest="command")
    inspect_parser = subparsers.add_parser(
        "inspect", help="查看现有数据库总量、筛选节点并导出图数据"
    )
    inspect_parser.add_argument(
        "--db", required=True, type=Path, help="knowledge.sqlite"
    )
    inspect_parser.add_argument("--elfie-id", default=None)
    inspect_parser.add_argument("--node-type", action="append", default=[])
    inspect_parser.add_argument(
        "--contains", default=None, help="标签、描述或属性包含的文字"
    )
    inspect_parser.add_argument("--genesis-submission", default=None)
    inspect_parser.add_argument("--confidence-threshold", type=float, default=0.6)
    inspect_parser.add_argument("--limit", type=int, default=DEFAULT_READ_LIMIT)
    inspect_parser.add_argument("--show-limit", type=int, default=DEFAULT_SHOW_LIMIT)
    inspect_parser.add_argument("--output-dir", type=Path, default=None)
    inspect_parser.add_argument(
        "--json", action="store_true", help="把完整报告打印到 stdout"
    )

    recall_parser = subparsers.add_parser(
        "recall", help="用真实数据库跑一次只读召回并展示路径/证据"
    )
    recall_parser.add_argument(
        "--db", required=True, type=Path, help="knowledge.sqlite"
    )
    recall_parser.add_argument("--elfie-id", default=None)
    recall_parser.add_argument("--query", required=True)
    recall_parser.add_argument(
        "--mode", choices=("basic", "local", "basic_local"), default="basic_local"
    )
    recall_parser.add_argument("--node-type", action="append", default=[])
    recall_parser.add_argument("--relation-type", action="append", default=[])
    recall_parser.add_argument("--occurred-from", default=None)
    recall_parser.add_argument("--occurred-to", default=None)
    recall_parser.add_argument("--limit", type=int, default=20)
    recall_parser.add_argument("--character-limit", type=int, default=12000)
    recall_parser.add_argument("--output-dir", type=Path, default=None)
    recall_parser.add_argument(
        "--json", action="store_true", help="把完整报告打印到 stdout"
    )
    return parser


def _run_inspect(args: argparse.Namespace) -> int:
    node_types = _csv_values(args.node_type)
    if args.limit < 1 or args.show_limit < 1:
        raise ValueError("limit and show-limit must be positive")
    if not 0.0 <= args.confidence_threshold <= 1.0:
        raise ValueError("confidence-threshold must be between 0 and 1")
    with _read_only_store(args.db, elfie_id=args.elfie_id) as store:
        report = build_inspection_report(
            store,
            database=str(args.db.expanduser().resolve()),
            node_types=node_types,
            contains=args.contains,
            genesis_submission=args.genesis_submission,
            confidence_threshold=args.confidence_threshold,
            limit=args.limit,
        )
    if args.output_dir is not None:
        print(f"已写入: {write_inspection_bundle(report, args.output_dir)}")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_inspection(report, args.show_limit)
    return 0


def _run_recall(args: argparse.Namespace) -> int:
    if args.limit < 1 or args.character_limit < 1:
        raise ValueError("limit and character-limit must be positive")
    limit = min(args.limit, 200)
    request = RecallRequest(
        text=args.query,
        mode=args.mode,
        node_types=_csv_values(args.node_type),
        relation_types=_csv_values(args.relation_type),
        occurred_from=args.occurred_from,
        occurred_to=args.occurred_to,
        lexical_limit=limit,
        seed_limit=min(limit, 20),
        node_limit=limit,
        assertion_limit=limit,
        episode_limit=min(limit, 20),
        evidence_limit=min(limit, 50),
        character_limit=args.character_limit,
    )
    with _read_only_store(args.db, elfie_id=args.elfie_id) as store:
        report = build_recall_report(store, request)
    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "recall.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (args.output_dir / "recall.txt").write_text(
            report["rendered"] + "\n", encoding="utf-8"
        )
        print(f"已写入: {args.output_dir}")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_recall(report)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command is None:
        _parser().print_help()
        return 2
    try:
        if args.command == "inspect":
            return _run_inspect(args)
        if args.command == "recall":
            return _run_recall(args)
    except (OSError, sqlite3.Error, ValueError) as error:
        print(f"memory-audit: {error}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
