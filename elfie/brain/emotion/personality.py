"""Big Five projection into emotion channel parameters."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class EmotionParameters:
    """Effective parameters for one short-term emotion channel."""

    baseline: float
    positive_gain: float
    negative_gain: float
    half_life_seconds: float
    activation_threshold: float


class PersonalityModifier:
    """Derive bounded baseline, rise, fall, and half-life independently.

    The coefficients are intentionally small and deterministic. They are a
    first-version temperament prior, not a second emotion state source.
    """

    def __init__(
        self,
        personality: Mapping[str, float] | None = None,
        *,
        config: Mapping[str, Mapping[str, float]] | None = None,
    ) -> None:
        raw = personality or {}
        self.traits = {
            name: _clamp(float(raw.get(name, 0.5)), 0.0, 1.0)
            for name in (
                "openness",
                "conscientiousness",
                "extraversion",
                "agreeableness",
                "neuroticism",
            )
        }
        self._config = config or {}

    def parameters(
        self,
        emotion: str,
        base: Mapping[str, float],
    ) -> EmotionParameters:
        """Return effective parameters without mutating the input config."""

        centered = {key: value - 0.5 for key, value in self.traits.items()}
        baseline = float(base.get("baseline", 0.0))
        positive_gain = float(base.get("positive_gain", 1.0))
        negative_gain = float(base.get("negative_gain", 1.0))
        half_life = float(base.get("half_life_seconds", 300.0))

        # Modest baseline temperament: it remains visible in absolute stock.
        if emotion == "happiness":
            baseline += 0.08 * centered["extraversion"]
            positive_gain *= math.exp(0.45 * centered["extraversion"])
            half_life *= math.exp(0.20 * centered["extraversion"])
        elif emotion in {"sadness", "fear"}:
            baseline += 0.08 * centered["neuroticism"]
            positive_gain *= math.exp(0.45 * centered["neuroticism"])
            half_life *= math.exp(0.30 * centered["neuroticism"])
        elif emotion == "anger":
            baseline += 0.05 * centered["neuroticism"]
            baseline -= 0.04 * centered["agreeableness"]
            positive_gain *= math.exp(
                0.40 * centered["neuroticism"] - 0.35 * centered["agreeableness"]
            )
            negative_gain *= math.exp(0.30 * centered["agreeableness"])
            half_life *= math.exp(0.25 * centered["neuroticism"])
        elif emotion == "surprise":
            positive_gain *= math.exp(0.25 * centered["openness"])
        elif emotion == "disgust":
            baseline += 0.03 * centered["neuroticism"]
            half_life *= math.exp(0.15 * centered["neuroticism"])

        overrides = self._config.get(emotion, {})
        baseline += float(overrides.get("baseline_offset", 0.0))
        positive_gain *= float(overrides.get("positive_gain_multiplier", 1.0))
        negative_gain *= float(overrides.get("negative_gain_multiplier", 1.0))
        half_life *= float(overrides.get("half_life_multiplier", 1.0))
        return EmotionParameters(
            baseline=_clamp(baseline, 0.0, 0.35),
            positive_gain=_clamp(positive_gain, 0.05, 4.0),
            negative_gain=_clamp(negative_gain, 0.05, 4.0),
            half_life_seconds=_clamp(half_life, 1.0, 86_400.0),
            activation_threshold=_clamp(
                float(base.get("activation_threshold", 0.2)), 0.01, 1.0
            ),
        )

    def get_accumulate_modifier(self, emotion: str) -> float:
        """Legacy diagnostic helper; use ``parameters`` for production logic."""

        return self.parameters(
            emotion,
            {
                "baseline": 0.0,
                "positive_gain": 1.0,
                "negative_gain": 1.0,
                "half_life_seconds": 300.0,
            },
        ).positive_gain

    def get_decay_modifier(self, emotion: str) -> float:
        """Return a diagnostic half-life multiplier, not an inverse growth rate."""

        params = self.parameters(
            emotion,
            {
                "baseline": 0.0,
                "positive_gain": 1.0,
                "negative_gain": 1.0,
                "half_life_seconds": 300.0,
            },
        )
        return params.half_life_seconds / 300.0


def calculate_personality_modifier(
    personality: Mapping[str, float], emotion: str
) -> float:
    """Compatibility-free convenience wrapper for diagnostics."""

    return PersonalityModifier(personality).get_accumulate_modifier(emotion)


__all__ = (
    "EmotionParameters",
    "PersonalityModifier",
    "calculate_personality_modifier",
)
