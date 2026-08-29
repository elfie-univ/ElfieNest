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

    def get_self_narrative(self) -> Dict[str, str]: ...

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
    typed_snapshot = getattr(memory, "memory_inspection_snapshot", None)
    if callable(typed_snapshot):
        return _build_typed_memory_cognition(
            memory,
            elfie_name,
            typed_snapshot(
                episode_limit=1000,
                node_limit=1000,
                assertion_limit=800,
            ),
        )
    episodes = _nodes(memory.storage, "episodic")
    entities = _nodes(memory.storage, "entity")
    knowledge = [
        *_nodes(memory.storage, "knowledge"),
        *_nodes(memory.storage, "pattern"),
    ]
    world_understanding = str(memory.get_self_narrative().get("world", ""))
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


def _build_typed_memory_cognition(
    memory: ProjectionMemory,
    elfie_name: str,
    snapshot: MemoryInspectionSnapshot,
) -> MemoryCognitionPayload:
    """Build the Lab payload from the typed Memory inspection boundary."""
    episodes = tuple(_episode_node(episode) for episode in snapshot.episodes)
    nodes = tuple(_recall_node(node) for node in snapshot.nodes)
    world_understanding = str(memory.get_self_narrative().get("world", ""))
    if not world_understanding:
        world_understanding = next(
            (
                node.content
                for node in nodes
                if node.metadata.get("core_key") == "world"
            ),
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


def _episode_node(episode: ClosedEpisode) -> MemoryNode:
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
    return MemoryNode(
        id=episode.episode_id,
        type="episodic",
        content=episode.content_text,
        metadata=metadata,
        created_at=episode.occurred_from,
    )


def _recall_node(node: RecallNode) -> MemoryNode:
    metadata = dict(node.properties)
    metadata.setdefault("importance", node.importance)
    metadata.setdefault("confidence", node.confidence)
    return MemoryNode(
        id=node.node_id,
        type=node.node_type,
        content=node.label,
        metadata=metadata,
    )


def _typed_relation_graph(
    nodes: Sequence[MemoryNode],
    assertions: Sequence[RecallAssertion],
    elfie_name: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    selected = _rank_nodes(
        [
            node
            for node in nodes
            if node.type in {"entity", "person", "elfie", "pet", "animal", "group"}
        ]
    )[: MAX_ITEMS - 1]
    node_ids = {node.id for node in selected}
    rendered_nodes = [
        {"id": "self", "label": elfie_name, "kind": "self", "weight": 1.0}
    ]
    rendered_nodes.extend(
        {
            "id": node.id,
            "label": node.content[:24],
            "kind": _entity_kind(node),
            "weight": _weight(node.metadata.get("importance"), 0.55),
        }
        for node in selected
    )
    links: list[dict[str, Any]] = []
    for node in selected:
        relationship = node.metadata.get("relationship") or node.metadata.get(
            "relationship_label"
        )
        relation_kind = node.metadata.get("relation_kind") or node.metadata.get(
            "relationship_key"
        )
        if isinstance(relationship, str) and relationship.strip():
            links.append(
                {
                    "source": "self",
                    "target": node.id,
                    "label": relationship.strip(),
                    "relation_kind": str(relation_kind or "relationship"),
                    "weight": _weight(node.metadata.get("importance"), 0.55),
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
    nodes: Sequence[MemoryNode],
    assertions: Sequence[RecallAssertion],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    selected = _rank_nodes(
        [
            node
            for node in nodes
            if node.type
            in {"knowledge", "pattern", "claim", "concept", "theory", "law"}
        ]
    )[:MAX_ITEMS]
    rendered_nodes = [
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
    node_ids = {node.id for node in selected}
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
        emotion = metadata.get("emotion")
        events.append(
            {
                "id": node.id,
                "content": node.content,
                "timestamp": str(metadata.get("timestamp", node.created_at or "")),
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
