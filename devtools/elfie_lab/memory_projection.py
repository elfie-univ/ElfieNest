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
    memory_knowledge_kind,
    memory_node_domain,
    resolve_memory_node_type,
)
from elfie.brain.memory.predicates import (
    NON_SEMANTIC_LEGACY_PREDICATES,
    relation_spec,
    resolve_predicate,
)

MAX_ITEMS = 20
MAX_RELATION_LINKS = 32
RELATION_LABELS: Dict[str, str] = {
    "owner_of": "主人",
    "owned_by": "归属于",
    "member_of": "成员",
    "kin_of": "家人（具体关系未知）",
    "friend_of": "朋友",
    "classmate_of": "同学",
    "colleague_of": "同事",
    "neighbor_of": "邻居",
    "acquaintance_of": "认识",
    "parent_of": "父母",
    "child_of": "子女",
    "sibling_of": "兄弟姐妹",
    "student_of": "学生",
    "teacher_of": "老师",
    "guided_by": "由其引导",
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
        **_build_typed_memory_cognition(memory, snapshot),
    }


def _build_typed_memory_cognition(
    memory: ProjectionMemory,
    snapshot: MemoryInspectionSnapshot,
) -> MemoryCognitionPayload:
    """Build the Lab payload from the typed Memory inspection boundary."""
    episodes = snapshot.episodes
    nodes = snapshot.nodes
    world_understanding = next(
        (node.label for node in nodes if node.properties.get("core_key") == "world"),
        "",
    )
    relation_nodes, relation_links = _typed_relation_graph(nodes, snapshot.assertions)
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
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    entity_nodes = [
        node for node in nodes if memory_node_domain(node.node_type) == "entity"
    ]
    entity_ids = {node.node_id for node in entity_nodes}
    relation_salience: dict[str, float] = {}
    explicit_relation_endpoints: set[str] = set()
    for assertion in assertions:
        if assertion.predicate in NON_SEMANTIC_LEGACY_PREDICATES:
            continue
        source = assertion.subject_id
        target = assertion.object_node_id
        if source not in entity_ids or target not in entity_ids:
            continue
        salience = _weight(assertion.importance, 0.5)
        relation_salience[source] = max(relation_salience.get(source, 0.0), salience)
        relation_salience[target] = max(relation_salience.get(target, 0.0), salience)
        context = assertion.qualifiers.get("context")
        if isinstance(context, str) and "explicit_pairwise_relation" in context:
            explicit_relation_endpoints.update((source, target))
    self_node = next(
        (node for node in entity_nodes if node.properties.get("is_self") is True),
        None,
    )
    # Keep relationship endpoints visible before filling the bounded view with
    # otherwise isolated high-importance places or objects. Otherwise a low-
    # salience neighbor could disappear merely because Genesis supplied many
    # unrelated world anchors, making the relationship graph look incomplete.
    selected = sorted(
        entity_nodes,
        key=lambda node: (
            -int(node.node_id in explicit_relation_endpoints),
            -int(node.node_id in relation_salience),
            -relation_salience.get(node.node_id, 0.0),
            -_weight(_node_metadata(node).get("importance"), 0.55),
            node.label,
            node.node_id,
        ),
    )[:MAX_ITEMS]
    if self_node is not None and self_node not in selected:
        selected = [self_node, *selected[: MAX_ITEMS - 1]]
    node_ids = {node.node_id for node in selected}
    rendered_nodes = [
        {
            "id": node.node_id,
            "label": node.label[:24],
            "kind": _entity_kind(node),
            "is_self": node.properties.get("is_self") is True,
            "weight": _weight(_node_metadata(node).get("importance"), 0.55),
        }
        for node in selected
    ]
    links_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for assertion in assertions:
        if assertion.predicate in NON_SEMANTIC_LEGACY_PREDICATES:
            continue
        source = assertion.subject_id
        target = assertion.object_node_id
        if source not in node_ids or target not in node_ids:
            continue
        relation_kind = _relation_kind(assertion)
        semantics = relation_spec(relation_kind)
        endpoints = tuple(sorted((source, target)))
        key = (
            relation_kind,
            endpoints[0] if semantics is not None and semantics.symmetric else source,
            endpoints[1] if semantics is not None and semantics.symmetric else target,
        )
        candidate = {
            "id": assertion.assertion_id,
            "source": source,
            "target": target,
            "label": RELATION_LABELS.get(relation_kind, relation_kind),
            "predicate": assertion.predicate,
            "relation_kind": relation_kind,
            "symmetric": bool(semantics.symmetric) if semantics is not None else False,
            "weight": _weight(assertion.importance, 0.5),
            "confidence": _weight(assertion.confidence, 0.5),
            "evidence_ids": list(assertion.evidence_ids),
        }
        prior = links_by_key.get(key)
        if prior is None or (
            candidate["weight"],
            candidate["confidence"],
            candidate["id"],
        ) > (prior["weight"], prior["confidence"], prior["id"]):
            links_by_key[key] = candidate
    return rendered_nodes, sorted(links_by_key.values(), key=_link_key)[
        :MAX_RELATION_LINKS
    ]


