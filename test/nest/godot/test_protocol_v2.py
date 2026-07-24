from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from nest.godot.messages import (
    CommandName,
    EventName,
    IntentTerminalStatus,
    RuntimeCommandFrame,
    parse_runtime_command_frame,
    parse_runtime_event_frame,
)


def test_runtime_protocol_v2_accepts_strict_command_and_event_frames() -> None:
    # Given
    issued_at = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)
    command = RuntimeCommandFrame(
        protocol=2,
        kind="command",
        name=CommandName.EXECUTE_INTENT,
        message_id="msg-1",
        runtime_id="runtime-main",
        generation=1,
        world_revision=4,
        issued_at=issued_at,
        correlation_id="command-1",
        payload={
            "command_id": "command-1",
            "actor_id": "fox-1",
            "intent": "move_to_anchor",
            "anchor_id": "activity-main",
            "deadline_seconds": 10.0,
        },
    )
    event_payload = {
        "command_id": "command-1",
        "actor_id": "fox-1",
        "status": "completed",
        "detail": "arrived",
    }

    # When
    parsed_command = parse_runtime_command_frame(command.model_dump(mode="json"))
    parsed_event = parse_runtime_event_frame(
        {
            "protocol": 2,
            "kind": "event",
            "name": "intent_terminal",
            "message_id": "event-1",
            "runtime_id": "runtime-main",
            "generation": 1,
            "world_revision": 4,
            "occurred_at": issued_at.isoformat(),
            "correlation_id": "command-1",
            "payload": event_payload,
        }
    )

    # Then
    assert parsed_command == command
    assert parsed_event.name is EventName.INTENT_TERMINAL
    assert parsed_event.payload["status"] == IntentTerminalStatus.COMPLETED


def test_runtime_protocol_v2_rejects_v1_unknown_names_and_extra_fields() -> None:
    # Given
    base_event = {
        "protocol": 2,
        "kind": "event",
        "name": "world_ready",
        "message_id": "event-1",
        "runtime_id": "runtime-main",
        "generation": 1,
        "world_revision": 4,
        "occurred_at": "2026-07-24T12:00:00+00:00",
        "payload": {"ready": True},
    }
    v1_event = base_event | {"protocol": 1}
    unknown_event = base_event | {"name": "arrived_at"}
    extra_event = base_event | {"debug_position": [1, 2, 3]}

    # When / Then
    with pytest.raises(ValidationError):
        parse_runtime_event_frame(v1_event)
    with pytest.raises(ValidationError):
        parse_runtime_event_frame(unknown_event)
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        parse_runtime_event_frame(extra_event)


def test_runtime_protocol_v2_rejects_unknown_terminal_status() -> None:
    # Given
    terminal_event = {
        "protocol": 2,
        "kind": "event",
        "name": "intent_terminal",
        "message_id": "event-1",
        "runtime_id": "runtime-main",
        "generation": 1,
        "world_revision": 4,
        "occurred_at": "2026-07-24T12:00:00+00:00",
        "correlation_id": "command-1",
        "payload": {
            "command_id": "command-1",
            "actor_id": "fox-1",
            "status": "timed_out",
        },
    }

    # When / Then
    with pytest.raises(ValidationError, match="completed.*failed.*cancelled"):
        parse_runtime_event_frame(terminal_event)


def test_runtime_protocol_v2_rejects_forged_correlation_and_payload_fields() -> None:
    event = {
        "protocol": 2,
        "kind": "event",
        "name": "intent_started",
        "message_id": "event-1",
        "runtime_id": "runtime-main",
        "generation": 1,
        "world_revision": 4,
        "occurred_at": "2026-07-24T12:00:00+00:00",
        "correlation_id": "other-command",
        "payload": {
            "command_id": "command-1",
            "actor_id": "fox-1",
        },
    }

    with pytest.raises(ValidationError, match="correlation_id"):
        parse_runtime_event_frame(event)
    event["correlation_id"] = "command-1"
    event["payload"]["position"] = [1, 2, 3]
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        parse_runtime_event_frame(event)


def test_runtime_protocol_v2_rejects_invalid_outbound_command_payloads() -> None:
    command = {
        "protocol": 2,
        "kind": "command",
        "name": "execute_intent",
        "message_id": "command-frame-1",
        "runtime_id": "runtime-main",
        "generation": 1,
        "world_revision": 4,
        "issued_at": "2026-07-24T12:00:00+00:00",
        "correlation_id": "forged-command",
        "payload": {
            "command_id": "command-1",
            "actor_id": "fox-1",
            "intent": "move_to_anchor",
            "anchor_id": "activity-01/activity",
            "deadline_seconds": 10.0,
        },
    }

    with pytest.raises(ValidationError, match="correlation_id"):
        parse_runtime_command_frame(command)
    command["correlation_id"] = "command-1"
    command["payload"]["position"] = [1, 2, 3]
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        parse_runtime_command_frame(command)


def test_scene_manifest_event_allows_nested_semantic_payload() -> None:
    event = parse_runtime_event_frame(
        {
            "protocol": 2,
            "kind": "event",
            "name": "scene_manifest",
            "message_id": "event-1",
            "runtime_id": "runtime-main",
            "generation": 1,
            "world_revision": 4,
            "occurred_at": "2026-07-24T12:00:00+00:00",
            "payload": {
                "nest_id": "local-nest",
                "world_revision": 4,
                "bed_count": 2,
                "zones": [
                    {
                        "zone_id": "dorm-01",
                        "kind": "dorm",
                        "label": "宿舍",
                        "stable_order": 0,
                        "active": True,
                    }
                ],
                "anchors": [
                    {
                        "anchor_id": "dorm-01/bed-01",
                        "zone_id": "dorm-01",
                        "kind": "bed",
                        "label": "床位",
                        "stable_order": 0,
                        "active": True,
                    }
                ],
            },
        }
    )

    assert event.payload["bed_count"] == 2


@pytest.mark.parametrize("event_name", ["config_rejected", "startup_error"])
def test_runtime_protocol_v2_accepts_typed_world_startup_failures(
    event_name: str,
) -> None:
    event = parse_runtime_event_frame(
        {
            "protocol": 2,
            "kind": "event",
            "name": event_name,
            "message_id": "event-error",
            "runtime_id": "runtime-main",
            "generation": 1,
            "world_revision": 4,
            "occurred_at": "2026-07-24T12:00:00+00:00",
            "correlation_id": "configure-1",
            "payload": {"code": "stale_revision"},
        }
    )

    assert event.name.value == event_name
