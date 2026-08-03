"""Recent-focus and important-experience projections."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Final

from app.features.elfie_profile.private_cognition_types import (
    ExperiencePayload,
    TopicPayload,
)
from app.infrastructure.persistence.elfie_cognition_reader import CognitionEvent

_TOPIC_CATEGORIES: Final[frozenset[str]] = frozenset(
    {"person", "place", "emotion", "activity"}
)
_STOP_WORDS: Final[frozenset[str]] = frozenset(
    {"什么", "这个", "那个", "然后", "可以", "精灵", "事情", "今天", "之后"}
)
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def recent_topics(
    events: tuple[CognitionEvent, ...], elfie_name: str
) -> list[TopicPayload]:
    """Build the stable, weighted word-cloud input from recent events."""
    ordered = sorted(events, key=lambda event: (_date(event.occurred_at), event.id), reverse=True)
    dated = [event for event in ordered if event.occurred_at and _date(event.occurred_at) != _EPOCH]
    if dated:
        cutoff = _date(dated[0].occurred_at) - timedelta(days=30)
        selected = [event for event in dated if _date(event.occurred_at) >= cutoff]
    else:
        selected = ordered[:50]
    aggregates: dict[str, dict[str, Any]] = {}
    for event in selected:
        seen: set[str] = set()
        for label, category in _event_topics(event):
            normalized = label.casefold()
            if normalized in seen or not _valid_topic(label, elfie_name):
                continue
            seen.add(normalized)
            current = aggregates.setdefault(
                label,
                {"count": 0, "importance": 0.0, "recency": 0.0, "categories": Counter()},
            )
            current["count"] += 1
            current["importance"] = max(current["importance"], _event_importance(event))
            current["recency"] = max(current["recency"], _recency(event, dated))
            current["categories"][category] += 1
    max_count = max((int(item["count"]) for item in aggregates.values()), default=1)
    scored: list[tuple[str, float, str]] = []
    for label, item in aggregates.items():
        score = 0.5 * int(item["count"]) / max_count + 0.3 * float(item["importance"]) + 0.2 * float(item["recency"])
        category = sorted(item["categories"].items(), key=lambda pair: (-pair[1], pair[0]))[0][0]
        scored.append((label, score, category))
    maximum = max((score for _, score, _ in scored), default=1.0)
    return [
        {"id": f"topic:{label}", "label": label, "category": category, "weight": round(score / maximum, 6)}
        for label, score, category in sorted(scored, key=lambda item: (-item[1], item[0], f"topic:{item[0]}"))[:50]
    ]


def important_experiences(events: tuple[CognitionEvent, ...]) -> list[ExperiencePayload]:
    """Keep at most ten lifetime-level events and display them newest first."""
    candidates = [event for event in events if _is_major(event)]
    lifecycle = [event for event in candidates if _is_lifecycle(event)]
    regular = [event for event in candidates if event not in lifecycle]
    selected = _dedupe_events(
        sorted(lifecycle, key=lambda event: (_date(event.occurred_at), event.id), reverse=True)
        + sorted(regular, key=lambda event: (-_event_importance(event), _date(event.occurred_at), event.id), reverse=True)
    )[:10]
    selected.sort(key=lambda event: (_date(event.occurred_at), event.id), reverse=True)
    return [_experience_payload(event) for event in selected]


def _event_topics(event: CognitionEvent) -> list[tuple[str, str]]:
    raw = event.metadata.get("topics", event.metadata.get("topic_metadata"))
    topics: list[tuple[str, str]] = []
    if isinstance(raw, dict):
        raw = list(raw.items())
    if isinstance(raw, (list, tuple)):
        for item in raw:
            if isinstance(item, str):
                topics.append((item.strip(), _topic_category(item, event.metadata)))
            elif isinstance(item, dict):
                label = item.get("label", item.get("topic"))
                if isinstance(label, str):
                    category = item.get("category", item.get("topic_category"))
                    topics.append((label.strip(), _topic_category(label, {"topic_category": category})))
    if topics:
        return topics
    tokens = re.findall(r"[\u4e00-\u9fff]{2,12}|[A-Za-z][A-Za-z0-9_-]{2,}", event.description)
    return [(token, _topic_category(token, event.metadata)) for token in tokens]


def _valid_topic(label: str, elfie_name: str) -> bool:
    if len(label) < 2 or len(label) > 12 or not label.strip():
        return False
    if label.casefold() == elfie_name.casefold() or label in _STOP_WORDS:
        return False
    return re.fullmatch(r"[A-Za-z_-]*\d+", label) is None and not label.isdigit()


def _topic_category(label: str, metadata: dict[str, Any]) -> str:
    declared = metadata.get("topic_category")
    if isinstance(declared, str) and declared in _TOPIC_CATEGORIES:
        return declared
    lowered = label.casefold()
    if any(word in lowered for word in ("主人", "朋友", "妈妈", "爸爸", "alice")):
        return "person"
    if any(word in lowered for word in ("公园", "房间", "学校", "家", "park", "home")):
        return "place"
    if any(word in lowered for word in ("开心", "难过", "害怕", "joy", "sad", "fear")):
        return "emotion"
    return "activity"


def _is_major(event: CognitionEvent) -> bool:
    return bool(event.metadata.get("major_event")) or _event_importance(event) >= 0.75


def _is_lifecycle(event: CognitionEvent) -> bool:
    text = " ".join(str(event.metadata.get(key, "")) for key in ("event_type", "lifecycle_event", "title")) + " " + event.description
    lowered = text.casefold()
    return any(token in lowered for token in ("birth", "born", "adoption", "adopted", "出生", "领养", "收养"))


def _dedupe_events(events: list[CognitionEvent]) -> list[CognitionEvent]:
    seen: set[str] = set()
    result: list[CognitionEvent] = []
    for event in events:
        key = str(event.metadata.get("title", "")).strip() or event.description.strip()
        if key and key in seen:
            continue
        seen.add(key)
        result.append(event)
    return result


def _experience_payload(event: CognitionEvent) -> ExperiencePayload:
    people = event.metadata.get("people", [])
    clean_people = [person.strip() for person in people if isinstance(person, str) and person.strip()] if isinstance(people, (list, tuple)) else []
    title = event.metadata.get("title")
    return {
        "id": event.id,
        "occurred_at": event.occurred_at,
        "title": title.strip() if isinstance(title, str) and title.strip() else event.description,
        "changed": event.metadata.get("changed", "") if isinstance(event.metadata.get("changed"), str) else "",
        "importance": round(_event_importance(event), 6),
        "people": clean_people,
    }


def _event_importance(event: CognitionEvent) -> float:
    return max(_weight(event.importance), _weight(event.metadata.get("importance")), _weight(event.metadata.get("emotion_intensity")), _weight(event.metadata.get("intensity")) / 100.0)


def _recency(event: CognitionEvent, dated: list[CognitionEvent]) -> float:
    if not dated or not event.occurred_at:
        return 0.0
    age = (_date(dated[0].occurred_at) - _date(event.occurred_at)).days
    return max(0.0, min(1.0, 1.0 - age / 30.0))


def _date(value: str) -> datetime:
    if not value:
        return _EPOCH
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return _EPOCH


def _weight(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    numeric = float(value)
    return max(0.0, min(1.0, numeric)) if numeric == numeric else 0.0


__all__ = ["important_experiences", "recent_topics"]
