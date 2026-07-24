"""Elfie Lab 会话的只读展示投影。"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict
from typing import Any, Dict, List

from devtools.elfie_lab.schemas import ElfieSpec
from devtools.elfie_lab.storage import ElfieLabStorage
from elfie import Elfie
from elfie.profile import AppearanceResolver


def build_profile(
    elfie: Elfie,
    spec: ElfieSpec,
    storage: ElfieLabStorage,
) -> Dict[str, Any]:
    """Build the stable profile payload consumed by the Lab UI."""
    character_profile = elfie.profile
    personality = character_profile.personality
    resolved = AppearanceResolver().resolve(character_profile).to_payload()
    big_five = personality.get("big_five", {})
    return {
        **spec.to_dict(),
        "configured_name": character_profile.identity.display_name,
        "species_id": character_profile.identity.species_id,
        "species_label": (
            "小狗" if character_profile.identity.species_id == "dog" else "狐狸"
        ),
        "personality_summary": _personality_summary(big_five),
        "personality_tags": _personality_tags(big_five),
        "big_five": big_five,
        "personality_derivation": personality.get("derivation", {}),
        "speech_style": personality.get("speech_style", {}),
        "appearance": resolved,
        "appearance_genome": asdict(character_profile.appearance),
        "portrait_url": (
            f"/api/elfies/{spec.elfie_id}/portrait"
            if storage.portrait_path(spec.elfie_id).is_file()
            else ""
        ),
        "memory_cognition": _memory_cognition_projection(elfie, spec),
        "memory_count": len(elfie.memory.get_all_episodes()),
        "model": {
            "interaction_protocol": "food",
            "default_food": "mock",
            "mock_model": "elfie-mock",
            "catalog_scope": "runtime",
        },
    }


def build_snapshot(elfie: Elfie, spec: ElfieSpec) -> Dict[str, Any]:
    """Build the current in-memory state shown by the Lab."""
    expression = elfie.amygdala.get_expression() or {}
    return {
        "energy": round(elfie.hypothalamus.get_energy(), 2),
        "fatigue": round(elfie.hypothalamus.get_fatigue(), 2),
        "is_sleeping": bool(elfie.hypothalamus.is_sleeping),
        "emotions": {
            name: round(value, 2) for name, value in elfie.amygdala.emotions.items()
        },
        "dominant_emotion": elfie.amygdala.get_dominant_mood(),
        "expression": expression,
        "attention_network": "cortical_worker",
        "species_id": spec.species_id,
        "anatomy_type": elfie.anatomy_type,
        "action_intent": elfie.nervous_system.motion_actuator.last_action_intent,
        "joint_angles": {
            name: round(value, 3)
            for name, value in elfie.anatomy.get_joint_angles().items()
        },
        "elapsed_time": round(elfie.elapsed_time, 3),
        "memory_count": len(elfie.memory.get_all_episodes()),
    }


def _personality_summary(big_five: Dict[str, Any]) -> str:
    labels = {
        "openness": "开放",
        "conscientiousness": "尽责",
        "extraversion": "外向",
        "agreeableness": "宜人",
        "neuroticism": "敏感",
    }
    ranked = sorted(
        (
            (key, float(value))
            for key, value in big_five.items()
            if key in labels and isinstance(value, (int, float))
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    return "、".join(f"高{labels[key]}" for key, _ in ranked[:2]) or "平衡人格"


def _personality_tags(big_five: Dict[str, Any]) -> List[str]:
    labels = {
        "openness": ("务实", "好奇"),
        "conscientiousness": ("随性", "自律"),
        "extraversion": ("安静", "活跃"),
        "agreeableness": ("独立", "亲和"),
        "neuroticism": ("沉稳", "敏感"),
    }
    ranked = sorted(
        (
            (abs(float(value) - 0.5), labels[key][float(value) >= 0.5])
            for key, value in big_five.items()
            if key in labels and isinstance(value, (int, float))
        ),
        reverse=True,
    )
    return [label for _, label in ranked[:3]]


def _memory_cognition_projection(
    elfie: Elfie,
    spec: ElfieSpec,
) -> Dict[str, Any]:
    episodes = elfie.memory.get_all_episodes()
    core = elfie.memory.get_core_cognition()
    nodes_by_type = {
        node_type: elfie.memory.storage.get_nodes_by_type(node_type, limit=40)
        for node_type in ("entity", "knowledge", "pattern")
    }
    token_counts: Counter[str] = Counter()
    for episode in episodes:
        content = str(episode.get("content", ""))
        for token in re.findall(
            r"[\u4e00-\u9fff]{2,6}|[A-Za-z][A-Za-z0-9_-]{2,}", content
        ):
            if token not in {"什么", "这个", "那个", "然后", "可以", "精灵"}:
                token_counts[token] += 1
    topics = [
        {"label": label, "weight": count}
        for label, count in token_counts.most_common(12)
    ]
    events = sorted(
        (
            {
                "content": str(item.get("content", "")),
                "timestamp": str(item.get("metadata", {}).get("timestamp", "")),
                "emotion": str(item.get("metadata", {}).get("emotion", "")),
                "importance": float(item.get("metadata", {}).get("intensity", 0.0)),
            }
            for item in episodes
        ),
        key=lambda item: str(item["timestamp"]),
        reverse=True,
    )[:8]
    entities = nodes_by_type["entity"][:9]
    relation_nodes = [{"id": "self", "label": spec.name, "weight": 1.0}]
    relation_nodes.extend(
        {
            "id": node.id,
            "label": node.content[:24],
            "weight": float(node.metadata.get("importance", 0.55)),
        }
        for node in entities
    )
    relation_links = []
    for node in entities:
        edges = elfie.memory.storage.get_edges(node.id, "both")
        if not edges:
            relation_links.append(
                {
                    "source": "self",
                    "target": node.id,
                    "label": "认识",
                    "weight": 0.5,
                }
            )
        relation_links.extend(
            {
                "source": node.id,
                "target": edge.target,
                "label": edge.rel,
                "weight": edge.weight,
            }
            for edge in edges
            if any(candidate.id == edge.target for candidate in entities)
        )
    knowledge_nodes = [
        {"id": node.id, "label": node.content[:48], "type": node.type}
        for node in [
            *nodes_by_type["knowledge"][:8],
            *nodes_by_type["pattern"][:4],
        ]
    ]
    knowledge_links = []
    known_ids = {item["id"] for item in knowledge_nodes}
    for item in knowledge_nodes:
        for edge in elfie.memory.storage.get_edges(item["id"], "both"):
            if edge.target in known_ids:
                knowledge_links.append(
                    {
                        "source": item["id"],
                        "target": edge.target,
                        "label": edge.rel,
                    }
                )
    return {
        "topics": topics,
        "important_events": events,
        "relations": {"nodes": relation_nodes, "links": relation_links},
        "knowledge": {"nodes": knowledge_nodes, "links": knowledge_links},
        "world_understanding": str(core.get("world", "")),
    }