def _typed_knowledge_graph(
    nodes: Sequence[RecallNode],
    assertions: Sequence[RecallAssertion],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    selected = _rank_nodes(
        [node for node in nodes if memory_node_domain(node.node_type) == "knowledge"]
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
        "supports": "supports",
        "implies": "supports",
        "conflicts": "conflicts",
        "revises": "revises",
    }
    links = [
        {
            "id": assertion.assertion_id,
            "source": assertion.subject_id,
            "target": assertion.object_node_id,
            "label": assertion.predicate,
            "relation_kind": relation_kinds.get(assertion.predicate, "supports"),
            "weight": _weight(assertion.importance, 0.5),
            "evidence_ids": list(assertion.evidence_ids),
        }
        for assertion in assertions
        if assertion.predicate not in NON_SEMANTIC_LEGACY_PREDICATES
        and assertion.subject_id in node_ids
        and assertion.object_node_id in node_ids
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
    metadata = _node_metadata(node)
    declared = str(metadata.get("entity_type", "")).lower()
    if declared in {"human", "person"}:
        return "person"
    if declared in {"elfie", "pet", "animal"}:
        return "elfie"
    if declared in {"group", "place", "object"}:
        return declared
    return resolve_memory_node_type(node.node_type).kind


def _knowledge_kind(node: RecallNode) -> str:
    metadata = _node_metadata(node)
    declared = metadata.get("knowledge_kind") or metadata.get("kind")
    if declared in {"fact", "concept", "pattern", "guideline", "belief"}:
        return str(declared)
    return str(memory_knowledge_kind(node.node_type, metadata))


def _source_event_ids(node: RecallNode) -> List[str]:
    metadata = _node_metadata(node)
    values = metadata.get("source_event_ids", metadata.get("source_ids", []))
    if not isinstance(values, (list, tuple)):
        return []
    return [value for value in values if isinstance(value, str)][:MAX_ITEMS]


def _relation_kind(assertion: RecallAssertion) -> str:
    """Use a sourced relationship role for display while retaining the predicate."""

    try:
        canonical = resolve_predicate(assertion.predicate)
    except ValueError:
        canonical = assertion.predicate
    if canonical != "relationship":
        return canonical
    context = assertion.qualifiers.get("context")
    if isinstance(context, str) and ":" in context:
        role = context.rsplit(":", 1)[-1].strip()
        if role:
            return {
                "family": "kin_of",
                "friend": "friend_of",
                "owner": "owned_by",
                "acquaintance": "acquaintance_of",
            }.get(role, role)
    return assertion.predicate


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
                "kind": (
                    _knowledge_kind(node)
                    if memory_node_domain(node.node_type) == "knowledge"
                    else _entity_kind(node)
                    if memory_node_domain(node.node_type) == "entity"
                    else node.node_type
                ),
                "weight": _weight(_node_metadata(node).get("importance"), 0.55),
            }
            for node in ranked
            if _node_metadata(node).get("world_ring") == key
        ][:MAX_ITEMS]
        rings.append({"kind": key, "label": label, "nodes": nodes})
    return {"summary": summary, "rings": rings}
