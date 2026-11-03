import pytest

from devtools.nest_lab.models import LabActionRequest
from infrastructure.godot.gateway.messages import parse_runtime_command_frame
from test.devtools.nest_lab.test_actions import _world
from test.infrastructure.godot.gateway.test_protocol_v4 import _use_anchor_frame


def test_lab_furniture_cycle_keeps_semantic_target_and_home_ownership(tmp_path):
    world, gateway, actor_id = _world(tmp_path)
    world.execute_action(
        LabActionRequest(
            actor_id=actor_id,
            action="use",
            anchor_id="dorm-01/bed-01",
            furniture_cycle="sleep-left",
        )
    )
    assert gateway.commands[-1][1]["furniture_cycle"] == "sleep-left"
    assert gateway.commands[-1][1]["anchor_id"] == "dorm-01/bed-01"
    frame = _use_anchor_frame(**gateway.commands[-1][1])
    frame["cause_id"] = gateway.commands[-1][1]["command_id"]
    frame["target_actor_id"] = actor_id
    request = parse_runtime_command_frame(frame)
    assert request.payload["furniture_cycle"] == "sleep-left"


def test_cycle_cannot_be_attached_to_unrelated_animation():
    with pytest.raises(ValueError):
        LabActionRequest(
            actor_id="a", action="animation", animation="jump", furniture_cycle="chair"
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"furniture_cycle": "unknown"},
        {"furniture_cycle": "seat", "intent": "move_to_anchor"},
        {"furniture_cycle": "seat", "interaction_transform": [0, 1, 2]},
    ],
)
def test_named_cycles_do_not_allow_arbitrary_pose_or_other_intents(overrides):
    with pytest.raises(ValueError):
        parse_runtime_command_frame(_use_anchor_frame(**overrides))
