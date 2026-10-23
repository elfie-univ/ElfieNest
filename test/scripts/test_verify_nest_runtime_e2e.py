"""Offline checks of the acceptance harness; these do not prove a live Godot run."""

import ast
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from infrastructure.godot.gateway.messages import (
    EventName,
    RuntimeEventFrame,
    SemanticLane,
)
from scripts.internal.diagnostics import verify_nest_runtime_e2e as acceptance


def event(name, payload, *, lane=SemanticLane.NEST, target=None, cause_id=None):
    return RuntimeEventFrame(
        protocol=3,
        kind="event",
        lane=lane,
        name=name,
        message_id=f"test-{name.value}",
        cause_id=cause_id or payload.get("command_id", payload.get("observation_id")),
        target_actor_id=target,
        runtime_id="offline-runtime",
        generation=1,
        world_revision=1,
        occurred_at=datetime.now(timezone.utc),
        payload=payload,
    )


def startup():
    return [
        event(
            EventName.SCENE_MANIFEST,
            {
                "nest_id": "offline-nest",
                "world_revision": 1,
                "bed_count": 32,
                "zones": [
                    {
                        "zone_id": "dorm-01",
                        "kind": "dorm",
                        "label": "Dorm",
                        "stable_order": 0,
                        "active": True,
                    }
                ],
                "anchors": [
                    {
                        "anchor_id": "dorm-01/chair-01",
                        "zone_id": "dorm-01",
                        "kind": "chair",
                        "label": "Chair",
                        "stable_order": 0,
                        "active": True,
                    }
                ],
                "facilities": [
                    {
                        "facility_id": "dorm-01/rest",
                        "zone_id": "dorm-01",
                        "kind": "rest",
                        "label": "Rest",
                        "active": True,
                    }
                ],
            },
        ),
        event(
            EventName.WORLD_SNAPSHOT,
            {
                "world_revision": 1,
                "actors": [
                    {
                        "actor_id": "tovren-1",
                        "zone_id": "dorm-01",
                        "posture": "standing",
                        "active_command_id": None,
                    }
                ],
            },
        ),
    ]


def visual(ids, *, zone="dorm-01", actor="saevi-1"):
    return event(
        EventName.VISUAL_OBSERVATION,
        {
            "observation_id": "real-visual-1",
            "actor_id": actor,
            "zone_id": zone,
            "visible_semantic_ids": ids,
        },
    )


@pytest.mark.parametrize(
    "ids",
    [
        ["anchor/dorm-01/chair-01"],
        ["facility/dorm-01/rest", "actor/tovren-1"],
    ],
)
def test_vision_checks_real_manifest_targets_without_requiring_dorm_rest(ids):
    assert acceptance._visible_semantic_ids(visual(ids), startup()) == tuple(ids)


def test_wait_for_fails_immediately_on_actual_startup_failure(monkeypatch):
    failure = event(
        EventName.STARTUP_ERROR,
        {"code": "navigation_anchors_unreachable", "accepted": False},
    )
    monkeypatch.setattr(acceptance, "_pump", lambda *_: [failure])
    monkeypatch.setattr(
        acceptance.time,
        "sleep",
        lambda *_: pytest.fail("startup error was hidden behind a timeout"),
    )
    with pytest.raises(RuntimeError, match="navigation_anchors_unreachable"):
        acceptance._wait_for(None, None, lambda _: False, timeout=1)


@pytest.mark.parametrize("posture", ["sleeping", "sitting"])
def test_furniture_snapshot_requires_actual_posture_and_command_correlation(posture):
    snapshot = event(
        EventName.WORLD_SNAPSHOT,
        {
            "world_revision": 1,
            "actors": [
                {
                    "actor_id": "saevi-1",
                    "zone_id": "dorm-01",
                    "posture": posture,
                    "active_command_id": None,
                }
            ],
        },
        cause_id="real-use",
    )
    assert acceptance._has_action_snapshot([snapshot], "real-use", posture)
    assert not acceptance._has_action_snapshot([snapshot], "unrelated", posture)
    assert not acceptance._has_action_snapshot([snapshot], "real-use", "standing")


