"""Deterministic topic extraction and semantic classification."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, DefaultDict, Dict, List, Sequence, Tuple, TypedDict

from elfie.brain.memory.node_types import MemoryNode

TOPIC_CATEGORIES = frozenset({"person", "place", "emotion", "activity"})
STOP_WORDS = frozenset({"什么", "这个", "那个", "然后", "可以", "精灵"})
CATEGORY_KEYWORDS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("person", ("主人", "朋友", "妈妈", "爸爸", "alice")),
    ("place", ("公园", "房间", "学校", "家里", "park", "home")),
    ("emotion", ("开心", "难过", "害怕", "joy", "sad", "fear")),
    ("activity", ("散步", "玩耍", "吃饭", "walk", "play")),
)


class TopicPayload(TypedDict):
    label: str
    weight: float
    category: str


def build_topics(episodes: Sequence[MemoryNode], limit: int) -> List[TopicPayload]:
    """Extract ranked topics with stable semantic categories."""
    counts: Counter[str] = Counter()
    categories: DefaultDict[str, Counter[str]] = defaultdict(Counter)
    for episode in episodes:
        for token in re.findall(
            r"[\u4e00-\u9fff]{2,6}|[A-Za-z][A-Za-z0-9_-]{2,}", episode.content
        ):
            if token not in STOP_WORDS:
                counts[token] += 1
                categories[token][_topic_category(token, episode.metadata)] += 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    maximum = max((count for _, count in ranked), default=1)
    return [
        {
            "label": label,
            "weight": count / maximum,
            "category": sorted(
                categories[label].items(), key=lambda item: (-item[1], item[0])
            )[0][0],
        }
        for label, count in ranked
    ]


def _topic_category(token: str, metadata: Dict[str, Any]) -> str:
    mapping = metadata.get("topic_categories")
    if isinstance(mapping, dict):
        mapped = mapping.get(token)
        if isinstance(mapped, str) and mapped in TOPIC_CATEGORIES:
            return mapped
    declared = metadata.get("topic_category")
    if isinstance(declared, str) and declared in TOPIC_CATEGORIES:
        return declared
    lowered = token.lower()
    for category, keywords in CATEGORY_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return category
    return "activity"
