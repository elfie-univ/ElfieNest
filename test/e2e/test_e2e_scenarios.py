"""Offline end-to-end scenarios for the typed Elfie cognitive loop."""

from __future__ import annotations

from elfie import ElfieFactory
from elfie.body import HeadlessBody
from elfie.communication import CommunicationHub, InboundDispositionStatus
from test.elfie.test_cognitive_lifecycle import (
    RecordingChannel,
    TwoTurnRuntime,
    _owner_message,
)


def test_owner_message_runs_through_output_and_receipt_feedback() -> None:
    body = HeadlessBody(body_id="e2e-body")
    body.connect()
    hub = CommunicationHub("elfie-loop")
    channel = RecordingChannel()
    hub.register_channel(channel, connect=True)
    runtime = TwoTurnRuntime()
    runtime.release_first.set()
    elfie = ElfieFactory().create(
        elfie_id="elfie-loop",
        memory_db_path=":memory:",
        body=body,
        communication=hub,
        model_port=runtime,
    )
    elfie.start()
    elfie.receive_communication_envelope(_owner_message(elfie.cognitive_datetime))
    elfie.advance_clock(0.5)
    elfie.wait_for_outcome_count(1, timeout=1.0)
    first = elfie.turn_outcomes()[0]
    elfie.wait_for_output(first.turn_id, timeout=1.0)
    elfie.advance_clock(5.0)
    elfie.wait_for_outcome_count(2, timeout=1.0)

    assert len(channel.sent) == 2
    assert "execution:receipt" in runtime.requests[1].user_prompt
    elfie.stop()
    elfie.join()


def test_external_message_replay_is_deduplicated_at_communication_edge() -> None:
    body = HeadlessBody(body_id="dedupe-body")
    hub = CommunicationHub("elfie-loop")
    hub.register_channel(RecordingChannel(), connect=True)
    runtime = TwoTurnRuntime()
    elfie = ElfieFactory().create(
        elfie_id="elfie-loop",
        memory_db_path=":memory:",
        body=body,
        communication=hub,
        model_port=runtime,
    )
    elfie.start()
    envelope = _owner_message(elfie.cognitive_datetime)

    first = elfie.receive_communication_envelope(envelope)
    replay = elfie.receive_communication_envelope(envelope)

    assert first.status is InboundDispositionStatus.ACCEPTED
    assert replay.status is InboundDispositionStatus.DUPLICATE
    assert len(elfie.communication.inbox.history) == 1
    elfie.stop()
    elfie.join()


def test_two_elfies_start_and_stop_without_shared_cognitive_state() -> None:
    elfies = []
    for index in range(2):
        elfie_id = f"e2e-{index}"
        body = HeadlessBody(body_id=f"body-{index}")
        hub = CommunicationHub(elfie_id)
        hub.register_channel(RecordingChannel(), connect=True)
        elfie = ElfieFactory().create(
            elfie_id=elfie_id,
            memory_db_path=":memory:",
            body=body,
            communication=hub,
            model_port=TwoTurnRuntime(),
        )
        elfie.start()
        elfies.append(elfie)

    assert all(elfie.is_running for elfie in elfies)
    for elfie in elfies:
        elfie.stop()
    for elfie in elfies:
        elfie.join()
    assert all(not elfie.is_running for elfie in elfies)
