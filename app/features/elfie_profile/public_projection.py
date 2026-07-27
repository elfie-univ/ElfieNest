"""Build the stable, deliberately small profile view for product clients."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Mapping, Optional

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
    config_dir: Optional[str],
    room_id: Optional[int],
    room_name: Optional[str],
    bed_id: Optional[int],
    bed_name: Optional[str],
    embodiment_state: str = "at_nest",
) -> Dict[str, object]:
    """Return only fields approved for normal product clients.

    Config-file paths and raw profile data are inputs to the projection only and
    must never become output fields.
    """
    result: Dict[str, object] = {
        "elfie_id": elfie_id,
        "name": name,
        "species_id": species_id,
        "gender": None,
        "birth_date": None,
        "summary": personality_style or None,
        "online_status": _online_status(embodiment_state),
        "portrait_url": "",
        "nest": {
            "room_id": room_id,
            "room_name": room_name,
            "bed_id": bed_id,
            "bed_name": bed_name,
            "posture": "resting" if bed_id is not None else "unknown",
        },
        "embodiment": {"state": embodiment_state},
    }
    if not config_dir:
        return _unavailable_profile(result, personality_style)

    repository = ElfieProfileRepository(Path(config_dir))
    if not repository.exists():
        return _unavailable_profile(result, personality_style)

    profile = repository.load()
    personality = profile.personality
    big_five = _public_big_five(personality.get("big_five"))
    summary = _profile_summary(personality) or personality_style or None
    result.update(
        {
            "summary": summary,
            "appearance": AppearanceResolver().resolve(profile).to_payload(),
            "big_five": big_five,
            "personality_tags": _personality_tags(personality_style, big_five),
        }
    )
    return result


def _unavailable_profile(
    result: Dict[str, object], personality_style: str
) -> Dict[str, object]:
    result.update(
        {
            "appearance": {},
            "big_five": {},
            "personality_tags": _personality_tags(personality_style, {}),
        }
    )
    return result


def _public_big_five(raw: object) -> Dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    values: Dict[str, float] = {}
    for key in _BIG_FIVE_KEYS:
        value = raw.get(key)
        if isinstance(value, (int, float)):
            values[key] = float(value)
    return values


def _personality_tags(style: str, big_five: Dict[str, float]) -> List[str]:
    tags = [style] if style else []
    ranked = sorted(big_five.items(), key=lambda item: item[1], reverse=True)
    tags.extend(key for key, _ in ranked[:2])
    return tags


def _profile_summary(personality: Mapping[str, object]) -> Optional[str]:
    metadata = personality.get("metadata")
    if not isinstance(metadata, dict):
        return None
    description = metadata.get("description")
    if not isinstance(description, str):
        return None
    normalized = description.strip()
    return normalized or None


def _online_status(embodiment_state: str) -> str:
    if embodiment_state == "hosted":
        return "online"
    if embodiment_state == "offline":
        return "offline"
    return "unknown"
