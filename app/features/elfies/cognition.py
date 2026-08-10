"""Bounded, read-only projections over authoritative cognition records."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Final

from .models import (
    CognitionStatus,
    ElfieCognitionResult,
    ExperienceResult,
    GraphEdgeResult,
    GraphNodeResult,
    ImportantExperiencesResult,
    KnowledgeBeliefsResult,
    RecentFocusResult,
    RelationshipWorldResult,
    TopicResult,
    WorldRingKey,
    WorldRingResult,
    WorldUnderstandingResult,
)
from .ports import (
    CognitionEdgeRecord,
    CognitionEntityRecord,
    CognitionEventRecord,
    CognitionSnapshotRecord,
)

_RINGS: Final[tuple[WorldRingKey, ...]] = (
    "self",
    "family",
    "nest",
    "society",
    "outside",
)
_TOPIC_CATEGORIES: Final[frozenset[str]] = frozenset(
    {"person", "place", "emotion", "activity"}
)
_STOP_WORDS: Final[frozenset[str]] = frozenset(
    {"什么", "这个", "那个", "然后", "可以", "精灵", "事情", "今天", "之后"}
)
_KNOWLEDGE_RELATIONS: Final[frozenset[str]] = frozenset(
    {"derived_from", "supports", "conflicts", "revises"}
)
_RELATIONSHIP_NODE_LIMIT: Final = 49
_RELATIONSHIP_EDGE_LIMIT: Final = 120
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


@dataclass
class _TopicAggregate:
    count: int = 0
    importance: float = 0.0
    recency: float = 0.0
    categories: Counter[str] = field(default_factory=Counter)


def project_cognition(
    snapshot: CognitionSnapshotRecord,
    *,
    elfie_name: str,
) -> ElfieCognitionResult:
    if snapshot.status != "ready":
        return _empty_cognition(snapshot.status, elfie_name)
    return ElfieCognitionResult(
        status="ready",
        recent_focus=RecentFocusResult(
            topics=_recent_topics(snapshot.events, elfie_name)
        ),
        important_experiences=ImportantExperiencesResult(
            entries=_important_experiences(snapshot.events)
        ),
        relationship_world=_relationship_world(
            snapshot.entities,
            snapshot.edges,
            elfie_name,
        ),
        world_understanding=_world_understanding(
            snapshot.entities,
            snapshot.core_world,
        ),
        knowledge_beliefs=_knowledge_beliefs(snapshot.entities, snapshot.edges),
    )


def _empty_cognition(status: str, elfie_name: str) -> ElfieCognitionResult:
    cognition_status: CognitionStatus = (
        "unavailable" if status == "unavailable" else "empty"
    )
    return ElfieCognitionResult(
        status=cognition_status,
        recent_focus=RecentFocusResult(topics=()),
        important_experiences=ImportantExperiencesResult(entries=()),
        relationship_world=RelationshipWorldResult(
            nodes=(GraphNodeResult("self", elfie_name, "self", 1.0),),
            edges=(),
        ),
        world_understanding=WorldUnderstandingResult(
            summary="",
            rings=tuple(WorldRingResult(key=key, nodes=()) for key in _RINGS),
        ),
        knowledge_beliefs=KnowledgeBeliefsResult(nodes=(), edges=()),
    )


def _recent_topics(
    events: tuple[CognitionEventRecord, ...],
    elfie_name: str,
) -> tuple[TopicResult, ...]:
    ordered = sorted(
        events,
        key=lambda event: (_date(event.occurred_at), event.id),
        reverse=True,
    )
    dated = [
        event
        for event in ordered
        if event.occurred_at and _date(event.occurred_at) != _EPOCH
    ]
    if dated:
        cutoff = _date(dated[0].occurred_at) - timedelta(days=30)
        selected = [event for event in dated if _date(event.occurred_at) >= cutoff]
    else:
        selected = ordered[:50]

    aggregates: dict[str, _TopicAggregate] = {}
    for event in selected:
        seen: set[str] = set()
        for label, category in _event_topics(event):
            normalized = label.casefold()
            if normalized in seen or not _valid_topic(label, elfie_name):
                continue
            seen.add(normalized)
            aggregate = aggregates.setdefault(label, _TopicAggregate())
            aggregate.count += 1
            aggregate.importance = max(aggregate.importance, event.importance)
            aggregate.recency = max(aggregate.recency, _recency(event, dated))
            aggregate.categories[category] += 1

    max_count = max((item.count for item in aggregates.values()), default=1)
    scored: list[tuple[str, float, str]] = []
    for label, item in aggregates.items():
        score = (
            0.5 * item.count / max_count + 0.3 * item.importance + 0.2 * item.recency
        )
        category = sorted(
            item.categories.items(),
            key=lambda pair: (-pair[1], pair[0]),
        )[0][0]
        scored.append((label, score, category))
    maximum = max((score for _, score, _ in scored), default=1.0)
    return tuple(
        TopicResult(
            id=f"topic:{label}",
            label=label,
            category=category,
            weight=round(score / maximum, 6),
        )
        for label, score, category in sorted(
            scored,
            key=lambda item: (-item[1], item[0]),
        )[:50]
    )


def _event_topics(event: CognitionEventRecord) -> tuple[tuple[str, str], ...]:
    if event.topics:
        return tuple(
            (
                topic.label,
                topic.category
                if topic.category in _TOPIC_CATEGORIES
                else _topic_category(topic.label),
            )
            for topic in event.topics
        )
    tokens = re.findall(
        r"[\u4e00-\u9fff]{2,12}|[A-Za-z][A-Za-z0-9_-]{2,}",
        event.description,
    )
    return tuple((token, _topic_category(token)) for token in tokens)


def _valid_topic(label: str, elfie_name: str) -> bool:
    if len(label) < 2 or len(label) > 12 or not label.strip():
        return False
    if label.casefold() == elfie_name.casefold() or label in _STOP_WORDS:
        return False
    return re.fullmatch(r"[A-Za-z_-]*\d+", label) is None and not label.isdigit()


def _topic_category(label: str) -> str:
    lowered = label.casefold()
    if any(word in lowered for word in ("主人", "朋友", "妈妈", "爸爸", "alice")):
        return "person"
    if any(word in lowered for word in ("公园", "房间", "学校", "家", "park", "home")):
        return "place"
    if any(word in lowered for word in ("开心", "难过", "害怕", "joy", "sad", "fear")):
        return "emotion"
    return "activity"


def _important_experiences(
    events: tuple[CognitionEventRecord, ...],
) -> tuple[ExperienceResult, ...]:
    candidates = [
        event for event in events if event.major_event or event.importance >= 0.75
    ]
    lifecycle = [event for event in candidates if _is_lifecycle(event)]
    regular = [event for event in candidates if event not in lifecycle]
    selected = _dedupe_events(
        sorted(
            lifecycle,
            key=lambda event: (_date(event.occurred_at), event.id),
            reverse=True,
        )
        + sorted(
            regular,
            key=lambda event: (-event.importance, _date(event.occurred_at), event.id),
            reverse=True,
        )
    )[:10]
    selected.sort(
        key=lambda event: (_date(event.occurred_at), event.id),
        reverse=True,
    )
    return tuple(
        ExperienceResult(
            id=event.id,
            occurred_at=event.occurred_at,
            title=event.title or event.description,
            changed=event.changed,
            importance=round(event.importance, 6),
            people=event.people,
        )
        for event in selected
    )


def _is_lifecycle(event: CognitionEventRecord) -> bool:
    text = " ".join(
        (
            event.event_type,
            event.lifecycle_event,
            event.title,
            event.description,
        )
    ).casefold()
    return any(
        token in text
        for token in ("birth", "born", "adoption", "adopted", "出生", "领养", "收养")
    )


def _dedupe_events(
    events: list[CognitionEventRecord],
) -> list[CognitionEventRecord]:
    seen: set[str] = set()
    result: list[CognitionEventRecord] = []
    for event in events:
        key = event.title.strip() or event.description.strip()
        if key and key in seen:
            continue
        seen.add(key)
        result.append(event)
    return result


def _relationship_world(
    entities: tuple[CognitionEntityRecord, ...],
    edges: tuple[CognitionEdgeRecord, ...],
    elfie_name: str,
) -> RelationshipWorldResult:
    candidates = [
        entity
        for entity in entities
        if _relationship_kind(entity) is not None and not entity.is_self
    ]
    candidates.sort(key=lambda entity: (-entity.weight, entity.name, entity.id))
    selected = candidates[:_RELATIONSHIP_NODE_LIMIT]
    visible = {entity.id for entity in selected}
    self_ids = {entity.id for entity in entities if entity.is_self}
    nodes = [GraphNodeResult("self", elfie_name, "self", 1.0)]
    nodes.extend(
        GraphNodeResult(
            id=entity.id,
            label=entity.name or entity.id,
            kind=_relationship_kind(entity) or "human",
            weight=round(entity.weight, 6),
        )
        for entity in selected
    )
    relation_rows: dict[tuple[str, str, str], GraphEdgeResult] = {}
    for entity in selected:
        if entity.relationship_label or entity.relation_key:
            relation_key = entity.relation_key or "relationship"
            relation_rows[("self", entity.id, relation_key)] = GraphEdgeResult(
                source="self",
                target=entity.id,
                relation_key=relation_key,
                display_label=entity.relationship_label,
                weight=round(entity.closeness, 6),
            )
    for edge in edges:
        source = "self" if edge.source in self_ids else edge.source
        target = "self" if edge.target in self_ids else edge.target
        if (source != "self" and source not in visible) or (
            target != "self" and target not in visible
        ):
            continue
        if source == "self" and target == "self":
            continue
        relation_key = edge.relation_type or "relationship"
        relation_rows[(source, target, relation_key)] = GraphEdgeResult(
            source=source,
            target=target,
            relation_key=relation_key,
            display_label=edge.summary,
            weight=round(edge.weight, 6),
        )
    ordered_keys = sorted(
        relation_rows,
        key=lambda key: (
            0 if key[0] == "self" or key[1] == "self" else 1,
            -relation_rows[key].weight,
            key,
        ),
    )
    return RelationshipWorldResult(
        nodes=tuple(nodes),
        edges=tuple(
            relation_rows[key] for key in ordered_keys[:_RELATIONSHIP_EDGE_LIMIT]
        ),
    )


def _world_understanding(
    entities: tuple[CognitionEntityRecord, ...],
    summary: str,
) -> WorldUnderstandingResult:
    candidates = [entity for entity in entities if entity.world_ring in _RINGS]
    ranked = sorted(
        candidates,
        key=lambda entity: (-entity.weight, entity.name, entity.id),
    )[:12]
    return WorldUnderstandingResult(
        summary=summary,
        rings=tuple(
            WorldRingResult(
                key=key,
                nodes=tuple(
                    GraphNodeResult(
                        id=entity.id,
                        label=entity.name or entity.id,
                        kind=entity.entity_type,
                        weight=round(entity.weight, 6),
                    )
                    for entity in ranked
                    if entity.world_ring == key
                ),
            )
            for key in _RINGS
        ),
    )


def _knowledge_beliefs(
    entities: tuple[CognitionEntityRecord, ...],
    edges: tuple[CognitionEdgeRecord, ...],
) -> KnowledgeBeliefsResult:
    candidates = {
        entity.id: entity for entity in entities if _knowledge_kind(entity) is not None
    }
    valid_edges = [
        edge
        for edge in edges
        if edge.relation_type in _KNOWLEDGE_RELATIONS
        and edge.source in candidates
        and edge.target in candidates
    ]
    connected = {edge.source for edge in valid_edges} | {
        edge.target for edge in valid_edges
    }
    selected = sorted(
        (candidates[node_id] for node_id in connected),
        key=lambda entity: (-entity.weight, entity.name, entity.id),
    )[:10]
    selected_ids = {entity.id for entity in selected}
    nodes = tuple(
        GraphNodeResult(
            id=entity.id,
            label=entity.name or entity.id,
            kind=_knowledge_kind(entity) or "knowledge",
            weight=round(entity.weight, 6),
        )
        for entity in sorted(
            selected,
            key=lambda entity: (_knowledge_order(entity), entity.name, entity.id),
        )
    )
    output_edges = tuple(
        GraphEdgeResult(
            source=edge.source,
            target=edge.target,
            relation_key=edge.relation_type,
            display_label=edge.summary,
            weight=round(edge.weight, 6),
        )
        for edge in sorted(
            valid_edges,
            key=lambda edge: (edge.source, edge.target, edge.relation_type),
        )
        if edge.source in selected_ids and edge.target in selected_ids
    )
    return KnowledgeBeliefsResult(nodes=nodes, edges=output_edges)


def _relationship_kind(entity: CognitionEntityRecord) -> str | None:
    if entity.entity_type in {"person", "human"}:
        return "human"
    if entity.entity_type in {"elfie", "pet", "animal"}:
        return "elfie"
    return None


def _knowledge_kind(entity: CognitionEntityRecord) -> str | None:
    if entity.concept_kind == "source":
        return "source"
    if entity.concept_kind in {"belief", "pattern"}:
        return "belief"
    if entity.concept_kind == "knowledge":
        return "knowledge"
    return None


def _knowledge_order(entity: CognitionEntityRecord) -> int:
    return {"source": 0, "knowledge": 1, "belief": 2}.get(
        _knowledge_kind(entity) or "knowledge",
        1,
    )


def _recency(
    event: CognitionEventRecord,
    dated: list[CognitionEventRecord],
) -> float:
    if not dated or not event.occurred_at:
        return 0.0
    age = (_date(dated[0].occurred_at) - _date(event.occurred_at)).days
    return max(0.0, min(1.0, 1.0 - age / 30.0))


def _date(value: str) -> datetime:
    if not value:
        return _EPOCH
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except (TypeError, ValueError):
        return _EPOCH


__all__ = ("project_cognition",)
