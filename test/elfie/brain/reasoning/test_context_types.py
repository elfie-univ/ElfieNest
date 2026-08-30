"""Contract tests for immutable Brain context snapshots."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from elfie.brain.emotion.contracts import EmotionSnapshot, EmotionValue
from elfie.brain.emotion.emotion_types import EmotionType
from elfie.brain.energy.contracts import EnergySnapshot
from elfie.brain.memory.contracts import MemoryContext, MemoryItem
from elfie.brain.reasoning.context_types import (
    BodyCapabilityDescriptor,
    BrainContext,
    ConnectedChannelDescriptor,
    ConversationContext,
    ConversationMessage,
    EffectiveCapabilities,
)
from elfie.brain.workspace.contracts import (
    InternalScope,
    ResponseScope,
    SourceDomain,
    TriggerReason,
    TurnFrame,
)
from elfie.message_types import ActorId, ActorRef, ElfieId, EventId

NOW = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)


def _frame() -> TurnFrame:
    return TurnFrame(
        frame_id=EventId("frame-1"),
        elfie_id=ElfieId("elfie-1"),
        revision=4,
        captured_at=NOW,
        cutoff_seq=9,
        trigger_reason=TriggerReason.SALIENCE,
        source_domain=SourceDomain.INTERNAL,
        interaction_scope=InternalScope(cause_id="manual-test"),
        response_scope=ResponseScope(external_domain=None),
    )


def test_brain_context_round_trip_preserves_revisions_and_capabilities() -> None:
    # Given: sealed perception plus timestamped snapshots and effective ports.
    context = BrainContext(
        revision=7,
        captured_at=NOW,
        frame=_frame(),
        emotion=EmotionSnapshot(
            revision=2,
            captured_at=NOW,
            values=tuple(
                EmotionValue(
                    name=emotion,
                    intensity=0.7 if emotion is EmotionType.HAPPINESS else 0.0,
                )
                for emotion in EmotionType
            ),
            active=(EmotionValue(name=EmotionType.HAPPINESS, intensity=0.7),),
            primary=EmotionType.HAPPINESS,
        ),
        homeostasis=EnergySnapshot(
            revision=3,
            captured_at=NOW,
            energy=82.0,
            fatigue=18.0,
            sleeping=False,
        ),
        conversation=ConversationContext(
            revision=5,
            captured_at=NOW,
            conversation_id="conversation-1",
            messages=(
                ConversationMessage(
                    event_id=EventId("social-event"),
                    sender=ActorRef(
                        actor_id=ActorId("user-1"),
                        source_kind="human",
                    ),
                    occurred_at=NOW,
                    content="hello",
                ),
            ),
        ),
        memory=MemoryContext(
            revision=6,
            captured_at=NOW,
            items=(
                MemoryItem(
                    memory_id=EventId("memory-1"),
                    content="the user prefers concise replies",
                    relevance=0.9,
                    source_event_ids=(EventId("social-event"),),
                ),
            ),
        ),
        capabilities=EffectiveCapabilities(
            revision=8,
            captured_at=NOW,
            current_body=BodyCapabilityDescriptor(
                body_id="body-1",
                capability_revision=11,
                sensors=("utterance", "touch"),
                actions=("speak", "walk"),
            ),
            connected_channels=(
                ConnectedChannelDescriptor(
                    channel_id="wechat-main",
                    account_id="account-1",
                    capability_revision=12,
                    content_kinds=("text", "image"),
                ),
            ),
        ),
    )

    # When: the complete context crosses a JSON boundary.
    restored = BrainContext.model_validate_json(context.model_dump_json())

    # Then: every revision, timestamp, and effective endpoint survives.
    assert restored == context
    assert restored.frame.revision == 4
    assert restored.capabilities.current_body is not None
    assert restored.capabilities.current_body.body_id == "body-1"
    assert restored.capabilities.connected_channels[0].channel_id == "wechat-main"


def test_effective_capabilities_rejects_deferred_realm_fields() -> None:
    # Given: a caller tries to add deferred scene/realm availability.
    raw = {
        "revision": 1,
        "captured_at": NOW,
        "current_body": None,
        "connected_channels": (),
        "available_realms": ("dream",),
    }

    # When / Then: the first-version capability boundary stays closed.
    with pytest.raises(ValidationError, match="available_realms"):
        EffectiveCapabilities.model_validate(raw)


def test_brain_context_rejects_snapshot_captured_after_context() -> None:
    # Given: an emotion snapshot newer than the context capture boundary.
    future = datetime(2026, 7, 21, 8, 1, tzinfo=timezone.utc)
    emotion = EmotionSnapshot.inactive(captured_at=future, revision=1)

    # When / Then: stale temporal assembly fails at construction.
    with pytest.raises(ValidationError, match="captured_at"):
        BrainContext(
            revision=1,
            captured_at=NOW,
            frame=_frame(),
            emotion=emotion,
            homeostasis=EnergySnapshot(
                revision=1,
                captured_at=NOW,
                energy=50.0,
                fatigue=50.0,
                sleeping=False,
            ),
            conversation=ConversationContext(
                revision=1,
                captured_at=NOW,
                conversation_id=None,
                messages=(),
            ),
            memory=MemoryContext(revision=1, captured_at=NOW, items=()),
            capabilities=EffectiveCapabilities(
                revision=1,
                captured_at=NOW,
                current_body=None,
                connected_channels=(),
            ),
        )
