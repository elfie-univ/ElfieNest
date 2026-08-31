"""Executable v1 design goals for six-channel emotion dynamics."""

from __future__ import annotations

from elfie.brain.emotion.contracts import (
    AffectDirection,
    AffectiveAppraisal,
    AppraisalRelevance,
    ChannelEffect,
    TrustedAppraisalScope,
)
from elfie.brain.emotion.dynamics import apply_signed_drive, calibrate_strength
from elfie.brain.emotion.emotion_system import EmotionSystem
from elfie.brain.emotion.emotion_types import EMOTION_NAMES, EmotionType
from elfie.brain.emotion.personality import PersonalityModifier
from elfie.brain.emotion.stimulus import EmotionStimulusEvent, StimulusSource
from elfie.message_types import EventId
from infrastructure.persistence.configuration.bundled_defaults import (
    load_emotion_dynamics_defaults,
)


def _event(
    event_id: str, channel: EmotionType, direction: AffectDirection, strength: int
):
    return EmotionStimulusEvent(
        event_id=EventId(event_id),
        appraisals=(
            AffectiveAppraisal(
                scope=TrustedAppraisalScope(
                    scope_id=event_id,
                    cause_event_id=EventId(event_id),
                    relevance=AppraisalRelevance.DIRECT,
                ),
                effects=(
                    ChannelEffect(
                        channel=channel,
                        direction=direction,
                        strength=strength,
                    ),
                ),
            ),
        ),
        source=StimulusSource.INTERNAL,
    )


def test_v1_has_exactly_six_channels_and_complete_tunable_parameters() -> None:
    configs = load_emotion_dynamics_defaults()["channels"]
    assert set(configs) == set(EMOTION_NAMES)
    required = {
        "baseline",
        "positive_gain",
        "negative_gain",
        "half_life_seconds",
        "activation_threshold",
    }
    assert all(required.issubset(config) for config in configs.values())


def test_positive_growth_saturates_with_diminishing_increments() -> None:
    system = EmotionSystem(clock=lambda: 0.0)
    values = []
    for index in range(4):
        system.apply_stimulus(
            _event(f"rise-{index}", EmotionType.FEAR, AffectDirection.INCREASE, 90)
        )
        values.append(system.get_emotion_value("fear"))

    increments = tuple(
        after - before
        for before, after in zip(
            (system.parameters("fear").baseline,) + tuple(values[:-1]),
            values,
        )
    )
    assert all(left > right > 0 for left, right in zip(increments, increments[1:]))
    assert values[-1] < 1.0


def test_negative_drive_consumes_current_stock_directly() -> None:
    before = apply_signed_drive(
        current=0.8,
        baseline=0.02,
        positive_gain=1.0,
        negative_gain=1.0,
        positive_evidence=0.0,
        negative_evidence=0.7,
    )

    assert 0.0 < before < 0.8


def test_strength_calibration_is_bounded_and_nonlinear() -> None:
    values = tuple(calibrate_strength(strength) for strength in (0, 20, 50, 80, 100))

    assert values[0] == 0.0
    assert values[-1] == 1.0
    assert all(0.0 <= value <= 1.0 for value in values)
    assert values[2] != 0.5


def test_personality_changes_baseline_gain_and_decay_independently() -> None:
    configs = load_emotion_dynamics_defaults()["channels"]
    calm = PersonalityModifier({"neuroticism": 0.1}).parameters("fear", configs["fear"])
    reactive = PersonalityModifier({"neuroticism": 0.9}).parameters(
        "fear", configs["fear"]
    )

    assert reactive.baseline > calm.baseline
    assert reactive.positive_gain > calm.positive_gain
    assert reactive.half_life_seconds > calm.half_life_seconds


def test_all_effects_are_program_calculated_from_semantic_channel_signals() -> None:
    system = EmotionSystem(clock=lambda: 0.0)
    event = EmotionStimulusEvent(
        event_id=EventId("multi-channel"),
        appraisals=(
            AffectiveAppraisal(
                scope=TrustedAppraisalScope(
                    scope_id="multi-channel",
                    cause_event_id=EventId("multi-channel"),
                    relevance=AppraisalRelevance.DIRECT,
                ),
                effects=tuple(
                    ChannelEffect(
                        channel=channel,
                        direction=(
                            AffectDirection.INCREASE
                            if channel in {EmotionType.HAPPINESS, EmotionType.SURPRISE}
                            else AffectDirection.DECREASE
                        ),
                        strength=60,
                    )
                    for channel in EmotionType
                ),
            ),
        ),
        source=StimulusSource.MODEL,
    )
    system.apply_stimulus(event)

    assert (
        system.get_emotion_value("happiness") > system.parameters("happiness").baseline
    )
    assert system.get_emotion_value("surprise") > system.parameters("surprise").baseline
