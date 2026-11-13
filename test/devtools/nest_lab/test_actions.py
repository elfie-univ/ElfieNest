from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from devtools.nest_lab.app import create_app
from devtools.nest_lab.models import LabActionRequest, NestLabConflictError
from devtools.nest_lab.world import NestLabWorld
from infrastructure.godot.gateway.messages import CommandName
from nest.space_facilities.models import AnchorKind, InteractionAnchor
from test.devtools.nest_lab.test_world import (
    _LabGateway,
    _PendingLabGateway,
    _saved_actors,
)


def _world(tmp_path, gateway=None):
    gateway = gateway or _LabGateway()
    gateway.connect()
    world = NestLabWorld(
        data_dir=tmp_path,
        http_port=8890,
        websocket_port=8891,
        gateway=gateway,
        saved_actors=_saved_actors(tmp_path),
    )
    world.poll()
    actor = world.add_actor("saevi")
    return world, gateway, actor.actor_id


def test_animation_preview_uses_the_existing_runtime_expression(tmp_path):
    world, gateway, actor_id = _world(tmp_path)
    result = world.execute_action(
        LabActionRequest(actor_id=actor_id, action="animation", animation="jump")
    )
    name, payload, revision = gateway.commands[-1]
    assert name is CommandName.EXECUTE_INTENT
    assert payload["intent"] == "emotion_expression"
    assert payload["expression"] == "jump"
    assert payload["actor_id"] == actor_id
    assert revision == 1
    assert result["command_id"] == payload["command_id"]
    assert "completed" in world.events()[-1]["detail"]


def test_inspection_chairs_stay_selectable_without_becoming_wander_targets(tmp_path):
    world, _, _ = _world(tmp_path)
    catalog = world._nest.world_catalog
    assert catalog is not None
    inspection = InteractionAnchor(
        anchor_id="dorm-01/inspection-chair",
        kind=AnchorKind.CHAIR,
        label="检查单人沙发",
        order=99,
        active=False,
    )
    zone = catalog.zones[0].model_copy(
        update={"anchors": (*catalog.zones[0].anchors, inspection)}
    )
    world._nest.apply_catalog(
        catalog.model_copy(update={"zones": (zone, *catalog.zones[1:])})
    )
    assert any(t["anchor_id"] == inspection.anchor_id for t in world.action_targets())
    assert inspection.anchor_id not in world._wander_scheduler._available_anchors()


def test_switch_waits_for_cancellation_and_starts_only_latest_selection(tmp_path):
    class DelayedCancelGateway(_PendingLabGateway):
        def send_runtime_command(self, name, payload, *, world_revision, cause_id=None):
            if name is CommandName.CANCEL_INTENT:
                self.commands.append((name, payload, world_revision))
                return cause_id
            return super().send_runtime_command(
                name, payload, world_revision=world_revision, cause_id=cause_id
            )

    world, gateway, actor_id = _world(tmp_path, DelayedCancelGateway())
    first = world.execute_action(
        LabActionRequest(actor_id=actor_id, action="animation", animation="jump")
    )
    world.execute_action(
        LabActionRequest(actor_id=actor_id, action="animation", animation="pose_waving")
    )
    latest = world.execute_action(
        LabActionRequest(actor_id=actor_id, action="animation", animation="idle")
    )
    assert gateway.commands[-1][0] is CommandName.CANCEL_INTENT
    assert (
        sum(name is CommandName.CANCEL_INTENT for name, _, _ in gateway.commands) == 1
    )
    world._actions.complete({"actor_id": actor_id, "command_id": "stale-command"})
    assert gateway.commands[-1][0] is CommandName.CANCEL_INTENT
    world._actions.complete({"actor_id": actor_id, "command_id": first["command_id"]})
    assert gateway.commands[-1][1]["expression"] == "idle"
    assert gateway.commands[-1][1]["command_id"] == latest["command_id"]


