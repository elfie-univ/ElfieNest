from typing import Any, Callable, Dict, List

from elfie import Elfie
from elfie.body import (
    BodyCommand,
    BodyId,
    BodyMode,
    BodyPort,
    CommandStatus,
    GodotTransport,
    NativeBody,
    UtteranceFinal,
)
from elfie.message_types import ActorId, EventId


class MockRuntimeAgent:
    class Config:
        providers = {"ollama": {"api_key": "", "api_base": "mock://local"}}

    config = Config()

    def ask(self, prompt: str, energy: float, task_complexity: int) -> str:
        return "听到了哒。[ACTION]nod_head[/ACTION]"


class FakeGodotGateway:
    def __init__(self) -> None:
        self.callbacks: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}
        self.sent: List[Dict[str, Any]] = []
        self.runtime_ready = False

    def register_callback(
        self, event_name: str, callback: Callable[[Dict[str, Any]], None]
    ) -> None:
        self.callbacks.setdefault(event_name, []).append(callback)

    def send_action(self, action: str, payload: Dict[str, Any]) -> None:
        self.sent.append({"action": action, "payload": payload})

    def emit(self, event_name: str, payload: Dict[str, Any]) -> None:
        for callback in self.callbacks.get(event_name, []):
            callback(payload)


def make_body(body_id: str = "elfie-1") -> tuple[NativeBody, FakeGodotGateway]:
    gateway = FakeGodotGateway()
    body = NativeBody(body_id=body_id, transport=GodotTransport(gateway))
    return body, gateway


def test_native_body_implements_body_port_without_replacing_legacy_engine() -> None:
    body, gateway = make_body()

    assert isinstance(body, BodyPort)
    assert body.describe().mode is BodyMode.NATIVE
    assert body.snapshot().connected is False
    assert gateway.callbacks == {}


def test_native_body_receives_only_its_own_existing_godot_events() -> None:
    body, gateway = make_body()
    body.connect()

    gateway.emit("user_message", {"elfie_id": "other", "message": "忽略"})
    gateway.emit(
        "user_message",
        {"elfie_id": "elfie-1", "message": "你好", "message_id": "msg-1"},
    )
    gateway.emit(
        "arrived_at",
        {"elfie_id": "elfie-1", "target": "chair_1", "posture": "sitting"},
    )

    events = body.read_events()

    assert [event.sensor for event in events] == ["hearing", "proprioception"]
    assert events[0].to_sensor_data() == {
        "has_new_message": True,
        "user_message": "你好",
        "message_id": "msg-1",
    }
    assert events[1].to_sensor_data()["target"] == "chair_1"
    assert body.snapshot().pending_event_count == 0


def test_native_body_reuses_existing_speech_expression_and_movement_events() -> None:
    body, gateway = make_body()
    body.connect()

    result = body.execute(
        BodyCommand(
            action="nod_head",
            parameters={
                "speech": "你好",
                "emotion": "happy",
                "joint_angles": {"neck_pitch": 0.4},
                "target": "chair_1",
                "posture": "sitting",
                "animation": "chat_look",
            },
        )
    )

    assert result.status is CommandStatus.COMPLETED
    assert [message["action"] for message in gateway.sent] == [
        "speak_event",
        "go_to",
        "emotion_expression",
    ]
    assert gateway.sent[0]["payload"]["elfie_id"] == "elfie-1"
    assert gateway.sent[0]["payload"]["text"] == "你好"
    assert gateway.sent[1]["payload"]["target"] == "chair_1"
    assert gateway.sent[2]["payload"]["actions"] == ["nod_head"]
    assert gateway.sent[2]["payload"]["joint_angles"] == {"neck_pitch": 0.4}


def test_native_body_disconnects_without_changing_the_shared_gateway() -> None:
    body, gateway = make_body()
    body.connect()
    body.disconnect()

    gateway.emit("user_message", {"elfie_id": "elfie-1", "message": "收不到"})
    result = body.execute(BodyCommand(action="blink_eyes"))

    assert body.read_events() == []
    assert result.status is CommandStatus.REJECTED
    assert gateway.sent == []


def test_native_body_reports_runtime_readiness_and_emergency_stop() -> None:
    body, gateway = make_body()
    body.connect()
    gateway.runtime_ready = True

    result = body.emergency_stop()

    assert result.status is CommandStatus.REJECTED
    assert "尚未实现" in result.error
    assert body.snapshot().metadata["godot_runtime_ready"] is True
    assert gateway.sent == []


def test_native_body_rejects_transport_command_without_required_payload() -> None:
    body, gateway = make_body()
    body.connect()

    result = body.execute(BodyCommand(action="movement.go_to"))

    assert result.status is CommandStatus.REJECTED
    assert "无法把命令映射" in result.error
    assert gateway.sent == []


def test_shared_transport_registers_gateway_callbacks_only_once() -> None:
    gateway = FakeGodotGateway()
    transport = GodotTransport(gateway)
    first = NativeBody(body_id="elfie-1", transport=transport)
    second = NativeBody(body_id="elfie-2", transport=transport)
    first.connect()
    second.connect()

    assert all(len(callbacks) == 1 for callbacks in gateway.callbacks.values())

    gateway.emit("user_message", {"elfie_id": "elfie-2", "message": "你好"})

    assert first.read_events() == []
    assert second.read_events()[0].to_sensor_data()["user_message"] == "你好"


def test_native_body_runs_the_existing_elfie_perception_chain_end_to_end() -> None:
    body, gateway = make_body()
    body.connect()
    elfie = Elfie(memory_db_path=":memory:", body=body)
    gateway.emit(
        "user_message",
        {"elfie_id": "elfie-1", "message": "你好", "message_id": "msg-1"},
    )

    result = elfie.perceive_body_and_respond(MockRuntimeAgent())

    assert result["success"] is True
    assert result["action"] == "nod_head"
    assert result["body_execution"]["status"] == "completed"
    assert [message["action"] for message in gateway.sent] == [
        "speak_event",
        "emotion_expression",
    ]


def test_elfie_emotion_expression_uses_current_body_instead_of_direct_godot_api() -> (
    None
):
    body, gateway = make_body()
    body.connect()
    elfie = Elfie(memory_db_path=":memory:", body=body)

    elfie._send_emotion_expression()

    assert gateway.sent[-1]["action"] == "emotion_expression"
    payload = gateway.sent[-1]["payload"]
    assert payload["elfie_id"] == "elfie-1"
    assert payload["expression"] == elfie.amygdala.get_expression()["expression"]


def test_legacy_native_port_characterization_before_contract_migration() -> None:
    """Given a disconnected native body, rejection never reaches Godot."""
    body, gateway = make_body(body_id="legacy-native")

    result = body.execute(BodyCommand(action="blink_eyes", command_id="legacy-command"))

    assert body.describe().body_id == "legacy-native"
    assert body.snapshot().connected is False
    assert result.command_id == "legacy-command"
    assert result.status is CommandStatus.REJECTED
    assert gateway.sent == []


def test_native_sensor_edge_preserves_wire_identity() -> None:
    body, gateway = make_body()
    body.connect()
    gateway.emit(
        "user_message",
        {
            "elfie_id": "elfie-1",
            "message": "你好",
            "message_id": "utterance-1",
            "actor_id": "owner-1",
        },
    )

    event = body.read_sensor_events()[0]

    assert event.event_id == EventId("utterance-1")
    assert event.body_id == BodyId("elfie-1")
    assert event.source.actor_id == ActorId("owner-1")
    assert isinstance(event.payload, UtteranceFinal)
