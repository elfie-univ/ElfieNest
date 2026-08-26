"""Stable, provenance-preserving rendering of a bounded RecallBundle.

The Memory adapter returns structured records.  This renderer is the narrow
presentation bridge for callers that need text in a model prompt; it never
invent facts and it never replaces the source IDs carried by the bundle.
"""

from __future__ import annotations

from typing import Iterable

from .memory_records import RecallAssertion, RecallBundle, RecallEvidence, RecallNode


def render_recall_bundle(
    bundle: RecallBundle,
    *,
    character_limit: int | None = None,
) -> str:
    """Render a deterministic labeled memory context with a hard cap.

    Values are treated as data.  Section labels make the provenance boundary
    explicit to a downstream model and stable ordering keeps prompt caching
    effective across equivalent queries.
    """
    limit = character_limit if character_limit is not None else _bundle_limit(bundle)
    if limit < 1:
        return ""
    lines: list[str] = ["[MEMORY_DATA]"]
    _append_sources(lines, bundle)
    _append_nodes(lines, bundle.focus_nodes)
    _append_assertions(lines, bundle.assertions)
    _append_paths(lines, bundle.paths)
    _append_episodes(lines, bundle.episodes)
    _append_evidence(lines, bundle.evidence)
    _append_conflicts(lines, bundle.conflicts)
    lines.append("[/MEMORY_DATA]")
    rendered = "\n".join(lines)
    if len(rendered) <= limit:
        return rendered
    # Keep the opening and closing markers intact; trim only complete lines so
    # an excerpt can never be mistaken for a new field or instruction.
    closing = "\n[/MEMORY_DATA]"
    if limit <= len("[MEMORY_DATA]") + len(closing):
        return "[MEMORY_DATA]"[:limit]
    budget = max(0, limit - len(closing))
    prefix = rendered[:budget]
    newline = prefix.rfind("\n")
    if newline >= 0:
        prefix = prefix[:newline]
    return prefix + closing


def _bundle_limit(bundle: RecallBundle) -> int:
    raw = bundle.limits.requested.get("characters", 12000)
    return int(raw) if isinstance(raw, int) else 12000


def _append_nodes(lines: list[str], nodes: Iterable[RecallNode]) -> None:
    values = list(nodes)
    if not values:
        return
    lines.append("NODES:")
    for node in values:
        description = f" — {node.description}" if node.description else ""
        lines.append(
            f"- id={node.node_id}; type={node.node_type}; label={node.label}; "
            f"relevance={node.relevance:.3f}{description}"
        )


def _append_sources(lines: list[str], bundle: RecallBundle) -> None:
    """Put compact source identities before verbose sections.

    A hard character cap may remove descriptions or paths, but it must not
    make a bounded context look as if it had no provenance at all.
    """
    source_ids = list(
        dict.fromkeys(
            [episode.episode_id for episode in bundle.episodes]
            + [item.source_id for item in bundle.evidence]
        )
    )
    if source_ids:
        lines.append("SOURCES: " + ",".join(source_ids))


def _append_assertions(lines: list[str], assertions: Iterable[RecallAssertion]) -> None:
    values = list(assertions)
    if not values:
        return
    lines.append("ASSERTIONS:")
    for assertion in values:
        obj = (
            f"node:{assertion.object_node_id}"
            if assertion.object_node_id is not None
            else f"literal:{assertion.object_literal!r}"
        )
        qualifiers = ", ".join(
            f"{key}={value}" for key, value in sorted(assertion.qualifiers.items())
        )
        lines.append(
            f"- id={assertion.assertion_id}; {assertion.subject_id} "
            f"--{assertion.predicate}--> {obj}; status={assertion.status}; "
            f"evidence={','.join(assertion.evidence_ids)}"
            + (f"; qualifiers={qualifiers}" if qualifiers else "")
        )


def _append_paths(lines: list[str], paths: Iterable[object]) -> None:
    values = list(paths)
    if not values:
        return
    lines.append("PATHS:")
    for path in values:
        lines.append(
            f"- nodes={' -> '.join(path.node_ids)}; assertions={','.join(path.assertion_ids)}; "
            f"hops={path.hop_count}"
        )


def _append_episodes(lines: list[str], episodes: Iterable[object]) -> None:
    values = list(episodes)
    if not values:
        return
    lines.append("EPISODES:")
    for episode in values:
        lines.append(
            f"- id={episode.episode_id}; occurred={episode.occurred_from}"
            + (f"..{episode.occurred_to}" if episode.occurred_to else "")
            + f"; detail={episode.detail_level}; excerpt={episode.excerpt}"
        )


def _append_evidence(lines: list[str], evidence: Iterable[RecallEvidence]) -> None:
    values = list(evidence)
    if not values:
        return
    lines.append("EVIDENCE:")
    for item in values:
        excerpt = f"; excerpt={item.excerpt}" if item.excerpt else ""
        locator = f"; locator={item.media_locator}" if item.media_locator else ""
        lines.append(
            f"- id={item.evidence_id}; source={item.source_id}; stance={item.stance}"
            f"{locator}{excerpt}"
        )


def _append_conflicts(lines: list[str], conflicts: Iterable[object]) -> None:
    values = list(conflicts)
    if not values:
        return
    lines.append("CONFLICTS:")
    for conflict in values:
        lines.append(
            f"- assertions={','.join(conflict.assertion_ids)}; reason={conflict.reason}"
        )


__all__ = ["render_recall_bundle"]
