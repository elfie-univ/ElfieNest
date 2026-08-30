"""Big Five projections for emotion baselines and dynamics."""

from __future__ import annotations

import pytest

from elfie.brain.emotion.emotion_types import EMOTION_CONFIGS
from elfie.brain.emotion.personality import PersonalityModifier


def test_neuroticism_raises_negative_baselines_and_gain() -> None:
    low = PersonalityModifier({"neuroticism": 0.1}).parameters(
        "fear", EMOTION_CONFIGS["fear"]
    )
    high = PersonalityModifier({"neuroticism": 0.9}).parameters(
        "fear", EMOTION_CONFIGS["fear"]
    )

    assert high.baseline > low.baseline
    assert high.positive_gain > low.positive_gain
    assert high.half_life_seconds > low.half_life_seconds


def test_extraversion_raises_happiness_baseline_and_gain() -> None:
    low = PersonalityModifier({"extraversion": 0.1}).parameters(
        "happiness", EMOTION_CONFIGS["happiness"]
    )
    high = PersonalityModifier({"extraversion": 0.9}).parameters(
        "happiness", EMOTION_CONFIGS["happiness"]
    )

    assert high.baseline > low.baseline
    assert high.positive_gain > low.positive_gain


def test_agreeableness_reduces_anger_gain_and_increases_negative_consumption() -> None:
    low = PersonalityModifier({"agreeableness": 0.1}).parameters(
        "anger", EMOTION_CONFIGS["anger"]
    )
    high = PersonalityModifier({"agreeableness": 0.9}).parameters(
        "anger", EMOTION_CONFIGS["anger"]
    )

    assert high.positive_gain < low.positive_gain
    assert high.negative_gain > low.negative_gain


def test_surprise_uses_a_short_configured_half_life() -> None:
    params = PersonalityModifier().parameters("surprise", EMOTION_CONFIGS["surprise"])

    assert params.half_life_seconds == pytest.approx(
        EMOTION_CONFIGS["surprise"]["half_life_seconds"]
    )
    assert params.half_life_seconds < EMOTION_CONFIGS["fear"]["half_life_seconds"]


def test_effective_parameters_are_bounded() -> None:
    params = PersonalityModifier(
        {
            "neuroticism": 10.0,
            "extraversion": -10.0,
            "agreeableness": 10.0,
        }
    ).parameters("anger", EMOTION_CONFIGS["anger"])

    assert 0.0 <= params.baseline <= 0.35
    assert 0.05 <= params.positive_gain <= 4.0
    assert 0.05 <= params.negative_gain <= 4.0
    assert 1.0 <= params.half_life_seconds <= 86_400.0