@pytest.mark.parametrize(
    "ids,zone,actor",
    [
        ([], "dorm-01", "saevi-1"),
        (["anchor/activity-01/activity"], "dorm-01", "saevi-1"),
        (["actor/saevi-1"], "dorm-01", "saevi-1"),
        (["anchor/dorm-01/chair-01"] * 2, "dorm-01", "saevi-1"),
        (["facility/dorm-01/rest"], "courtyard", "saevi-1"),
        (["facility/dorm-01/rest"], "dorm-01", "unknown"),
    ],
)
def test_vision_rejects_empty_unknown_duplicate_or_wrong_zone_targets(ids, zone, actor):
    with pytest.raises(RuntimeError):
        acceptance._visible_semantic_ids(visual(ids, zone=zone, actor=actor), startup())


def test_vision_rejects_stale_manifest():
    observed = visual(["anchor/dorm-01/chair-01"]).model_copy(
        update={"world_revision": 2}
    )
    with pytest.raises(RuntimeError, match="manifest"):
        acceptance._visible_semantic_ids(observed, startup())


class OfflineGateway:
    """Synchronous wire fixture, never a WebSocket server or a real Runtime."""

    def __init__(self, *, omit=None, status="completed", identity=None):
        self.omit = omit
        self.status = status
        self.identity = identity or {}
        self.sink = None
        self.sent = []
        self.runtime_connection = MagicMock(runtime_id="offline-runtime", generation=1)
        self.runtime_world_revision = 1

    def register_body_sink(self, actor_id, sink):
        self.sink = sink

    def unregister_body_sink(self, actor_id, sink):
        assert self.sink is sink
        self.sink = None

    def send_body_command(self, payload, *, cause_id):
        self.sent.append(payload)
        for name in (
            EventName.INTENT_ACCEPTED,
            EventName.INTENT_STARTED,
            EventName.INTENT_TERMINAL,
        ):
            if name == self.omit:
                continue
            identity = {
                key: payload[key]
                for key in ("command_id", "actor_id", "intent_id", "body_generation")
            }
            identity.update(self.identity)
            if name is EventName.INTENT_TERMINAL:
                identity["status"] = self.status
            self.sink.receive_runtime_event(
                event(name, identity, lane=SemanticLane.BODY, target="saevi-1")
            )
        return True


@pytest.mark.parametrize("anchor", ["dorm-01/bed-01", "dorm-01/chair-01"])
def test_furniture_uses_native_body_and_requires_wire_lifecycle(anchor):
    gateway = OfflineGateway()
    result = acceptance._use_furniture(gateway, anchor)

    assert result["receipts"] == ["accepted", "started", "completed"]
    assert result["anchor_id"] == anchor
    assert len(gateway.sent) == 1
    assert gateway.sent[0]["intent"] == "use_anchor"
    assert gateway.sent[0]["anchor_id"] == anchor
    assert gateway.sent[0]["initiator"] == "elfie"
    assert gateway.sent[0]["body_generation"] == 1
    assert not {"posture", "position", "interaction_transform"} & gateway.sent[0].keys()
    assert gateway.sink is None


@pytest.mark.parametrize(
    "options",
    [
        {"omit": EventName.INTENT_ACCEPTED},
        {"omit": EventName.INTENT_STARTED},
        {"status": "failed"},
        {"status": "cancelled"},
        {"identity": {"intent_id": "unrelated"}},
        {"identity": {"body_generation": 2}},
    ],
)
def test_furniture_rejects_missing_failed_or_miscorrelated_wire_evidence(options):
    gateway = OfflineGateway(**options)
    with pytest.raises(RuntimeError):
        acceptance._use_furniture(gateway, "dorm-01/bed-01")
    assert gateway.sink is None


def test_identity_fixture_loads_bundled_catalog_without_bootstrap_or_elfie_home(
    monkeypatch,
):
    from elfie.profile import species_registry

    monkeypatch.setattr(species_registry, "_catalog", None)
    elfie = acceptance._elfie("saevi-1", "saevi", 101)
    assert elfie.profile.identity.elfie_id == "saevi-1"
    assert elfie.mock_calls == []


def test_identity_fixture_supplies_actual_species_and_appearance_to_production_catalog():
    from app.orchestration.nest_session.residents import actor_catalog

    descriptors = actor_catalog(
        {"tovren-1": acceptance._elfie("tovren-1", "tovren", 202)}
    )
    assert descriptors[0].species == "tovren"
    assert descriptors[0].appearance


