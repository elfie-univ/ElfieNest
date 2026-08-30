"""Focused tests for the six-channel signed affect model."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from elfie.brain.emotion.appraiser import EmotionAppraiser
from elfie.brain.emotion.contracts import (
    AffectDirection,
    AffectiveAppraisal,
    AppraisalRelevance,
    ChannelEffect,
    TrustedAppraisalScope,
)
from elfie.brain.emotion.emotion_system import EmotionSystem
from elfie.brain.emotion.emotion_types import EMOTION_NAMES, EmotionType
from elfie.brain.emotion.stimulus import EmotionStimulusEvent, StimulusSource
from elfie.brain.workspace.contracts import PerceptionEvent, SocialPayload
from elfie.message_types import (
    ActorId,
    ActorRef,
    ElfieId,
    EventId,
    MessageMeta,
    TraceId,
)
from infrastructure.persistence.configuration.bundled_defaults import (
    load_emotion_dynamics_defaults,
)


def _stimulus(event_id: str, effect: ChannelEffect, *, turn_id: str | None = None):
    return EmotionStimulusEvent(
        event_id=EventId(event_id),
        appraisals=(_appraisal(event_id, (effect,)),),
        source=StimulusSource.INTERNAL,
        turn_id=turn_id,
    )


def _appraisal(
    scope_id: str,
    effects: tuple[ChannelEffect, ...],
) -> AffectiveAppraisal:
    return AffectiveAppraisal(
        scope=TrustedAppraisalScope(
            scope_id=scope_id,
            cause_event_id=EventId(scope_id),
            relevance=AppraisalRelevance.DIRECT,
        ),
        effects=effects,
    )


def test_system_stores_six_absolute_channels_with_personality_visible_baselines() -> (
    None
):
    system = EmotionSystem(clock=lambda: 0.0)

    assert tuple(system.emotions) == EMOTION_NAMES
    assert all(0.0 <= value <= 1.0 for value in system.emotions.values())
    assert system.parameters("happiness").baseline > 0.0


def test_positive_drive_saturates_and_each_increment_gets_smaller() -> None:
    system = EmotionSystem(clock=lambda: 0.0)
    values = []
    for index in range(3):
        system.apply_stimulus(
            _stimulus(
                f"positive-{index}",
                ChannelEffect(
                    channel=EmotionType.FEAR,
                    direction=AffectDirection.INCREASE,
                    strength=80,
                ),
            )
        )
        values.append(system.get_emotion_value("fear"))

    increments = tuple(
        b - a
        for a, b in zip(
            (system.parameters("fear").baseline,) + tuple(values[:-1]), values
        )
    )
    assert values[0] < values[1] < values[2] < 1.0
    assert increments[0] > increments[1] > increments[2] > 0.0


def test_passive_return_has_fast_initial_drop_then_a_long_tail() -> None:
    system = EmotionSystem(clock=lambda: 0.0)
    system.apply_stimulus(
        _stimulus(
            "fear-once",
            ChannelEffect(
                channel=EmotionType.FEAR,
                direction=AffectDirection.INCREASE,
                strength=90,
            ),
        )
    )
    first = system.get_emotion_value("fear")
    system.advance_to(60.0)
    second = system.get_emotion_value("fear")
    system.advance_to(120.0)
    third = system.get_emotion_value("fear")

    assert first > second > third > system.parameters("fear").baseline
    assert first - second > second - third


def test_negative_drive_consumes_current_stock_and_equal_signed_evidence_cancels() -> (
    None
):
    system = EmotionSystem(clock=lambda: 0.0)
    system.apply_stimulus(
        _stimulus(
            "anger-once",
            ChannelEffect(
                channel=EmotionType.HAPPINESS,
                direction=AffectDirection.INCREASE,
                strength=90,
            ),
        )
    )
    before = system.get_emotion_value("happiness")
    system.apply_stimulus(
        EmotionStimulusEvent(
            event_id=EventId("anger-cancel"),
            appraisals=(
                _appraisal(
                    "anger-cancel-up",
                    (
                        ChannelEffect(
                            channel=EmotionType.HAPPINESS,
                            direction=AffectDirection.INCREASE,
                            strength=70,
                        ),
                    ),
                ),
                _appraisal(
                    "anger-cancel-down",
                    (
                        ChannelEffect(
                            channel=EmotionType.HAPPINESS,
                            direction=AffectDirection.DECREASE,
                            strength=70,
                        ),
                    ),
                ),
            ),
            source=StimulusSource.INTERNAL,
        )
    )
    assert system.get_emotion_value("happiness") == pytest.approx(before)

    system.apply_stimulus(
        _stimulus(
            "anger-down",
            ChannelEffect(
                channel=EmotionType.HAPPINESS,
                direction=AffectDirection.DECREASE,
                strength=60,
            ),
        )
    )
    assert 0.0 <= system.get_emotion_value("happiness") < before


def test_cause_guidance_is_exact_and_cleared_by_sleep_reset() -> None:
    system = EmotionSystem(clock=lambda: 0.0)
    system.update_cause_guidance(
        "threat-1",
        (
            ChannelEffect(
                channel=EmotionType.FEAR,
                direction=AffectDirection.DECREASE,
                strength=90,
            ),
        ),
    )

    assert (
        system.guidance_appraisal("threat-1", event_id=EventId("next-observation"))
        is not None
    )
    assert (
        system.guidance_appraisal("threat-2", event_id=EventId("different-observation"))
        is None
    )

    system.reset_to_baseline(1.0)

    assert (
        system.guidance_appraisal("threat-1", event_id=EventId("after-sleep")) is None
    )


def _social(content: str) -> PerceptionEvent:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return PerceptionEvent(
        meta=MessageMeta(
            event_id=EventId("social-1"),
            elfie_id=ElfieId("elfie-1"),
            source=ActorRef(actor_id=ActorId("owner-1"), source_kind="owner"),
            occurred_at=now,
            received_at=now,
            trace_id=TraceId("trace-1"),
        ),
        payload=SocialPayload(
            type="social",
            channel_id="chat",
            conversation_id="conversation",
            sender=ActorRef(actor_id=ActorId("owner-1"), source_kind="owner"),
            content=content,
        ),
        salience=0.5,
    )


def test_owner_observed_affect_is_not_elfie_affect_without_self_relevance() -> None:
    observed = EmotionAppraiser().appraise(_social("I am very sad today"))
    assert observed is None

    hostile = EmotionAppraiser().appraise(_social("I hate you, leave me alone"))
    assert hostile is not None
    hostile_effects = tuple(
        effect for appraisal in hostile.appraisals for effect in appraisal.effects
    )
    assert {effect.channel for effect in hostile_effects} >= {
        EmotionType.ANGER,
        EmotionType.SADNESS,
    }
    assert any(
        effect.channel is EmotionType.HAPPINESS
        and effect.direction is AffectDirection.DECREASE
        for effect in hostile_effects
    )


def test_slow_feedback_replays_from_anchor_and_replaces_fast_effect() -> None:
    system = EmotionSystem(clock=lambda: 0.0)
    anchor = system.capture_turn_state()
    fast = system.candidate_from(
        anchor,
        (
            EmotionStimulusEvent(
                event_id=EventId("fast-turn-event"),
                appraisals=(
                    _appraisal(
                        "fast-turn-event",
                        (
                            ChannelEffect(
                                channel=EmotionType.ANGER,
                                direction=AffectDirection.INCREASE,
                                strength=95,
                            ),
                        ),
                    ),
                ),
                source=StimulusSource.SOCIAL,
                turn_id="turn-1",
            ),
        ),
        timestamp=0.0,
        phase="fast",
        status="provisional",
    )
    assert system.commit_turn_state(fast)
    slow = system.candidate_from(
        anchor,
        (
            EmotionStimulusEvent(
                event_id=EventId("model-feedback"),
                appraisals=(
                    _appraisal(
                        "slow-turn-event",
                        (
                            ChannelEffect(
                                channel=EmotionType.HAPPINESS,
                                direction=AffectDirection.INCREASE,
                                strength=80,
                            ),
                        ),
                    ),
                ),
                source=StimulusSource.MODEL,
                turn_id="turn-1",
            ),
        ),
        timestamp=5.0,
        phase="slow",
        status="replaced",
    )
    assert system.commit_turn_state(slow)

    assert system.get_emotion_value("anger") == pytest.approx(
        system.parameters("anger").baseline
    )
    assert (
        system.get_emotion_value("happiness") > system.parameters("happiness").baseline
    )
    statuses = {(record.phase, record.status) for record in system.effect_records()}
    assert ("slow", "replaced") in statuses
    assert ("fast", "provisional") not in statuses


@pytest.mark.parametrize(
    ("channel", "target_seconds"),
    (
        (EmotionType.HAPPINESS, 26 * 60),
        (EmotionType.SADNESS, 20 * 60),
        (EmotionType.ANGER, 22 * 60),
        (EmotionType.FEAR, 16 * 60),
        (EmotionType.SURPRISE, 60),
        (EmotionType.DISGUST, 5 * 60),
    ),
)
def test_bundled_dynamics_match_everyday_episode_scale(
    channel: EmotionType,
    target_seconds: int,
) -> None:
    """Keep one strong isolated event in the empirically plausible range.

    The target is a product calibration anchor, not a claim that every human
    episode has one fixed duration.  Repeated observations and model feedback
    can still extend or shorten the trajectory.
    """

    system = EmotionSystem(
        clock=lambda: 0.0,
        dynamics_config=load_emotion_dynamics_defaults(),
    )
    system.apply_stimulus(
        EmotionStimulusEvent(
            event_id=EventId(f"duration-{channel.value}"),
            appraisals=(
                _appraisal(
                    f"duration-{channel.value}",
                    (
                        ChannelEffect(
                            channel=channel,
                            direction=AffectDirection.INCREASE,
                            strength=90,
                        ),
                    ),
                ),
            ),
            source=StimulusSource.PHYSICAL,
        )
    )
    threshold = system.parameters(channel).activation_threshold
    active_seconds = None
    for second in range(1, 3601):
        system.advance_to(float(second))
        if system.get_emotion_value(channel.value) < threshold:
            active_seconds = second
            break

    assert active_seconds is not None
    assert active_seconds == pytest.approx(
        target_seconds, abs=max(10, target_seconds * 0.02)
    )
