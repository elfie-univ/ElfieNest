"""从中文性格描述派生可重放的 Brain Selfhood seed。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from types import MappingProxyType
from typing import Dict, Final, Literal, Mapping, Union

BigFiveRanges = Dict[str, tuple[float, float]]
OverrideValue = Union[float, int, str, None]
PersonalitySource = Literal[
    "description",
    "fallback",
    "description+manual_override",
    "fallback+manual_override",
]

BIG_FIVE_TRAITS: Final = (
    "openness",
    "conscientiousness",
    "extraversion",
    "agreeableness",
    "neuroticism",
)

PERSONALITY_PRESETS: Final[Dict[str, BigFiveRanges]] = {
    "活泼好动": {
        "openness": (0.5, 0.8),
        "conscientiousness": (0.3, 0.6),
        "extraversion": (0.75, 0.95),
        "agreeableness": (0.5, 0.8),
        "neuroticism": (0.3, 0.6),
    },
    "安静温顺": {
        "openness": (0.4, 0.7),
        "conscientiousness": (0.6, 0.85),
        "extraversion": (0.2, 0.5),
        "agreeableness": (0.7, 0.95),
        "neuroticism": (0.2, 0.45),
    },
    "好奇探索": {
        "openness": (0.7, 0.95),
        "conscientiousness": (0.4, 0.7),
        "extraversion": (0.6, 0.85),
        "agreeableness": (0.5, 0.8),
        "neuroticism": (0.2, 0.5),
    },
    "胆小害羞": {
        "openness": (0.4, 0.7),
        "conscientiousness": (0.5, 0.8),
        "extraversion": (0.15, 0.4),
        "agreeableness": (0.5, 0.8),
        "neuroticism": (0.6, 0.9),
    },
    "傲娇独立": {
        "openness": (0.5, 0.8),
        "conscientiousness": (0.5, 0.8),
        "extraversion": (0.3, 0.6),
        "agreeableness": (0.3, 0.6),
        "neuroticism": (0.4, 0.7),
    },
    "完全随机": dict.fromkeys(BIG_FIVE_TRAITS, (0.0, 1.0)),
}

PERSONALITY_KEYWORDS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "活泼好动": ("活泼", "开朗", "好动", "热情"),
        "安静温顺": ("温柔", "温顺", "乖巧", "安静"),
        "好奇探索": ("好奇", "探索", "聪明"),
        "胆小害羞": ("胆小", "害羞", "敏感", "怕生"),
        "傲娇独立": ("傲娇", "独立", "高冷"),
    }
)


class PersonalityDerivationError(ValueError):
    """性格派生输入不符合 Brain Selfhood 契约。"""


@dataclass(frozen=True)
class PersonalityDerivation:
    """一次可重放且可解释的性格派生结果。"""

    # Keep the value object allocation-free beyond its declared fields on
    # CPython 3.9, matching the public Selfhood contract.
    __slots__ = (
        "preset",
        "big_five",
        "matched_keywords",
        "provenance",
        "overridden_traits",
        "seed",
    )

    preset: str
    big_five: Mapping[str, float]
    matched_keywords: tuple[str, ...]
    provenance: PersonalitySource
    overridden_traits: tuple[str, ...]
    seed: int


def derive_personality(
    elfie_id: str,
    personality_description: str,
    overrides: Mapping[str, OverrideValue] | None = None,
    *,
    default_big_five: Mapping[str, object] | None = None,
) -> PersonalityDerivation:
    """按固定中文词表和 ``elfie_id`` 派生稳定 Selfhood。"""
    winner, matched_keywords = _select_preset(personality_description)
    seed = int.from_bytes(hashlib.sha256(elfie_id.encode()).digest()[:8], "big")
    if winner is None:
        preset = "默认基线"
        source: PersonalitySource = "fallback"
        generated = _load_default_big_five(default_big_five)
    else:
        preset = winner
        source = "description"
        generated = _derive_preset_scores(seed, winner)
    final_values = dict(generated)
    overridden_traits = _apply_overrides(final_values, overrides)
    if overridden_traits:
        source = (
            "fallback+manual_override"
            if source == "fallback"
            else "description+manual_override"
        )
    return PersonalityDerivation(
        preset=preset,
        big_five=MappingProxyType(final_values),
        matched_keywords=matched_keywords,
        provenance=source,
        overridden_traits=overridden_traits,
        seed=seed,
    )


def _select_preset(description: str) -> tuple[str | None, tuple[str, ...]]:
    candidates: list[tuple[int, int, int, str, tuple[str, ...]]] = []
    for preset_order, (preset, keywords) in enumerate(PERSONALITY_KEYWORDS.items()):
        matched = tuple(keyword for keyword in keywords if keyword in description)
        if matched:
            first_position = min(description.index(keyword) for keyword in matched)
            candidates.append(
                (-len(matched), first_position, preset_order, preset, matched)
            )
    if not candidates:
        return None, ()
    _, _, _, winner, matched_keywords = min(candidates)
    return winner, tuple(
        sorted(matched_keywords, key=lambda keyword: description.index(keyword))
    )


def _derive_preset_scores(seed: int, preset: str) -> Mapping[str, float]:
    scores: dict[str, float] = {}
    for trait, (lower, upper) in PERSONALITY_PRESETS[preset].items():
        digest = hashlib.sha256(f"{seed}:{preset}:{trait}".encode()).digest()
        fraction = int.from_bytes(digest[:8], "big") / ((1 << 64) - 1)
        scores[trait] = round(lower + ((upper - lower) * fraction), 4)
    return scores


def _load_default_big_five(
    default_big_five: Mapping[str, object] | None,
) -> Mapping[str, float]:
    # Direct domain construction has only a neutral safety baseline.  The
    # product baseline is supplied by the bundled configuration Adapter.
    defaults = (
        dict.fromkeys(BIG_FIVE_TRAITS, 0.5)
        if default_big_five is None
        else default_big_five
    )
    result: dict[str, float] = {}
    try:
        for trait in BIG_FIVE_TRAITS:
            value = defaults[trait]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(trait)
            result[trait] = float(value)
    except (KeyError, TypeError, ValueError) as error:
        raise PersonalityDerivationError("默认人格配置无效") from error
    return result


def _apply_overrides(
    values: dict[str, float],
    overrides: Mapping[str, OverrideValue] | None,
) -> tuple[str, ...]:
    if overrides is None:
        return ()
    applied: list[str] = []
    for trait, raw_value in overrides.items():
        if trait not in BIG_FIVE_TRAITS:
            raise PersonalityDerivationError(f"未知 Big Five 覆盖字段: {trait}")
        if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
            raise PersonalityDerivationError(f"{trait} 必须是 0 到 1 的数值")
        value = float(raw_value)
        if not 0.0 <= value <= 1.0:
            raise PersonalityDerivationError(f"{trait} 必须在 [0, 1] 范围内")
        values[trait] = value
        applied.append(trait)
    return tuple(applied)


__all__ = (
    "BIG_FIVE_TRAITS",
    "BigFiveRanges",
    "OverrideValue",
    "PERSONALITY_KEYWORDS",
    "PERSONALITY_PRESETS",
    "PersonalityDerivation",
    "PersonalityDerivationError",
    "derive_personality",
)