def test_lab_can_preview_any_bed_without_changing_home_ownership(tmp_path):
    world, gateway, actor_id = _world(tmp_path)
    targets = world.action_targets()
    assert targets[0]["anchor_id"] == "dorm-01/bed-01"
    assert targets[0]["kind"] == "bed"
    world.execute_action(
        LabActionRequest(actor_id=actor_id, action="use", anchor_id="dorm-01/bed-01")
    )
    assert gateway.commands[-1][1]["intent"] == "use_anchor"
    world.execute_action(
        LabActionRequest(actor_id=actor_id, action="use", anchor_id="dorm-01/bed-02")
    )
    assert gateway.commands[-1][1]["anchor_id"] == "dorm-01/bed-02"
    assert world._nest.home_anchor_id(actor_id) == "dorm-01/bed-01"


def test_manual_action_cancels_wandering_before_issuing_the_command(tmp_path):
    world, gateway, actor_id = _world(tmp_path, _PendingLabGateway())
    world.set_wandering()
    world.execute_action(
        LabActionRequest(actor_id=actor_id, action="move", anchor_id="dorm-01/bed-01")
    )
    assert not world.world()["wandering"]
    assert any(name is CommandName.CANCEL_INTENT for name, _, _ in gateway.commands)
    assert gateway.commands[-1][1]["intent"] == "move_to_anchor"
    world.stop_action(actor_id)
    world.poll()
    assert gateway.commands[-2][0] is CommandName.CANCEL_INTENT
    assert gateway.commands[-1][1]["expression"] == "idle"


def test_actions_reject_unknown_actors_and_unavailable_runtime(tmp_path):
    world, gateway, actor_id = _world(tmp_path)
    with pytest.raises(NestLabConflictError, match="角色"):
        world.execute_action(
            LabActionRequest(actor_id="missing", action="animation", animation="jump")
        )
    gateway.disconnect()
    with pytest.raises(NestLabConflictError, match="就绪"):
        world.execute_action(
            LabActionRequest(actor_id=actor_id, action="animation", animation="jump")
        )


def test_prepare_demonstration_cancels_without_queuing_idle_or_wandering(tmp_path):
    world, gateway, actor_id = _world(tmp_path, _PendingLabGateway())
    world.execute_action(
        LabActionRequest(actor_id=actor_id, action="animation", animation="jump")
    )
    assert world.prepare_demonstration(actor_id) == {"actor_id": actor_id}
    assert gateway.commands[-1][0] is CommandName.CANCEL_INTENT
    assert not world.world()["wandering"]
    with pytest.raises(NestLabConflictError):
        world.prepare_demonstration("missing")


def test_simulation_pause_also_cancels_a_manual_move(tmp_path):
    world, gateway, actor_id = _world(tmp_path, _PendingLabGateway())
    world.execute_action(
        LabActionRequest(actor_id=actor_id, action="move", anchor_id="dorm-01/bed-01")
    )
    world.pause()
    world.poll()
    assert any(name is CommandName.CANCEL_INTENT for name, _, _ in gateway.commands)
    assert gateway.commands[-1][1]["expression"] == "idle"


def test_lab_action_routes_validate_requests_and_remain_isolated(tmp_path):
    client = TestClient(create_app(tmp_path), base_url="http://127.0.0.1")
    assert client.get("/api/action-targets").json() == {"items": []}
    assert (
        client.post(
            "/api/actions", json={"actor_id": "missing", "action": "animation"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/actions",
            json={"actor_id": "missing", "action": "animation", "animation": "jump"},
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "move", "anchor_id": ""},
        {"action": "animation", "animation": "jump", "anchor_id": "a"},
        {"action": "use", "anchor_id": "a", "animation": "jump"},
    ],
)
def test_incompatible_action_fields_are_rejected(payload):
    with pytest.raises(ValueError):
        LabActionRequest(actor_id="actor", **payload)
