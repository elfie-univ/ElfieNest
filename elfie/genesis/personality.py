"""Personality priors and deterministic Big Five derivation."""

from __future__ import annotations

import random
from typing import Iterable, Mapping, Sequence

from elfie.profile import get_species_definition

from .contracts import BIG_FIVE_TRAITS, BigFiveProfile, GenesisError

SPECIES_PRIORS: Mapping[str, tuple[float, ...]] = {
    "dog": (0.10, 0.05, 0.15, 0.25, -0.10),
    "fox": (0.25, -0.05, 0.10, 0.00, 0.05),
    "cat": (0.18, 0.02, -0.05, 0.08, 0.12),
}
STAGE_PRIORS: Mapping[str, tuple[float, ...]] = {
    "youth": (0.05, -0.10, 0.05, 0.00, 0.10),
    "young_adult": (0.05, 0.00, 0.05, 0.00, 0.00),
    "mature": (-0.05, 0.10, -0.05, 0.05, -0.05),
    "elder": (-0.10, 0.05, -0.10, 0.10, 0.00),
}
ANSWER_VECTORS: Mapping[str, tuple[float, ...]] = {
    "approach": (0.0, 0.0, 2.0, 1.0, -1.0),
    "quiet": (0.0, 1.0, -1.0, 1.0, 0.0),
    "independent": (0.0, 1.0, -2.0, -1.0, -1.0),
    "explore": (2.0, -1.0, 1.0, 0.0, 0.0),
    "research": (2.0, 1.0, 0.0, 1.0, -1.0),
    "observe": (-1.0, 1.0, -1.0, 0.0, 1.0),
    "adapt": (1.0, -1.0, 1.0, 0.0, -2.0),
    "plan": (-1.0, 2.0, 0.0, 1.0, -1.0),
    "comfort": (0.0, -1.0, -1.0, 1.0, 2.0),
    "direct": (0.0, 0.0, 1.0, -2.0, -1.0),
    "discuss": (0.0, 0.0, 1.0, 2.0, -1.0),
    "pause": (0.0, 1.0, -1.0, 0.0, 1.0),
    "lively": (1.0, -1.0, 2.0, 0.0, 0.0),
    "steady": (0.0, 2.0, -1.0, 1.0, -1.0),
    "space": (0.0, 1.0, -1.0, 1.0, 0.0),
    "any": (0.0, 0.0, 0.0, 0.0, 0.0),
}
LABELS: Mapping[str, tuple[tuple[str, float], ...]] = {
    "openness": (("好奇探索", 0.55), ("偏爱熟悉", -0.55)),
    "conscientiousness": (("有条有理", 0.55), ("随性灵活", -0.55)),
    "extraversion": (("外向热情", 0.55), ("安静内敛", -0.55)),
    "agreeableness": (("温柔体贴", 0.55), ("坚定直接", -0.55)),
    "neuroticism": (("感受细腻", 0.55), ("情绪平稳", -0.55)),
}


def core_profile(
    *, species_id: str, life_stage: str, answers: Sequence[str]
) -> BigFiveProfile:
    try:
        get_species_definition(species_id)
    except ValueError as error:
        raise GenesisError(f"不支持的物种: {species_id}") from error
    validate_answers(answers)
    values = [0.0] * len(BIG_FIVE_TRAITS)
    for answer in answers:
        vector = ANSWER_VECTORS[answer]
        values = [left + right for left, right in zip(values, vector)]
    count = max(1, len(answers))
    q = [value / count for value in values]
    species = SPECIES_PRIORS.get(species_id, (0.0,) * len(BIG_FIVE_TRAITS))
    stage = STAGE_PRIORS[life_stage]
    latent = tuple(
        clamp((5.0 * user + species_value + 0.5 * stage_value) / 6.5, -2.0, 2.0)
        for user, species_value, stage_value in zip(q, species, stage)
    )
    return profile(latent)


def role_delta(
    role: str, core: tuple[float, ...], rng: random.Random
) -> tuple[float, ...]:
    if role == "inner_anchor":
        ranked = sorted(
            range(len(core)), key=lambda index: abs(core[index]), reverse=True
        )
        top = set(ranked[:2])
        return tuple(
            (0.32 if value >= 0.0 else -0.32) if index in top else 0.0
            for index, value in enumerate(core)
        )
    if role == "discovery_variant":
        least = min(range(len(core)), key=lambda index: abs(core[index]))
        base = [-0.08, 0.06, -0.12, 0.10, 0.12]
        base[least] = 0.34 if rng.random() >= 0.5 else -0.34
        return tuple(base)
    role_base: tuple[float, ...] = {
        "primary_match": (0.00, 0.00, 0.00, 0.00, 0.00),
        "appearance_anchor": (0.06, -0.04, 0.05, 0.00, 0.00),
        "balanced_variant": (0.12, -0.10, 0.08, 0.06, -0.06),
    }.get(role, (0.0,) * len(BIG_FIVE_TRAITS))
    return tuple(value + rng.uniform(-0.035, 0.035) for value in role_base)


def profile(latent: Iterable[float]) -> BigFiveProfile:
    values = tuple(clamp(float(value), -2.0, 2.0) for value in latent)
    scores = tuple(
        int(round(clamp(50.0 + 22.5 * value, 5.0, 95.0))) for value in values
    )
    labels: list[str] = []
    for trait, value in zip(BIG_FIVE_TRAITS, values):
        high, low = LABELS[trait]
        if value >= high[1]:
            labels.append(high[0])
        elif value <= low[1]:
            labels.append(low[0])
    if not labels:
        dominant = max(range(len(values)), key=lambda index: abs(values[index]))
        high, low = LABELS[BIG_FIVE_TRAITS[dominant]]
        labels.append(high[0] if values[dominant] >= 0.0 else low[0])
    return BigFiveProfile(values, scores, tuple(labels[:3]))


def validate_answers(answers: Sequence[str]) -> None:
    if len(answers) != 5 or any(answer not in ANSWER_VECTORS for answer in answers):
        raise GenesisError("answers必须包含5个有效相处答案")


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


__all__ = (
    "ANSWER_VECTORS",
    "LABELS",
    "SPECIES_PRIORS",
    "STAGE_PRIORS",
    "clamp",
    "core_profile",
    "profile",
    "role_delta",
    "validate_answers",
)
