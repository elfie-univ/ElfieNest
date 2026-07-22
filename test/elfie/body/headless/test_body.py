from datetime import datetime, timedelta, timezone

from elfie.body import (
    BodyCapabilities,
    BodyId,
    BodySensorEvent,
    CommandStatus,
    ExpressionCommand,
    HeadlessBody,
    UtteranceFinal,
)
from elfie.message_types import (
    ActorId,
    ActorRef,
    CommandId,
    EventId,
    IntentId,
    TurnId,
)

NOW = datetime(2026, 7, 22, 8, 0, tzinfo=timezone.utc)


def make_command(
    *, body_id: str = "headless_default", command_id: str = "command-1"
) -> ExpressionCommand:
    return ExpressionCommand(
        command_type="expression",
        command_id=CommandId(command_id),
        turn_id=TurnId("turn-1"),
        intent_id=IntentId("intent-1"),
        body_id=BodyId(body_id),
        issued_at=NOW,
        deadline=NOW + timedelta(seconds=1),
        capability_revision=1,
        kind="blink",
    )


def test_headless_body_drains_injected_sensor_event() -> None:
    body = HeadlessBody(body_id="debug-body")
    event = BodySensorEvent(
        event_id=EventId("turn-1"),
        body_id=BodyId("debug-body"),
        source=ActorRef(actor_id=ActorId("owner-1"), source_kind="text"),
        occurred_at=NOW,
        received_at=NOW,
        payload=UtteranceFinal(kind="utterance_final", text="你好"),
    )
    body.inject_event(event)

    events = body.read_sensor_events()

    assert events == [event]
    assert body.snapshot_body(now=NOW).pending_event_count == 0


def test_headless_body_records_supported_typed_command() -> None:
    body = HeadlessBody()
    body.connect()
    command = make_command()

    receipts = body.execute(command, now=NOW)

    assert receipts[-1].status is CommandStatus.COMPLETED
    snapshot = body.snapshot_body(now=NOW)
    assert snapshot.last_command_id == command.command_id
    assert snapshot.last_status is CommandStatus.COMPLETED


def test_headless_body_rejects_command_outside_capabilities() -> None:
    body = HeadlessBody(
        capabilities=BodyCapabilities(actions=frozenset({"speech.say"}))
    )
    body.connect()

    receipts = body.execute(make_command(), now=NOW)

    assert receipts[-1].status is CommandStatus.REJECTED
    assert receipts[-1].error is not None
    assert receipts[-1].error.code == "unsupported_capability"


def test_disconnected_headless_body_returns_correlated_rejection() -> None:
    body = HeadlessBody(body_id="headless-offline")
    command = make_command(body_id="headless-offline", command_id="offline-command")

    receipts = body.execute(command, now=NOW)

    assert body.snapshot_body(now=NOW).connected is False
    assert receipts[-1].command_id == command.command_id
    assert receipts[-1].status is CommandStatus.REJECTED
