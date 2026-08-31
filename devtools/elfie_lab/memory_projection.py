"""Deterministic presentation projection for Elfie memory and cognition."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Protocol, Sequence, Tuple, TypedDict

from devtools.elfie_lab.topic_projection import TopicPayload, build_topics
from elfie.brain.memory.memory_records import (
    ClosedEpisode,
    MemoryInspectionSnapshot,
    RecallAssertion,
    RecallNode,
)

MAX_ITEMS = 20
MAX_RELATION_LINKS = 32
RELATION_LABELS: Dict[str, str] = {
    "owner": "主人",
    "family": "家人",
    "friend": "朋友",
    "acquaintance": "认识",
}
RINGS: Tuple[Tuple[str, str], ...] = (
    ("self", "自我"),
    ("family", "家人"),
    ("nest", "巢穴"),
    ("society", "社会"),
    ("outside", "外部世界"),
)


class GraphPayload(TypedDict):
    nodes: List[Dict[str, Any]]
    links: List[Dict[str, Any]]


class WorldModelPayload(TypedDict):
    summary: str
    rings: List[Dict[str, Any]]


class MemoryCognitionPayload(TypedDict):
    topics: List[TopicPayload]
    important_events: List[Dict[str, Any]]
    relations: GraphPayload
    knowledge: GraphPayload
    world_understanding: str
    world_model: WorldModelPayload


class ProjectionMemory(Protocol):
    def memory_inspection_snapshot(
        self,
        *,
        episode_limit: int = 1000,
        node_limit: int = 1000,
        assertion_limit: int = 800,
    ) -> MemoryInspectionSnapshot: ...


def build_memory_cognition(
    memory: ProjectionMemory,
    elfie_name: str,
) -> MemoryCognitionPayload:
    """Project graph memory into a bounded, deterministic UI payload."""
    snapshot = memory.memory_inspection_snapshot(
        episode_limit=1000,
        node_limit=1000,
        assertion_limit=800,
    )
    return {
        **_build_typed_memory_cognition(memory, elfie_name, snapshot),
    }


def _build_typed_memory_cognition(
    memory: ProjectionMemory,
    elfie_name: str,
    snapshot: MemoryInspectionSnapshot,
) -> MemoryCognitionPayload:
    """Build the Lab payload from the typed Memory inspection boundary."""
    episodes = snapshot.episodes
    nodes = snapshot.nodes
    world_understanding = next(
        (node.label for node in nodes if node.properties.get("core_key") == "world"),
        "",
    )
    relation_nodes, relation_links = _typed_relation_graph(
        nodes, snapshot.assertions, elfie_name
    )
    knowledge_nodes, knowledge_links = _typed_knowledge_graph(
        nodes, snapshot.assertions
    )
    return {
        "topics": build_topics(episodes, MAX_ITEMS),
        "important_events": _important_events(episodes),
        "relations": {"nodes": relation_nodes, "links": relation_links},
        "knowledge": {"nodes": knowledge_nodes, "links": knowledge_links},
        "world_understanding": world_understanding,
        "world_model": _world_model(world_understanding, nodes),
    }


def _episode_metadata(episode: ClosedEpisode) -> Dict[str, Any]:
    metadata = dict(episode.metadata)
    metadata.update(
        {
            "emotion": episode.emotion or "",
            "emotion_intensity": episode.emotion_intensity or 0.0,
            "importance": episode.importance,
            "timestamp": episode.occurred_from or "",
            "people": metadata.get("people", []),
            "detail_level": episode.detail_level,
            "lifecycle": episode.lifecycle,
            "source_event_ids": list(episode.source_event_ids),
        }
    )
    return metadata


def _node_metadata(node: RecallNode) -> Dict[str, Any]:
    metadata = dict(node.properties)
    metadata.setdefault("importance", node.importance)
    metadata.setdefault("confidence", node.confidence)
    return metadata


def _typed_relation_graph(
    nodes: Sequence[RecallNode],
    assertions: Sequence[RecallAssertion],
    elfie_name: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    selected = _rank_nodes(
        [
            node
            for node in nodes
            if node.node_type in {"entity", "person", "elfie", "pet", "animal", "group"}
        ]
    )[: MAX_ITEMS - 1]
    node_ids = {node.node_id for node in selected}
    rendered_nodes = [
        {"id": "self", "label": elfie_name, "kind": "self", "weight": 1.0}
    ]
    rendered_nodes.extend(
        {
            "id": node.node_id,
            "label": node.label[:24],
            "kind": _entity_kind(node),
            "weight": _weight(_node_metadata(node).get("importance"), 0.55),
        }
        for node in selected
    )
    links: list[dict[str, Any]] = []
    for node in selected:
        metadata = _node_metadata(node)
        relationship = metadata.get("relationship") or metadata.get(
            "relationship_label"
        )
        relation_kind = metadata.get("relation_kind") or metadata.get(
            "relationship_key"
        )
        if isinstance(relationship, str) and relationship.strip():
            links.append(
                {
                    "source": "self",
                    "target": node.node_id,
                    "label": relationship.strip(),
                    "relation_kind": str(relation_kind or "relationship"),
                    "weight": _weight(metadata.get("importance"), 0.55),
                }
            )
    for assertion in assertions:
        source = assertion.subject_id
        target = assertion.object_node_id
        if source not in node_ids or target not in node_ids:
            continue
        links.append(
            {
                "source": source,
                "target": target,
                "label": RELATION_LABELS.get(assertion.predicate, assertion.predicate),
                "relation_kind": assertion.predicate,
                "weight": _weight(assertion.importance, 0.5),
            }
        )
    return rendered_nodes, sorted(links, key=_link_key)[:MAX_RELATION_LINKS]


def _typed_knowledge_graph(
    nodes: Sequence[RecallNode],
    assertions: Sequence[RecallAssertion],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    selected = _rank_nodes(
        [
            node
            for node in nodes
            if node.node_type
            in {"knowledge", "pattern", "claim", "concept", "theory", "law"}
        ]
    )[:MAX_ITEMS]
    rendered_nodes = [
        {
            "id": node.node_id,
            "label": node.label[:48],
            "kind": _knowledge_kind(node),
            "weight": _weight(_node_metadata(node).get("importance"), 0.55),
            "confidence": _weight(
                _node_metadata(node).get("confidence"),
                _weight(_node_metadata(node).get("importance"), 0.55),
            ),
            "source_event_ids": _source_event_ids(node),
        }
        for node in selected
    ]
    node_ids = {node.node_id for node in selected}
    relation_kinds = {
        "derived_from": "derived_from",
        "about": "derived_from",
        "supports": "supports",
        "implies": "supports",
        "conflicts": "conflicts",
        "revises": "revises",
    }
    links = [
        {
            "source": assertion.subject_id,
            "target": assertion.object_node_id,
            "label": assertion.predicate,
            "relation_kind": relation_kinds.get(assertion.predicate, "supports"),
            "weight": _weight(assertion.importance, 0.5),
        }
        for assertion in assertions
        if assertion.subject_id in node_ids and assertion.object_node_id in node_ids
    ]
    return rendered_nodes, sorted(links, key=_link_key)[:MAX_ITEMS]


def _weight(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    numeric = float(value)
    if not math.isfinite(numeric):
        return default
    return min(1.0, max(0.0, numeric))


def _rank_nodes(nodes: Sequence[RecallNode]) -> List[RecallNode]:
    return sorted(
        nodes,
        key=lambda node: (
            -_weight(_node_metadata(node).get("importance"), 0.55),
            node.label,
            node.node_id,
        ),
    )


def _important_events(episodes: Sequence[ClosedEpisode]) -> List[Dict[str, Any]]:
    ranked = sorted(
        episodes,
        key=lambda episode: (
            str(
                _episode_metadata(episode).get("timestamp", episode.occurred_from or "")
            ),
            episode.episode_id,
        ),
        reverse=True,
    )[:MAX_ITEMS]
    events: List[Dict[str, Any]] = []
    for episode in ranked:
        metadata = _episode_metadata(episode)
        people = metadata.get("people", [])
        if not isinstance(people, (list, tuple)):
            people = []
        importance = metadata.get("importance")
        if importance is None:
            importance = metadata.get(
                "emotion_intensity", metadata.get("intensity", 0.0)
            )
        emotion = metadata.get("emotion")
        events.append(
            {
                "id": episode.episode_id,
                "content": episode.content_text,
                "timestamp": str(
                    metadata.get("timestamp", episode.occurred_from or "")
                ),
                "emotion": emotion if isinstance(emotion, str) else "",
                "importance": _weight(importance),
                "people": [person for person in people if isinstance(person, str)],
                "changed": (
                    metadata["changed"]
                    if isinstance(metadata.get("changed"), str)
                    else ""
                ),
            }
        )
    return events


def _entity_kind(node: RecallNode) -> str:
    declared = str(_node_metadata(node).get("entity_type", "")).lower()
    if declared in {"elfie", "pet", "animal"}:
        return "elfie"
    return "human"


def _knowledge_kind(node: RecallNode) -> str:
    if node.node_type == "pattern":
        return "pattern"
    if _node_metadata(node).get("kind") == "belief":
        return "belief"
    return "knowledge"


def _source_event_ids(node: RecallNode) -> List[str]:
    metadata = _node_metadata(node)
    values = metadata.get("source_event_ids", metadata.get("source_ids", []))
    if not isinstance(values, (list, tuple)):
        return []
    return [value for value in values if isinstance(value, str)][:MAX_ITEMS]


def _link_key(link: Dict[str, Any]) -> Tuple[str, str, str]:
    return str(link["source"]), str(link["target"]), str(link["label"])


def _world_model(summary: str, candidates: Sequence[RecallNode]) -> WorldModelPayload:
    ranked = _rank_nodes(candidates)[:MAX_ITEMS]
    rings: List[Dict[str, Any]] = []
    for key, label in RINGS:
        nodes = [
            {
                "id": node.node_id,
                "label": node.label[:48],
                "kind": _knowledge_kind(node)
                if node.node_type != "entity"
                else _entity_kind(node),
                "weight": _weight(_node_metadata(node).get("importance"), 0.55),
            }
            for node in ranked
            if _node_metadata(node).get("world_ring") == key
        ][:MAX_ITEMS]
        rings.append({"kind": key, "label": label, "nodes": nodes})
    return {"summary": summary, "rings": rings}
