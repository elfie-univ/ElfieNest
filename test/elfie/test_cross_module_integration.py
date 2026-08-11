"""Cross-module integration checks for the canonical typed loop."""

from __future__ import annotations

from elfie import ElfieFactory
from elfie.body import BodyId, BodySensorEvent, HeadlessBody, UtteranceFinal
from elfie.communication import (
    CommunicationEnvelope,
    CommunicationHub,
    MessageDirection,
    TextPart,
)
from elfie.message_types import ActorRef, MessageMeta
from test.elfie.test_cognitive_lifecycle import RecordingChannel, TwoTurnRuntime


def test_body_source_identity_reaches_cortical_context() -> None:
    # Given: a physical room utterance with its own source identity.
    body = HeadlessBody(body_id="cross-body")
    body.connect()
    hub = CommunicationHub("cross-elfie")
    hub.register_channel(RecordingChannel(), connect=True)
    runtime = TwoTurnRuntime()
    runtime.release_first.set()
    elfie = ElfieFactory().create(
        elfie_id="cross-elfie",
        memory_db_path=":memory:",
        body=body,
        communication=hub,
        model_port=runtime,
    )
    elfie.start()
    now = elfie.cognitive_datetime
    source = ActorRef(actor_id="room-speaker", source_kind="room")
    event = BodySensorEvent(
        event_id="room-utterance-1",
        body_id=BodyId(body.body_id),
        source=source,
        occurred_at=now,
        received_at=now,
        payload=UtteranceFinal(kind="utterance_final", text="hello from the room"),
    )

    # When: NervousSystem publishes and the Brain seals a frame.
    elfie.pump_body_events((event,))
    elfie.advance_clock(5.0)
    elfie.wait_for_outcome_count(1, timeout=1.0)

    # Then: source identity survives into the model-neutral context.
    assert "room-speaker" in runtime.requests[0].user_prompt
    assert "hello from the room" in runtime.requests[0].user_prompt
    elfie.stop()
    elfie.join()


def test_non_owner_social_input_is_not_written_as_owner_memory() -> None:
    # Given: a peer-origin digital message on a connected channel.
    body = HeadlessBody(body_id="peer-body")
    body.connect()
    hub = CommunicationHub("peer-elfie")
    hub.register_channel(RecordingChannel(), connect=True)
    runtime = TwoTurnRuntime()
    runtime.release_first.set()
    elfie = ElfieFactory().create(
        elfie_id="peer-elfie",
        memory_db_path=":memory:",
        body=body,
        communication=hub,
        model_port=runtime,
    )
    peer = ActorRef(actor_id="peer-1", source_kind="elfie")
    now = elfie.cognitive_datetime
    envelope = CommunicationEnvelope(
        meta=MessageMeta(
            event_id="peer-message-1",
            elfie_id="peer-elfie",
            source=peer,
            occurred_at=now,
            received_at=now,
            trace_id="peer-trace-1",
        ),
        account_id="peer-account",
        channel_id="chat",
        conversation_id="peer-chat",
        sender=peer,
        recipients=(ActorRef(actor_id="peer-elfie", source_kind="elfie"),),
        direction=MessageDirection.INBOUND,
        external_message_id="peer-external-1",
        dedupe_key="peer-external-1",
        parts=(TextPart(text="peer says hello"),),
    )

    # When: the peer message completes one cognitive turn.
    elfie.start()
    elfie.receive_communication_envelope(envelope)
    elfie.advance_clock(0.5)
    elfie.wait_for_outcome_count(1, timeout=1.0)

    # Then: identity reaches context but owner-compatible memory is untouched.
    assert "peer-1" in runtime.requests[0].user_prompt
    assert elfie.memory.get_all_episodes() == []
    elfie.stop()
    elfie.join()
