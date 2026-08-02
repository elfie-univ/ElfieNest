"""Deterministic presentation projection for Elfie memory and cognition."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Protocol, Sequence, Tuple, TypedDict

from devtools.elfie_lab.topic_projection import TopicPayload, build_topics
from elfie.brain.memory.node_types import Edge, MemoryNode

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


class ProjectionStorage(Protocol):
    def get_nodes_by_type(
        self, node_type: str, limit: int = 100
    ) -> List[MemoryNode]: ...

    def get_edges(self, node_id: str, direction: str = "outgoing") -> List[Edge]: ...


class ProjectionMemory(Protocol):
    storage: ProjectionStorage

    def get_core_cognition(self) -> Dict[str, str]: ...


def build_memory_cognition(
    memory: ProjectionMemory,
    elfie_name: str,
) -> MemoryCognitionPayload:
    """Project graph memory into a bounded, deterministic UI payload."""
    episodes = _nodes(memory.storage, "episodic")
    entities = _nodes(memory.storage, "entity")
    knowledge = [
        *_nodes(memory.storage, "knowledge"),
        *_nodes(memory.storage, "pattern"),
    ]
    world_understanding = str(memory.get_core_cognition().get("world", ""))
    relation_nodes, relation_links = _relation_graph(
        memory.storage, entities, elfie_name
    )
    knowledge_nodes, knowledge_links = _knowledge_graph(memory.storage, knowledge)
    return {
        "topics": build_topics(episodes, MAX_ITEMS),
        "important_events": _important_events(episodes),
        "relations": {"nodes": relation_nodes, "links": relation_links},
        "knowledge": {"nodes": knowledge_nodes, "links": knowledge_links},
        "world_understanding": world_understanding,
        "world_model": _world_model(world_understanding, [*entities, *knowledge]),
    }


def _nodes(storage: ProjectionStorage, node_type: str) -> List[MemoryNode]:
    return storage.get_nodes_by_type(node_type, limit=1000)


def _weight(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    numeric = float(value)
    if not math.isfinite(numeric):
        return default
    return min(1.0, max(0.0, numeric))


def _rank_nodes(nodes: Sequence[MemoryNode]) -> List[MemoryNode]:
    return sorted(
        nodes,
        key=lambda node: (
            -_weight(node.metadata.get("importance"), 0.55),
            node.content,
            node.id,
        ),
    )


def _important_events(episodes: Sequence[MemoryNode]) -> List[Dict[str, Any]]:
    ranked = sorted(
        episodes,
        key=lambda node: (
            str(node.metadata.get("timestamp", node.created_at or "")),
            node.id,
        ),
        reverse=True,
    )[:MAX_ITEMS]
    events: List[Dict[str, Any]] = []
    for node in ranked:
        metadata = node.metadata
        people = metadata.get("people", [])
        if not isinstance(people, (list, tuple)):
            people = []
        importance = metadata.get("importance")
        if importance is None:
            importance = metadata.get(
                "emotion_intensity", metadata.get("intensity", 0.0)
            )
        events.append(
            {
                "id": node.id,
                "content": node.content,
                "timestamp": str(metadata.get("timestamp", node.created_at or "")),
                "emotion": str(metadata.get("emotion", "")),
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


def _entity_kind(node: MemoryNode) -> str:
    declared = str(node.metadata.get("entity_type", "")).lower()
    if declared in {"elfie", "pet", "animal"}:
        return "elfie"
    return "human"


def _relation_graph(
    storage: ProjectionStorage,
    entities: Sequence[MemoryNode],
    elfie_name: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    selected = _rank_nodes(entities)[: MAX_ITEMS - 1]
    nodes = [{"id": "self", "label": elfie_name, "kind": "self", "weight": 1.0}]
    nodes.extend(
        {
            "id": node.id,
            "label": node.content[:24],
            "kind": _entity_kind(node),
            "weight": _weight(node.metadata.get("importance"), 0.55),
        }
        for node in selected
    )
    known_ids = {node.id for node in selected}
    links: List[Dict[str, Any]] = []
    for node in selected:
        relationship = node.metadata.get("relationship")
        if isinstance(relationship, str) and relationship.strip():
            links.append(
                {
                    "source": "self",
                    "target": node.id,
                    "label": relationship.strip(),
                    "relation_kind": str(
                        node.metadata.get("relation_kind", "relationship")
                    ),
                    "weight": _weight(node.metadata.get("importance"), 0.55),
                }
            )
        for edge in storage.get_edges(node.id, "outgoing"):
            if edge.target in known_ids:
                links.append(
                    {
                        "source": node.id,
                        "target": edge.target,
                        "label": RELATION_LABELS.get(edge.rel, edge.rel),
                        "relation_kind": edge.rel,
                        "weight": _weight(edge.weight, 0.5),
                    }
                )
    return nodes, sorted(links, key=_link_key)[:MAX_RELATION_LINKS]


def _knowledge_kind(node: MemoryNode) -> str:
    if node.type == "pattern":
        return "pattern"
    if node.metadata.get("kind") == "belief":
        return "belief"
    return "knowledge"


def _source_event_ids(node: MemoryNode) -> List[str]:
    values = node.metadata.get("source_event_ids", node.metadata.get("source_ids", []))
    if not isinstance(values, (list, tuple)):
        return []
    return [value for value in values if isinstance(value, str)][:MAX_ITEMS]


def _knowledge_graph(
    storage: ProjectionStorage,
    candidates: Sequence[MemoryNode],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    selected = _rank_nodes(candidates)[:MAX_ITEMS]
    nodes = [
        {
            "id": node.id,
            "label": node.content[:48],
            "kind": _knowledge_kind(node),
            "weight": _weight(node.metadata.get("importance"), 0.55),
            "confidence": _weight(
                node.metadata.get("confidence"),
                _weight(node.metadata.get("importance"), 0.55),
            ),
            "source_event_ids": _source_event_ids(node),
        }
        for node in selected
    ]
    known_ids = {node.id for node in selected}
    links: List[Dict[str, Any]] = []
    relation_kinds = {
        "derived_from": "derived_from",
        "about": "derived_from",
        "supports": "supports",
        "implies": "supports",
        "conflicts": "conflicts",
        "revises": "revises",
    }
    for node in selected:
        for edge in storage.get_edges(node.id, "outgoing"):
            if edge.target in known_ids:
                links.append(
                    {
                        "source": node.id,
                        "target": edge.target,
                        "label": edge.rel,
                        "relation_kind": relation_kinds.get(edge.rel, "supports"),
                        "weight": _weight(edge.weight, 0.5),
                    }
                )
    return nodes, sorted(links, key=_link_key)[:MAX_ITEMS]


def _link_key(link: Dict[str, Any]) -> Tuple[str, str, str]:
    return str(link["source"]), str(link["target"]), str(link["label"])


def _world_model(summary: str, candidates: Sequence[MemoryNode]) -> WorldModelPayload:
    ranked = _rank_nodes(candidates)[:MAX_ITEMS]
    rings: List[Dict[str, Any]] = []
    for key, label in RINGS:
        nodes = [
            {
                "id": node.id,
                "label": node.content[:48],
                "kind": _knowledge_kind(node)
                if node.type != "entity"
                else _entity_kind(node),
                "weight": _weight(node.metadata.get("importance"), 0.55),
            }
            for node in ranked
            if node.metadata.get("world_ring") == key
        ][:MAX_ITEMS]
        rings.append({"kind": key, "label": label, "nodes": nodes})
    return {"summary": summary, "rings": rings}
