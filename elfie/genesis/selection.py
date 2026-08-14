"""Candidate ranking and deterministic seed helpers."""

from __future__ import annotations

import hashlib
from typing import Mapping, Sequence

from .appearance import appearance_fit
from .contracts import BigFiveProfile, GenesisAppearanceIntent, GenesisCandidate

ROLE_FIT_WEIGHTS: Mapping[str, tuple[float, float]] = {
    "primary_match": (0.55, 0.45),
    "appearance_anchor": (0.25, 0.75),
    "inner_anchor": (0.75, 0.25),
    "balanced_variant": (0.50, 0.50),
    "discovery_variant": (0.40, 0.35),
}
ROLE_FIT_FLOORS: Mapping[str, float] = {
    "primary_match": 0.52,
    "appearance_anchor": 0.52,
    "inner_anchor": 0.52,
    "balanced_variant": 0.48,
    "discovery_variant": 0.32,
}


def personality_fit(values: Sequence[float], target: Sequence[float]) -> float:
    total = sum(abs(left - right) for left, right in zip(values, target))
    return max(0.0, min(1.0, 1.0 - total / (4.0 * len(target))))


def role_fit(
    candidate: GenesisCandidate,
    role: str,
    appearance: GenesisAppearanceIntent,
    core: BigFiveProfile,
) -> float:
    personality = personality_fit(candidate.personality.candidate.latent, core.latent)
    visual = appearance_fit(candidate.appearance, appearance)
    personality_weight, visual_weight = ROLE_FIT_WEIGHTS[role]
    return personality_weight * personality + visual_weight * visual


def derive_seed(*parts: int) -> int:
    payload = ":".join(str(part) for part in parts).encode("ascii")
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "big")


__all__ = (
    "ROLE_FIT_FLOORS",
    "ROLE_FIT_WEIGHTS",
    "derive_seed",
    "personality_fit",
    "role_fit",
)
