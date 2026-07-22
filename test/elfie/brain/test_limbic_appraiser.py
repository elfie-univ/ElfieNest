"""Tests for the pure perception-to-limbic appraisal boundary."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from elfie.brain.emotion.emotion_types import EmotionType
from elfie.brain.emotion.stimulus import EmotionStimulusEvent, StimulusSource
from elfie.brain.limbic_appraiser import BrainClockPulse, LimbicAppraiser
from elfie.brain.perception_types import (
    InternalPayload,
    InternalSignal,
    PerceptionEvent,
    PhysicalModality,
    PhysicalPayload,
    SocialPayload,
)
from elfie.message_types import (
    ActorId,
    ActorRef,
    ElfieId,
    EventId,
    MessageMeta,
    TraceId,
)

NOW = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)


def _event(
    payload: PhysicalPayload | SocialPayload | InternalPayload,
) -> PerceptionEvent:
    return PerceptionEvent(
        meta=MessageMeta(
            event_id=EventId("impact-1"),
            elfie_id=ElfieId("elfie-1"),
            source=ActorRef(actor_id=ActorId("body-1"), source_kind="body"),
            occurred_at=NOW,
            received_at=NOW,
            trace_id=TraceId("trace-1"),
        ),
        payload=payload,
        salience=0.8,
    )


def test_touch_perception_maps_to_immutable_fear_stimulus() -> None:
    # Given: a salient tactile impact already normalized by NervousSystem.
    event = _event(
        PhysicalPayload(
            type="physical",
            body_id="body-1",
            modality=PhysicalModality.TOUCH,
            content="impact above reflex threshold",
        )
    )

    # When: the pure appraiser evaluates the perception.
    stimulus = LimbicAppraiser().appraise(event)

    # Then: source identity becomes a typed, immutable fear stimulus.
    assert stimulus is not None
    assert stimulus.event_id == EventId("impact-1")
    assert stimulus.emotion is EmotionType.FEAR
    assert stimulus.intensity == 0.8
    assert stimulus.source is StimulusSource.PHYSICAL


def test_clock_control_data_is_not_a_perception_or_limbic_stimulus() -> None:
    # Given: a coordinator mailbox pulse and the legacy CLOCK perception shape.
    pulse = BrainClockPulse(timestamp=5.0)
    legacy_clock_event = _event(
        InternalPayload(type="internal", signal=InternalSignal.CLOCK, detail="tick")
    )

    # When: only real perception is passed to appraisal.
    stimulus = LimbicAppraiser().appraise(legacy_clock_event)

    # Then: the control pulse is separate data and neither form creates stimulus.
    assert not isinstance(pulse, PerceptionEvent)
    assert stimulus is None
    assert not hasattr(pulse, "turn")


def test_social_appraisal_preserves_domain_source_semantics() -> None:
    # Given: a platform-neutral social message perception.
    sender = ActorRef(actor_id=ActorId("owner-1"), source_kind="human")
    event = _event(
        SocialPayload(
            type="social",
            channel_id="chat-main",
            conversation_id="conversation-1",
            sender=sender,
            content="hello",
        )
    )

    # When: the pure appraiser converts it into a limbic stimulus.
    stimulus = LimbicAppraiser().appraise(event)

    # Then: the new contract says social, not the legacy EmotionInput value text.
    assert stimulus is not None
    assert stimulus.source.value == "social"


def test_appraiser_cannot_mutate_emotion_or_homeostasis() -> None:
    # Given: the coordinator-independent pure appraiser.
    appraiser = LimbicAppraiser()

    # When / Then: no subsystem mutation port is obtainable from it.
    assert not hasattr(appraiser, "emotion_system")
    assert not hasattr(appraiser, "homeostasis")
    assert not hasattr(appraiser, "update_emotion")


def test_control_and_stimulus_contracts_reject_malformed_time_and_intensity() -> None:
    # Given: malformed control data and an out-of-range stimulus.
    malformed_pulse = {"timestamp": "5.0"}

    # When / Then: strict boundary parsing rejects both invalid forms.
    with pytest.raises(ValidationError):
        BrainClockPulse.model_validate(malformed_pulse)
    with pytest.raises(ValidationError):
        EmotionStimulusEvent(
            event_id=EventId("impact-1"),
            emotion=EmotionType.FEAR,
            intensity=1.1,
            source=StimulusSource.PHYSICAL,
        )
