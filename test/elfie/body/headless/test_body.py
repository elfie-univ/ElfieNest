from elfie.body import (
    BodyCapabilities,
    BodyCommand,
    CommandStatus,
    HeadlessBody,
)


def test_headless_body_drains_injected_sensor_data() -> None:
    body = HeadlessBody(body_id="debug-body")
    body.connect()
    body.inject_sensor_data(
        {"message_id": "turn-1", "user_message": "你好"},
        event_id="turn-1",
    )

    events = body.read_events()

    assert len(events) == 1
    assert events[0].event_id == "turn-1"
    assert events[0].to_sensor_data()["user_message"] == "你好"
    assert body.snapshot().pending_event_count == 0


def test_headless_body_records_supported_action() -> None:
    body = HeadlessBody()
    body.connect()

    result = body.execute(BodyCommand(action="face.blink"))

    assert result.status is CommandStatus.COMPLETED
    assert result.output["recorded"] is True
    assert body.last_result is result
    assert body.snapshot().last_action == "face.blink"


def test_headless_body_rejects_action_outside_capabilities() -> None:
    body = HeadlessBody(
        capabilities=BodyCapabilities(
            sensors=frozenset({"text"}),
            actions=frozenset({"speech.say"}),
        )
    )
    body.connect()

    result = body.execute(BodyCommand(action="tail.wag"))

    assert result.status is CommandStatus.REJECTED
    assert "不支持动作" in result.error
