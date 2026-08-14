from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from infrastructure.godot.gateway.messages import (
    CommandName,
    EventName,
    RuntimeCommandFrame,
    SemanticLane,
    parse_runtime_command_frame,
    parse_runtime_event_frame,
)

OCCURRED_AT = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)


def test_protocol_v3_preserves_body_target_cause_and_physical_values() -> None:
    event = parse_runtime_event_frame(
        {
            "protocol": 3,
            "kind": "event",
            "lane": "body",
            "name": "tactile_contact",
            "message_id": "touch-1",
            "cause_id": "move-1",
            "target_actor_id": "elfie-1",
            "runtime_id": "runtime-main",
            "generation": 2,
            "world_revision": 4,
            "occurred_at": OCCURRED_AT.isoformat(),
            "payload": {
                "actor_id": "elfie-1",
                "intensity": 0.4,
                "direction": "left",
                "contact_kind": "world",
                "source_semantic_id": "wall-1",
            },
        }
    )

    assert event.protocol == 3
    assert event.lane is SemanticLane.BODY
    assert event.target_actor_id == "elfie-1"
    assert event.cause_id == "move-1"
    assert event.payload.get("force_newtons") is None


def test_protocol_v3_requires_exact_lane_and_target_pairing() -> None:
    body_event = {
        "protocol": 3,
        "kind": "event",
        "lane": "body",
        "name": "intent_started",
        "message_id": "event-1",
        "cause_id": "command-1",
        "runtime_id": "runtime-main",
        "generation": 1,
        "world_revision": 4,
        "occurred_at": OCCURRED_AT.isoformat(),
        "payload": {"command_id": "command-1", "actor_id": "elfie-1"},
    }
    with pytest.raises(ValidationError, match="target_actor_id"):
        parse_runtime_event_frame(body_event)

    nest_event = {
        "protocol": 3,
        "kind": "event",
        "lane": "nest",
        "name": "world_configured",
        "message_id": "event-2",
        "target_actor_id": "elfie-1",
        "runtime_id": "runtime-main",
        "generation": 1,
        "world_revision": 4,
        "occurred_at": OCCURRED_AT.isoformat(),
        "payload": {"configured": True, "navigation_ready": True},
    }
    with pytest.raises(ValidationError, match="target_actor_id"):
        parse_runtime_event_frame(nest_event)


def test_protocol_v3_rejects_protocol_v2_without_compatibility_parser() -> None:
    event = {
        "protocol": 2,
        "kind": "event",
        "lane": "nest",
        "name": "world_configured",
        "message_id": "event-1",
        "runtime_id": "runtime-main",
        "generation": 1,
        "world_revision": 4,
        "occurred_at": OCCURRED_AT.isoformat(),
        "payload": {"configured": True, "navigation_ready": True},
    }

    with pytest.raises(ValidationError):
        parse_runtime_event_frame(event)


def test_protocol_v3_builds_targeted_body_command() -> None:
    command = RuntimeCommandFrame(
        protocol=3,
        kind="command",
        lane=SemanticLane.BODY,
        name=CommandName.EXECUTE_INTENT,
        message_id="message-1",
        cause_id="command-1",
        target_actor_id="elfie-1",
        runtime_id="runtime-main",
        generation=1,
        world_revision=4,
        issued_at=OCCURRED_AT,
        payload={
            "command_id": "command-1",
            "actor_id": "elfie-1",
            "intent": "move_to_anchor",
            "anchor_id": "activity-01/activity",
            "deadline_seconds": 10.0,
        },
    )

    assert parse_runtime_command_frame(command.model_dump(mode="json")) == command
    assert command.target_actor_id == "elfie-1"
    assert command.cause_id == "command-1"


def test_protocol_v3_accepts_body_speech_after_nest_preflight_without_text() -> None:
    command = RuntimeCommandFrame(
        protocol=3,
        kind="command",
        lane=SemanticLane.BODY,
        name=CommandName.EXECUTE_INTENT,
        message_id="message-speech-1",
        cause_id="speech-1",
        target_actor_id="elfie-1",
        runtime_id="runtime-main",
        generation=1,
        world_revision=4,
        issued_at=OCCURRED_AT,
        payload={
            "command_id": "speech-1",
            "actor_id": "elfie-1",
            "intent": "speak",
            "deadline_seconds": 10.0,
        },
    )

    assert parse_runtime_command_frame(command.model_dump(mode="json")) == command


def test_protocol_v3_keeps_visual_observation_on_nest_lane_without_media() -> None:
    command = RuntimeCommandFrame(
        protocol=3,
        kind="command",
        lane=SemanticLane.NEST,
        name=CommandName.REQUEST_VISUAL_OBSERVATION,
        message_id="observation-request-1",
        cause_id="observation-1",
        runtime_id="runtime-main",
        generation=1,
        world_revision=4,
        issued_at=OCCURRED_AT,
        payload={
            "observation_id": "observation-1",
            "actor_id": "elfie-1",
            "max_results": 8,
        },
    )
    event = parse_runtime_event_frame(
        {
            "protocol": 3,
            "kind": "event",
            "lane": "nest",
            "name": "visual_observation",
            "message_id": "observation-event-1",
            "cause_id": "observation-1",
            "runtime_id": "runtime-main",
            "generation": 1,
            "world_revision": 4,
            "occurred_at": OCCURRED_AT.isoformat(),
            "payload": {
                "observation_id": "observation-1",
                "actor_id": "elfie-1",
                "zone_id": "dorm-01",
                "visible_semantic_ids": [
                    "actor/elfie-2",
                    "anchor/dorm-01/bed-01",
                ],
            },
        }
    )

    assert parse_runtime_command_frame(command.model_dump(mode="json")) == command
    assert event.name is EventName.VISUAL_OBSERVATION
    assert "media" not in event.payload


def test_protocol_v3_validates_environment_command_and_actual_state() -> None:
    command = RuntimeCommandFrame(
        protocol=3,
        kind="command",
        lane=SemanticLane.NEST,
        name=CommandName.APPLY_ENVIRONMENT,
        message_id="environment-request-1",
        cause_id="environment-1",
        runtime_id="runtime-main",
        generation=1,
        world_revision=4,
        issued_at=OCCURRED_AT,
        payload={
            "object_id": "nest/environment",
            "command_id": "environment-1",
            "lights_on": False,
            "quiet_mode": True,
        },
    )
    event = parse_runtime_event_frame(
        {
            "protocol": 3,
            "kind": "event",
            "lane": "nest",
            "name": "environment_state",
            "message_id": "environment-event-1",
            "cause_id": "environment-1",
            "runtime_id": "runtime-main",
            "generation": 1,
            "world_revision": 4,
            "occurred_at": OCCURRED_AT.isoformat(),
            "payload": {
                "object_id": "nest/environment",
                "command_id": "environment-1",
                "lights_on": False,
                "quiet_mode": True,
                "applied": True,
            },
        }
    )

    assert parse_runtime_command_frame(command.model_dump(mode="json")) == command
    assert event.name is EventName.ENVIRONMENT_STATE


def test_event_names_expose_world_configuration_not_world_readiness() -> None:
    assert EventName.WORLD_CONFIGURED.value == "world_configured"
    assert "world_ready" not in {event.value for event in EventName}
