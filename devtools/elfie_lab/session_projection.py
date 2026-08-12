"""Elfie Lab 会话的只读展示投影。"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, cast

from devtools.elfie_lab.memory_projection import (
    MemoryCognitionPayload,
    ProjectionMemory,
    build_memory_cognition,
)
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
    selfhood = elfie.selfhood.snapshot()
    resolved = AppearanceResolver().resolve(character_profile).to_payload()
    big_five = selfhood.big_five.model_dump()
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
        "personality_derivation": selfhood.derivation.model_dump(),
        "speech_style": {
            "greetings": list(selfhood.speech_style.greetings),
            "verbal_ticks": selfhood.speech_style.verbal_tick,
        },
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
    cognitive_mode, long_reasoning_allowed, available_budget = (
        elfie.hypothalamus.cognitive_policy()
    )
    memory_state = elfie.memory.snapshot(elfie.cognitive_datetime)
    motivation = elfie.motivation_snapshot() if elfie.cognition_configured else None
    activities = [
        record.model_dump(mode="json")
        for record in (elfie.activities() if elfie.cognition_configured else ())
    ]
    return {
        "energy": round(elfie.hypothalamus.get_energy(), 2),
        "fatigue": round(elfie.hypothalamus.get_fatigue(), 2),
        "is_sleeping": bool(elfie.hypothalamus.is_sleeping),
        "cognitive_mode": cognitive_mode,
        "long_reasoning_allowed": long_reasoning_allowed,
        "available_cognitive_budget": round(available_budget, 2),
        "energy_revision": elfie.hypothalamus.revision,
        "emotions": {
            name: round(value, 2) for name, value in elfie.amygdala.emotions.items()
        },
        "dominant_emotion": elfie.amygdala.get_dominant_mood(),
        "emotion_revision": elfie.amygdala.revision,
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
        "memory_revision": memory_state.revision,
        "memory_episodic_count": memory_state.episodic_count,
        "memory_total_count": memory_state.total_count,
        "activities": activities,
        "activity_count": len(activities),
        "motivation": (
            motivation.model_dump(mode="json") if motivation is not None else None
        ),
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
) -> MemoryCognitionPayload:
    return build_memory_cognition(cast(ProjectionMemory, elfie.memory), spec.name)
