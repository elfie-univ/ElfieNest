"""Build the stable, deliberately small profile view for product clients."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from elfie.profile import AppearanceResolver, ElfieProfileRepository

_BIG_FIVE_KEYS = (
    "openness",
    "conscientiousness",
    "extraversion",
    "agreeableness",
    "neuroticism",
)


def build_public_profile(
    *,
    elfie_id: str,
    name: str,
    species_id: str,
    personality_style: str,
    config_dir: str,
    room_id: int | None,
    room_name: str | None,
    bed_id: int | None,
    bed_name: str | None,
    embodiment_state: str = "at_nest",
) -> Dict[str, Any]:
    """Return only fields approved for normal product clients.

    Config-file paths and raw profile data are inputs to the projection only and
    must never become output fields.
    """
    profile = ElfieProfileRepository(Path(config_dir)).load()
    personality = profile.personality
    big_five = _public_big_five(personality.get("big_five"))
    return {
        "elfie_id": elfie_id,
        "name": name,
        "species_id": species_id,
        "portrait_url": "",
        "appearance": AppearanceResolver().resolve(profile).to_payload(),
        "big_five": big_five,
        "personality_tags": _personality_tags(personality_style, big_five),
        "nest": {
            "room_id": room_id,
            "room_name": room_name,
            "bed_id": bed_id,
            "bed_name": bed_name,
            "posture": "resting" if bed_id is not None else "unknown",
        },
        "embodiment": {"state": embodiment_state},
    }


def _public_big_five(raw: object) -> Dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    values: Dict[str, float] = {}
    for key in _BIG_FIVE_KEYS:
        value = raw.get(key)
        if isinstance(value, (int, float)):
            values[key] = float(value)
    return values


def _personality_tags(style: str, big_five: Dict[str, float]) -> list[str]:
    tags = [style] if style else []
    ranked = sorted(big_five.items(), key=lambda item: item[1], reverse=True)
    tags.extend(key for key, _ in ranked[:2])
    return tags