def test_cancel_snapshot_matches_cancelled_actor_and_requires_actual_idle_state():
    snapshot = event(
        EventName.WORLD_SNAPSHOT,
        {
            "world_revision": 1,
            "actors": [
                {
                    "actor_id": "tovren-1",
                    "zone_id": "dorm-01",
                    "posture": "idle",
                    "active_command_id": None,
                    "action_anchor_id": None,
                }
            ],
        },
        cause_id="cancel-1",
    )
    assert acceptance._has_action_snapshot(
        [snapshot], "cancel-1", "idle", actor_id="tovren-1"
    )
    assert not acceptance._has_action_snapshot(
        [snapshot], "cancel-1", "walking", actor_id="tovren-1"
    )
    assert not acceptance._has_action_snapshot(
        [snapshot], "cancel-1", "idle", actor_id="saevi-1"
    )


def test_direct_body_commands_keep_v3_identity_and_current_movement_targets():
    tree = ast.parse(Path(acceptance.__file__).read_text())
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "RuntimeIntentPayload"
    ]
    assert len(calls) == 3  # Speech, two sequential destinations, cancellation.
    for call in calls:
        assert {"intent_id", "body_generation", "initiator"} <= {
            keyword.arg for keyword in call.keywords
        }
    literals = {node.value for node in ast.walk(tree) if isinstance(node, ast.Str)}
    assert {"central-01/activity", "courtyard/activity"} <= literals
    assert "activity-01/activity" not in literals


def test_startup_allows_cold_import_and_scene_load():
    tree = ast.parse(Path(acceptance.__file__).read_text())
    startup = next(
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "startup"
            for target in node.targets
        )
    )
    timeout = next(
        keyword.value for keyword in startup.keywords if keyword.arg == "timeout"
    )
    assert ast.literal_eval(timeout) == 90.0


def test_gateway_estate_harness_leaves_commands_and_acceptance_to_real_owners():
    source = (
        Path(acceptance.PROJECT_ROOT)
        / "godot_project/scripts/test/test_gateway_estate_e2e.gd"
    ).read_text()
    assert source.startswith("extends SceneTree")
    assert 'load("res://main.tscn")' in source
    assert 'get("_runtime_client")' in source
    assert 'get("_socket")' in source
    assert 'get("_handshake_complete")' in source
    assert "WebSocketPeer.STATE_OPEN" in source
    assert "WebSocketPeer.STATE_CLOSED" in source
    assert "110_000" in source
    assert ".queue_free()" in source
    for forbidden in (
        "WebSocketPeer.new",
        ".poll(",
        "send_text(",
        "execute_intent(",
        "OS.set_environment",
        "save_png",
        "print(",
    ):
        assert forbidden not in source


def test_observer_recording_uses_public_semantics_and_only_advances_on_change(tmp_path):
    import json
    from types import SimpleNamespace

    entity = MagicMock()
    entity.room_id = "fixture-nest"
    semantic = {
        "room_id": "fixture-nest",
        "posture": "sleeping",
        "action_anchor_id": "dorm-01/bed-01",
    }
    entity.model_dump.return_value = semantic
    engine = MagicMock()
    engine.session.observer_semantic_entities.return_value = {"saevi-1": entity}
    engine.nest.config.bed_count = 32
    server = SimpleNamespace(
        runtime_connection=SimpleNamespace(generation=1), runtime_world_revision=1
    )
    recording = acceptance._ObserverRecording(tmp_path / "observer.json")
    recording.capture(engine, server)
    recording.capture(engine, server)
    result = json.loads(recording.path.read_text())
    assert result["snapshot"]["sequence"] == 1
    assert result["snapshot"]["entities"] == {"saevi-1": semantic}
    assert result["world_config"]["nest_id"] == "fixture-nest"
    assert "position" not in recording.path.read_text()
    recording.capture(engine, server, "passed")
    assert json.loads(recording.path.read_text())["snapshot"]["sequence"] == 2


def test_recorded_body_call_keeps_pumping_without_losing_wire_events(
    tmp_path, monkeypatch
):
    from threading import Event

    pumped = Event()
    frame = event(
        EventName.SPEECH_REACH,
        {
            "command_id": "speech",
            "actor_id": "saevi-1",
            "zone_id": "dorm-01",
            "audience_actor_ids": [],
        },
    )

    def pump(*_args):
        pumped.set()
        return [frame]

    monkeypatch.setattr(acceptance, "_pump", pump)
    recording = acceptance._ObserverRecording(tmp_path / "observer.json")

    def invoke():
        assert pumped.wait(1)
        return "completed"

    assert acceptance._run_action(None, None, recording, invoke) == "completed"
    assert frame in recording.pending_events
    assert acceptance._wait_for(
        None, None, lambda frames: frame in frames, timeout=1, recording=recording
    )
    assert recording.pending_events == []
