"""Run one real embodied Brain -> Body -> Godot acceptance round.

The diagnostic uses the production Brain, Nest session, Body, Gateway, and
Godot authority.  In the stage-one default ``mock`` embodied mode it verifies
the Brain-owned semantic wander decision and terminal Body feedback; when the
code switch is changed to ``brain`` it verifies the model follow-up path.  It
creates a synthetic Elfie and copies only provider configuration into a temporary
ELFIE_HOME so private profile, memory, and report data stay out of the live
run.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, cast

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from app.bootstrap.app_wiring.food import build_report_repository
from app.bootstrap.model_execution import build_model_execution_services
from app.bootstrap.system_wiring.nest_session import (
    load_emotion_dynamics_config,
    load_emotion_expression_config,
)
from app.features.configuration.food import StoredModelEvidence
from app.orchestration.nest_session import ElfieNestEngine
from elfie import Elfie, ElfieFactory
from elfie.body.contracts import (
    ActionOutcomePayload,
    BodyId,
    BodySensorEvent,
    ObservationCommand,
    SpeechCommand,
    UtteranceFinal,
)
from elfie.brain.reasoning.model_header import ReasoningConstitution
from elfie.factory import ElfieAssembly
from elfie.message_types import ActorId, ActorRef, CommandId, EventId, IntentId, TurnId
from infrastructure.godot.body_transport import (
    GodotTransport,
    RuntimeIntentPayload,
    RuntimeIntentResult,
)
from infrastructure.godot.gateway.api import GodotAPIServer
from infrastructure.godot.gateway.messages import CommandName, RuntimeEventFrame
from infrastructure.godot.native_body import NativeBody
from infrastructure.godot.nest_session import GodotNestSessionAdapter
from infrastructure.godot.nest_session.ports import BodyEventSink
from infrastructure.godot.runner import find_godot, forward_output, run_import
from infrastructure.models.model_execution_adapter import (
    SerializedModelExecutionAdapter,
    StructuredModelExecution,
)
from infrastructure.models.model_execution_contracts import (
    StructuredModelExecutionRequest,
    StructuredModelExecutionResult,
)
from infrastructure.persistence.configuration.bundled_defaults import (
    load_energy_defaults,
    load_nest_config,
    load_reasoning_constitution,
)
from infrastructure.persistence.configuration.species import (
    load_and_configure_species_catalog,
)
from infrastructure.persistence.food import SQLiteFoodAdapter
from infrastructure.persistence.food_evidence import record_model_evidence
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from infrastructure.persistence.nest_db.store import init_db


class RecordingStructuredExecution:
    """Record exact model-boundary input/output while delegating to production."""

    def __init__(self, raw: StructuredModelExecution) -> None:
        self._raw = raw
        self.requests: list[dict[str, Any]] = []
        self.results: list[dict[str, Any]] = []
        self.errors: list[dict[str, str]] = []

    @property
    def tool_port(self) -> Any:
        return getattr(self._raw, "tool_port", None)

    def structured_capabilities(
        self,
        food_key: str | None = None,
        food_unavailable: bool = False,
    ) -> Any:
        return self._raw.structured_capabilities(food_key, food_unavailable)

    def generate_structured(
        self,
        request: StructuredModelExecutionRequest,
    ) -> StructuredModelExecutionResult:
        self.requests.append(request.model_dump(mode="json"))
        try:
            result = self._raw.generate_structured(request)
        except Exception as error:  # noqa: BLE001 - preserve provider evidence
            self.errors.append({"type": type(error).__name__, "message": str(error)})
            raise
        self.results.append(result.model_dump(mode="json"))
        return result


class RecordingGateway:
    """Record wire commands/events without changing the Gateway implementation."""

    def __init__(self, raw: GodotAPIServer) -> None:
        self.raw = raw
        self.commands: list[dict[str, Any]] = []
        self.body_commands: list[dict[str, Any]] = []
        self.runtime_events: list[dict[str, Any]] = []

    @property
    def runtime_connection(self) -> Any:
        return self.raw.runtime_connection

    @property
    def runtime_ready(self) -> bool:
        return self.raw.runtime_ready

    def start(self) -> None:
        self.raw.start()

    def stop(self) -> None:
        self.raw.stop()

    def send_runtime_command(
        self,
        name: CommandName,
        payload: Mapping[str, Any],
        *,
        world_revision: int,
        cause_id: str | None = None,
    ) -> str | None:
        self.commands.append(
            {
                "name": name.value,
                "payload": dict(payload),
                "world_revision": world_revision,
                "cause_id": cause_id,
            }
        )
        return self.raw.send_runtime_command(
            name,
            dict(payload),
            world_revision=world_revision,
            cause_id=cause_id,
        )

    def drain_runtime_events(self) -> tuple[RuntimeEventFrame, ...]:
        events = self.raw.drain_runtime_events()
        self.runtime_events.extend(event.model_dump(mode="json") for event in events)
        return events

    def mark_world_configured(self, connection: Any, *, world_revision: int) -> None:
        self.raw.mark_world_configured(connection, world_revision=world_revision)

    def register_body_sink(self, actor_id: str, sink: BodyEventSink) -> None:
        self.raw.register_body_sink(actor_id, sink)

    def unregister_body_sink(self, actor_id: str, sink: BodyEventSink) -> None:
        self.raw.unregister_body_sink(actor_id, sink)

    def send_body_command(
        self,
        payload: RuntimeIntentPayload,
        *,
        cause_id: str,
    ) -> bool:
        item = {
            "name": "execute_intent",
            "payload": dict(payload),
            "cause_id": cause_id,
        }
        self.body_commands.append(item)
        return self.raw.send_body_command(payload, cause_id=cause_id)

    def cancel_body_command(self, *, command_id: str, actor_id: str) -> bool:
        self.commands.append(
            {
                "name": "cancel_intent",
                "payload": {"command_id": command_id, "actor_id": actor_id},
                "cause_id": command_id,
            }
        )
        return self.raw.cancel_body_command(command_id=command_id, actor_id=actor_id)


def _brain_trace(elfie: Elfie) -> dict[str, Any]:
    """Capture public Brain outcomes plus the last deterministic rejection."""
    outcomes = elfie.turn_outcomes()
    reasoning: dict[str, Any] = {}
    decisions: dict[str, Any] = {}
    for outcome in outcomes:
        turn_id = str(outcome.turn_id)
        reasoning[turn_id] = _dump(elfie.turn_reasoning(outcome.turn_id))
        decisions[turn_id] = _dump(elfie.turn_decision(outcome.turn_id))
    runtime = getattr(elfie, "_brain_runtime", None)
    router = getattr(runtime, "router", None)
    return {
        "turn_outcomes": _dump(outcomes),
        "turn_reasoning": reasoning,
        "turn_decisions": decisions,
        "router_last_rejection": _dump(getattr(router, "last_rejection", None)),
    }


def _copy_isolated_home(source_home: Path) -> Path:
    isolated = Path(
        tempfile.mkdtemp(
            prefix="elfienest-brain-godot-e2e-",
            dir="/private/tmp",
        )
    )
    (isolated / "configs").mkdir(parents=True)
    (isolated / "reports").mkdir(parents=True)
    for relative in ("configs/providers.yaml", "configs/auth.env"):
        source = source_home / relative
        if source.is_file():
            target = isolated / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    init_db(str(isolated / "nest.db"))
    food = SQLiteFoodAdapter(isolated / "nest.db")
    common = food.get_package("food_common")
    if common is None:
        raise RuntimeError("fresh isolated database has no food_common package")
    food.update_package(
        replace(
            common,
            enabled=True,
            primary_model="volcengine_coding_plan_0001/deepseek-v4-flash",
        )
    )
    return isolated


def _seed_isolated_model_readiness(db_path: Path) -> None:
    """Permit the live call without copying the user's report database."""
    record_model_evidence(
        (
            StoredModelEvidence(
                reference="volcengine_coding_plan_0001/deepseek-v4-flash",
                display_name="E2E configured model",
                capabilities=frozenset({"text"}),
                verified=True,
                observed_at=datetime.now(timezone.utc).isoformat(),
            ),
        ),
        repository=build_report_repository(str(db_path)),
        scope="diagnostic:brain-godot-e2e",
        trigger="isolated_live_call",
    )


def _dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, (tuple, list)):
        return [_dump(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _dump(item) for key, item in value.items()}
    return value


def _free_socket() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    return sock


def _wait_until(
    predicate: Callable[[], bool],
    *,
    timeout: float,
    description: str,
    pump: Callable[[], None] | None = None,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        if pump is not None:
            pump()
        time.sleep(0.05)
    raise TimeoutError(f"timed out waiting for {description}")


def _make_elfie(
    body: Any,
    *,
    actor_id: str,
    display_name: str,
    seed: int,
) -> Elfie:
    load_and_configure_species_catalog()
    from elfie.profile import create_visual_profile

    profile = create_visual_profile(
        elfie_id=actor_id,
        display_name=display_name,
        species_id="fox",
        seed=seed,
    )
    selfhood_seed = {
        "state_schema_version": 1,
        "revision": 1,
        "committed_at": datetime.fromtimestamp(0, timezone.utc),
        "identity_core": {
            "elfie_id": actor_id,
            "display_name": display_name,
            "species_id": "fox",
            "species_name": "小狐狸",
            "resident_role": "resident",
        },
        "adaptive_self": {
            "big_five": {
                "openness": 0.8,
                "conscientiousness": 0.7,
                "extraversion": 0.6,
                "agreeableness": 0.8,
                "neuroticism": 0.3,
            },
            "interaction_tendency_ids": ("curious",),
            "coping_tendency_ids": ("careful",),
            "expression_tendency_ids": ("warm",),
            "value_ids": ("honest",),
            "speech_marker_ids": ("哒",),
            "source_event_ids": (),
        },
    }
    return ElfieFactory().assemble(
        ElfieAssembly(
            profile=profile,
            memory_store=SQLiteMemoryStoreAdapter.in_memory(elfie_id=actor_id),
            selfhood_seed=selfhood_seed,
            reasoning_constitution=ReasoningConstitution.from_mapping(
                load_reasoning_constitution()
            ),
            energy_limits=load_energy_defaults(),
            emotion_expression_config=load_emotion_expression_config(),
            emotion_dynamics_config=load_emotion_dynamics_config(),
            body=body,
        )
    )


def _make_native_body(
    gateway: RecordingGateway,
    engine: ElfieNestEngine,
    actor_id: str,
) -> NativeBody:
    """Build one production Godot Body adapter for the live diagnostic."""
    transport = GodotTransport(
        gateway,
        actor_id=actor_id,
        speech_intent=cast(
            Callable[[RuntimeIntentPayload], bool],
            engine.session.prepare_speech,
        ),
        semantic_action=cast(
            Callable[[RuntimeIntentPayload], Optional[str]],
            engine.session.prepare_semantic_action,
        ),
        semantic_action_result=cast(
            Callable[[RuntimeIntentPayload, RuntimeIntentResult], None],
            engine.session.complete_semantic_action,
        ),
        visual_observation=cast(
            Callable[[RuntimeIntentPayload], bool],
            engine.session.prepare_visual_observation,
        ),
    )
    return NativeBody(body_id=actor_id, transport=transport)


def _record_body_input_reads(
    body: NativeBody,
    actor_id: str,
    sink: dict[str, list[dict[str, Any]]],
) -> None:
    """Record events only when the Body actually hands them to NervousSystem."""
    original_read = body.read_sensor_events

    def read_sensor_events() -> list[BodySensorEvent]:
        events = original_read()
        sink[actor_id].extend(_dump(events))
        return events

    body.read_sensor_events = read_sensor_events  # type: ignore[method-assign]


def _record_body_action_outcomes(
    elfie: Elfie,
    actor_id: str,
    sink: list[dict[str, Any]],
) -> None:
    """Record terminal action facts at the NS->Workspace ingress."""
    nervous_system = elfie._nervous_system
    original_receive = nervous_system.receive_body_event

    def receive_body_event(event: BodySensorEvent) -> Any:
        if isinstance(event.payload, ActionOutcomePayload):
            sink.append({"actor_id": actor_id, "event": _dump(event)})
        return original_receive(event)

    nervous_system.receive_body_event = receive_body_event  # type: ignore[method-assign]


def _stop_process(process: subprocess.Popen[str] | None) -> str:
    if process is None:
        return "not_started"
    if process.poll() is not None:
        return f"exited:{process.returncode}"
    process.terminate()
    try:
        process.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5.0)
        return "killed_owned_process"
    return "terminated_owned_process"


def _contains_action_feedback(value: Any) -> bool:
    """Match the normalized embodied action fact sent to the model."""
    rendered = str(value)
    return "action_outcome" in rendered or (
        "physical:proprioception" in rendered
        and "action=" in rendered
        and "status=completed" in rendered
    )


def run(timeout: float, post_verify_seconds: float) -> tuple[int, dict[str, Any]]:
    source_home = Path(os.environ.get("ELFIE_HOME", str(Path.home() / ".elfienest")))
    isolated_home = _copy_isolated_home(source_home)
    os.environ["ELFIE_HOME"] = str(isolated_home)
    _seed_isolated_model_readiness(isolated_home / "nest.db")
    evidence_dir = PROJECT_ROOT / "build" / "e2e" / "brain-godot-live"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    initial_screenshot = evidence_dir / "initial.png"
    final_screenshot = evidence_dir / "final.png"
    godot_report = evidence_dir / "godot-report.json"
    godot_log_path = evidence_dir / "godot-console.log"
    evidence_path = evidence_dir / "evidence.json"

    server_socket = _free_socket()
    ws_port = int(server_socket.getsockname()[1])
    nonce = f"e2e-{uuid.uuid4().hex}"
    server = GodotAPIServer(
        host="127.0.0.1",
        port=ws_port,
        http_port=0,
        handshake_nonce=nonce,
        prebound_socket=server_socket,
    )
    gateway = RecordingGateway(server)
    world_runtime = GodotNestSessionAdapter(gateway=gateway)
    engine = ElfieNestEngine(
        world_runtime,
        tick_interval_sec=0.05,
        state_store=None,
        nest_config=load_nest_config(),
    )
    services = build_model_execution_services(
        str(isolated_home / "nest.db"),
        live_reload=False,
        resolve_main_food=False,
    )
    recorder = RecordingStructuredExecution(services.execution)
    godot_process: subprocess.Popen[str] | None = None
    primary_actor_id = "90000001"
    listener_actor_id = "90000002"
    body_events_by_actor: dict[str, list[dict[str, Any]]] = {
        primary_actor_id: [],
        listener_actor_id: [],
    }
    body_input_events_by_actor: dict[str, list[dict[str, Any]]] = {
        primary_actor_id: [],
        listener_actor_id: [],
    }
    body_action_outcomes: list[dict[str, Any]] = []
    bodies_by_actor: dict[str, NativeBody] = {}
    elfies_by_actor: dict[str, Elfie] = {}
    body_event_handlers: dict[str, Callable[[RuntimeEventFrame], None]] = {}
    action_executor: ThreadPoolExecutor | None = None
    speech_future: Any = None
    visual_future: Any = None
    speech_result: Any = None
    visual_result: Any = None
    speech_command: SpeechCommand | None = None
    visual_command: ObservationCommand | None = None
    sensory_checks: dict[str, bool] = {}
    body_events = body_events_by_actor[primary_actor_id]
    setup_events: list[str] = []
    trigger_receipts: Any = ()
    elfie: Elfie | None = None
    cleanup: dict[str, Any] = {}
    result: dict[str, Any] = {
        "status": "failed",
        "source_home": str(source_home),
        "isolated_home": str(isolated_home),
        "evidence_dir": str(evidence_dir),
        "gateway": {"ws_port": ws_port},
    }
    try:
        godot_binary = find_godot()
        if godot_binary is None:
            raise RuntimeError("Godot 4 executable was not found")
        import_result = run_import(
            godot_binary,
            PROJECT_ROOT / "godot_project",
            purpose="brain-godot-e2e-project-import",
        )
        forward_output(import_result)
        if import_result.exit_code != 0:
            raise RuntimeError(
                "Godot project import failed before the live Brain-Godot round"
            )
        gateway.start()
        godot_env = os.environ.copy()
        godot_env.update(
            {
                "ELFIENEST_GODOT_MODE": "authority",
                "ELFIENEST_GODOT_SHOW_VISUALS": "1",
                "ELFIENEST_GODOT_WS": f"ws://127.0.0.1:{ws_port}",
                "ELFIENEST_GODOT_NONCE": nonce,
                "ELFIENEST_E2E_CAMERA_VIEW": "区域俯视 01-04",
                "ELFIENEST_E2E_INITIAL_SCREENSHOT": str(initial_screenshot),
                "ELFIENEST_E2E_FINAL_SCREENSHOT": str(final_screenshot),
                "ELFIENEST_E2E_GODOT_REPORT": str(godot_report),
                "ELFIENEST_E2E_ACTOR_ID": primary_actor_id,
                "ELFIENEST_E2E_GODOT_TIMEOUT_SECONDS": str(timeout),
                "ELFIENEST_E2E_POST_VERIFY_SECONDS": str(post_verify_seconds),
            }
        )
        godot_log = godot_log_path.open("w", encoding="utf-8")
        godot_process = subprocess.Popen(
            [
                str(godot_binary),
                "--path",
                str(PROJECT_ROOT / "godot_project"),
                "--script",
                "res://scripts/test/test_live_embodied_e2e.gd",
            ],
            cwd=str(PROJECT_ROOT / "godot_project"),
            env=godot_env,
            stdout=godot_log,
            stderr=subprocess.STDOUT,
            text=True,
        )

        def tick() -> None:
            if godot_process is not None and godot_process.poll() is not None:
                if godot_process.returncode != 0:
                    raise RuntimeError(
                        f"Godot exited during E2E with code {godot_process.returncode}"
                    )
                if not godot_report.is_file():
                    raise RuntimeError(
                        "Godot exited cleanly before writing the E2E report"
                    )
            engine.tick_once(0.05)

        _wait_until(
            lambda: engine.session.runtime_world_ready,
            timeout=timeout,
            description="Godot semantic world readiness",
            pump=tick,
        )
        runtime_world_ready_at_setup = engine.session.runtime_world_ready
        world_capabilities_at_setup = engine.session.world_capabilities()
        setup_events.extend(
            event["name"]
            for event in gateway.runtime_events
            if isinstance(event.get("name"), str)
        )

        # Use the same production Body wiring as a live Elfie, but keep its
        # Brain persistence in memory for a deterministic isolated run.
        for actor_id, display_name, seed in (
            (primary_actor_id, "E2E Primary Elfie", 91001),
            (listener_actor_id, "E2E Listener Elfie", 91002),
        ):
            body = _make_native_body(gateway, engine, actor_id)
            bodies_by_actor[actor_id] = body
            _record_body_input_reads(body, actor_id, body_input_events_by_actor)

            def body_event_handler(
                event: RuntimeEventFrame,
                actor_id: str = actor_id,
            ) -> None:
                body_events_by_actor[actor_id].append(event.model_dump(mode="json"))

            body_event_handlers[actor_id] = body_event_handler
            body.transport.connect(body_event_handler)
            elfie_instance = _make_elfie(
                body,
                actor_id=actor_id,
                display_name=display_name,
                seed=seed,
            )
            elfies_by_actor[actor_id] = elfie_instance
            engine.session.register_elfie(actor_id, elfie_instance)
            if not body.connected:
                body.connect()
            _record_body_action_outcomes(
                elfie_instance,
                actor_id,
                body_action_outcomes,
            )

        actor_id = primary_actor_id
        body = bodies_by_actor[primary_actor_id]
        elfie = elfies_by_actor[primary_actor_id]

        # Synchronize the actor into Godot before cognition starts. The setup
        # snapshot is recorded and deliberately not treated as the trigger.
        engine.session.flush_runtime_state()

        def drain_setup_events() -> None:
            gateway.drain_runtime_events()
            time.sleep(0.05)

        _wait_until(
            lambda: any(
                event.get("name") == "world_snapshot"
                for event in gateway.runtime_events
            ),
            timeout=10.0,
            description="Godot actor synchronization snapshot",
            pump=drain_setup_events,
        )
        setup_snapshot_count = sum(
            event.get("name") == "world_snapshot" for event in gateway.runtime_events
        )

        _wait_until(
            lambda: initial_screenshot.is_file(),
            timeout=10.0,
            description="Godot rendered initial room screenshot",
            pump=drain_setup_events,
        )

        engine.session.configure_cognition_factory(
            lambda _actor_id: SerializedModelExecutionAdapter(
                recorder,
                scope_id=_actor_id,
            )
        )
        engine.session.start_elfies()
        brain_runtime = getattr(elfie, "_brain_runtime", None)
        embodied_input_mode = str(
            getattr(getattr(brain_runtime, "embodied_input_mode", None), "value", "")
        )
        requested_target = "facility/activity-01/activity"
        trigger_at = elfie.cognitive_datetime
        trigger = BodySensorEvent(
            event_id=EventId("e2e-trigger-1"),
            body_id=BodyId(actor_id),
            body_generation=elfie.current_body_generation or 1,
            source=ActorRef(
                actor_id=ActorId("e2e-harness"),
                source_kind="e2e_harness",
            ),
            occurred_at=trigger_at,
            received_at=trigger_at,
            payload=UtteranceFinal(
                kind="utterance_final",
                text=(
                    "E2E acceptance request: execute one movement now using the "
                    "registered move.to capability; move to "
                    f"{requested_target}; do not answer with prose."
                ),
            ),
        )
        trigger_receipts = elfie.pump_body_events((trigger,))
        # The normal policy admits this non-critical embodied event after the
        # oldest-event window.  Advance the production cognitive clock so the
        # diagnostic does not depend on wall-clock scheduling before the first
        # turn is admitted.
        elfie.advance_clock(5.0)

        def has_completed_action() -> bool:
            return any(
                event.get("name") == "intent_terminal"
                and event.get("payload", {}).get("status") == "completed"
                for event in body_events
            )

        def has_followup_model_turn() -> bool:
            if len(recorder.requests) < 2 or len(recorder.results) < 2:
                return False
            return any(
                _contains_action_feedback(request.get("prompt", ""))
                or _contains_action_feedback(request.get("messages", ""))
                for request in recorder.requests[1:]
            )

        def has_godot_movement_report() -> bool:
            if not godot_report.is_file():
                return False
            try:
                report = json.loads(godot_report.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return False
            return report.get("status") == "passed"

        def has_expected_brain_progress() -> bool:
            if not has_completed_action() or not has_godot_movement_report():
                return False
            if embodied_input_mode == "mock":
                return not recorder.requests
            return has_followup_model_turn()

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            tick()
            if has_expected_brain_progress():
                break
            time.sleep(0.05)
        else:
            raise TimeoutError(
                "timed out waiting for completed Godot action and expected Brain progress"
            )

        if embodied_input_mode != "mock":
            _wait_until(
                lambda: len(elfie.turn_outcomes()) >= 2,
                timeout=10.0,
                description="follow-up Brain outcome",
                pump=tick,
            )

        def body_inputs(actor: str) -> list[dict[str, Any]]:
            return body_input_events_by_actor[actor]

        def has_body_input(
            actor: str,
            kind: str,
            predicate: Callable[[dict[str, Any]], bool] | None = None,
        ) -> bool:
            for event in body_inputs(actor):
                payload = event.get("payload", {})
                if payload.get("kind") != kind:
                    continue
                if predicate is None or predicate(payload):
                    return True
            return False

        def has_action_outcome(command_id: str) -> bool:
            return any(
                item.get("event", {}).get("payload", {}).get("command_id") == command_id
                and item.get("event", {}).get("payload", {}).get("status")
                == "completed"
                for item in body_action_outcomes
            )

        # Drive the remaining sensory links through the same production
        # NervousSystem -> Body path.  The worker waits for one terminal result,
        # while the main diagnostic thread keeps polling the real Godot socket.
        speech_now = elfie.cognitive_datetime
        speech_command = SpeechCommand(
            command_type="speech",
            command_id=CommandId("e2e-speech-1"),
            turn_id=TurnId("e2e-sensory-turn"),
            intent_id=IntentId("e2e-speech-intent"),
            body_id=BodyId(primary_actor_id),
            issued_at=speech_now,
            deadline=speech_now + timedelta(seconds=20),
            capability_revision=body.capabilities.revision,
            body_generation=elfie.current_body_generation or 1,
            text="E2E hearing and semantic-world verification.",
        )
        action_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="brain-godot-e2e-action",
        )
        speech_future = action_executor.submit(
            elfie._nervous_system.execute_body_command,
            body,
            speech_command,
            now=speech_now,
        )
        sensory_deadline = time.monotonic() + timeout
        while time.monotonic() < sensory_deadline:
            tick()
            if speech_future.done() and visual_future is None:
                speech_result = speech_future.result()
                if not speech_result or speech_result[-1].status.value != "completed":
                    raise RuntimeError(
                        f"Godot speech command did not complete: {_dump(speech_result)}"
                    )
                visual_now = elfie.cognitive_datetime
                visual_command = ObservationCommand(
                    command_type="observation",
                    command_id=CommandId("e2e-visual-1"),
                    turn_id=TurnId("e2e-sensory-turn"),
                    intent_id=IntentId("e2e-visual-intent"),
                    body_id=BodyId(primary_actor_id),
                    issued_at=visual_now,
                    deadline=visual_now + timedelta(seconds=10),
                    capability_revision=body.capabilities.revision,
                    body_generation=elfie.current_body_generation or 1,
                    observation_id="e2e-observation-1",
                    max_results=16,
                )
                visual_future = action_executor.submit(
                    elfie._nervous_system.execute_body_command,
                    body,
                    visual_command,
                    now=visual_now,
                )
            if visual_future is not None and visual_future.done():
                visual_result = visual_future.result()
                if not visual_result or visual_result[-1].status.value != "completed":
                    raise RuntimeError(
                        "Godot visual observation request did not complete: "
                        f"{_dump(visual_result)}"
                    )
            sensory_checks = {
                "speech_reach": any(
                    event.get("name") == "speech_reach"
                    and event.get("payload", {}).get("command_id")
                    == str(speech_command.command_id)
                    and listener_actor_id
                    in event.get("payload", {}).get("audience_actor_ids", [])
                    for event in gateway.runtime_events
                ),
                "hearing": has_body_input(
                    listener_actor_id,
                    "heard_utterance",
                    lambda payload: (
                        payload.get("sender_id") == primary_actor_id
                        and payload.get("text") == speech_command.text
                    ),
                ),
                "vision_request": any(
                    event.get("name") == "visual_observation"
                    and event.get("payload", {}).get("observation_id")
                    == "e2e-observation-1"
                    for event in gateway.runtime_events
                ),
                "vision": has_body_input(
                    primary_actor_id,
                    "semantic_visual_scene",
                    lambda payload: (
                        payload.get("observation_id") == "e2e-observation-1"
                    ),
                ),
                "touch": has_body_input(primary_actor_id, "tactile_impact"),
                "proprioception": has_body_input(
                    primary_actor_id,
                    "proprioception_sample",
                    lambda payload: (
                        isinstance(payload.get("position"), list)
                        and len(payload["position"]) == 3
                    ),
                ),
                "speech_action_outcome": has_action_outcome(
                    str(speech_command.command_id)
                ),
                "visual_action_outcome": (
                    visual_command is not None
                    and has_action_outcome(str(visual_command.command_id))
                ),
            }
            if all(sensory_checks.values()):
                break
            time.sleep(0.05)
        else:
            raise TimeoutError(
                "timed out waiting for real Godot hearing, vision, touch, "
                "proprioception, and terminal action feedback"
            )

        time.sleep(0.2)
        godot_report_data: Any = None
        if godot_report.is_file():
            godot_report_data = json.loads(godot_report.read_text(encoding="utf-8"))
        terminal_commands = [
            event.get("payload", {}).get("command_id")
            for event in body_events
            if event.get("name") == "intent_terminal"
        ]
        actual_targets = [
            command.get("payload", {}).get("anchor_id")
            for command in gateway.body_commands
            if command.get("payload", {}).get("anchor_id")
        ]
        outcomes = elfie.turn_outcomes()
        brain_trace = _brain_trace(elfie)
        receipt_dump: dict[str, Any] = {}
        for outcome in outcomes:
            receipt_dump[str(outcome.turn_id)] = _dump(
                elfie.execution_receipts(outcome.turn_id)
            )
        action_outcome_requests = [
            request
            for request in recorder.requests
            if _contains_action_feedback(request.get("prompt", ""))
            or _contains_action_feedback(request.get("messages", ""))
        ]
        workspace_metrics = _dump(elfie._workspace.metrics())
        acceptance_passed = bool(
            godot_report_data
            and godot_report_data.get("status") == "passed"
            and has_expected_brain_progress()
            and all(sensory_checks.values())
        )
        result.update(
            {
                "status": "passed" if acceptance_passed else "failed",
                "actor_id": actor_id,
                "listener_actor_id": listener_actor_id,
                "requested_target": requested_target,
                "actual_targets": actual_targets,
                "runtime_world_ready": runtime_world_ready_at_setup,
                "world_capabilities": world_capabilities_at_setup,
                "runtime_world_ready_at_finish": engine.session.runtime_world_ready,
                "world_capabilities_at_finish": engine.session.world_capabilities(),
                "body_connected": body.connected,
                "embodied_input_mode": embodied_input_mode,
                "trigger": _dump(trigger),
                "trigger_receipts": _dump(trigger_receipts),
                "sensory_commands": {
                    "speech": _dump(speech_command),
                    "visual": _dump(visual_command),
                },
                "sensory_command_results": {
                    "speech": _dump(speech_result),
                    "visual": _dump(visual_result),
                },
                "model_requests": recorder.requests,
                "model_results": recorder.results,
                "model_errors": recorder.errors,
                "runtime_commands": gateway.commands,
                "body_commands": gateway.body_commands,
                "body_events": body_events,
                "body_events_by_actor": body_events_by_actor,
                "body_input_events_by_actor": body_input_events_by_actor,
                "body_action_outcomes": body_action_outcomes,
                "sensory_checks": sensory_checks,
                "workspace_metrics": workspace_metrics,
                "godot_report": godot_report_data,
                "nest_lane_events": gateway.runtime_events,
                "setup_events": setup_events,
                "setup_snapshot_count": setup_snapshot_count,
                "terminal_command_ids": terminal_commands,
                "action_outcome_model_requests": action_outcome_requests,
                "turn_outcomes": _dump(outcomes),
                "brain_trace": brain_trace,
                "execution_receipts": receipt_dump,
                "screenshots": {
                    "initial": str(initial_screenshot),
                    "final": str(final_screenshot),
                },
            }
        )
        if result["status"] != "passed":
            raise RuntimeError(
                f"Godot movement report was not passed: {godot_report_data}"
            )
        return 0, result
    except Exception as error:  # noqa: BLE001 - emit complete acceptance evidence
        brain_debug: dict[str, Any] = {}
        if elfie is not None:
            brain_debug.update(
                {
                    "is_running": elfie.is_running,
                    "cognition_configured": elfie.cognition_configured,
                    "elapsed_time": elfie.elapsed_time,
                }
            )
            try:
                brain_debug["workspace_metrics"] = _dump(elfie._workspace.metrics())
                brain_debug["workspace_pending_writes"] = _dump(
                    elfie._workspace._storage.pending_writes()
                )
            except Exception as debug_error:  # noqa: BLE001
                brain_debug["workspace_metrics_error"] = (
                    f"{type(debug_error).__name__}:{debug_error}"
                )
            try:
                brain_debug["logical_clock_enabled"] = bool(
                    getattr(elfie._nervous_system, "_logical_clock", None)
                )
            except Exception as debug_error:  # noqa: BLE001
                brain_debug["logical_clock_error"] = (
                    f"{type(debug_error).__name__}:{debug_error}"
                )
            try:
                brain_debug["turn_outcomes"] = _dump(elfie.turn_outcomes())
            except Exception as debug_error:  # noqa: BLE001
                brain_debug["turn_outcomes_error"] = (
                    f"{type(debug_error).__name__}:{debug_error}"
                )
            try:
                brain_debug.update(_brain_trace(elfie))
            except Exception as debug_error:  # noqa: BLE001
                brain_debug["trace_error"] = (
                    f"{type(debug_error).__name__}:{debug_error}"
                )
            runtime = getattr(elfie, "_brain_runtime", None)
            coordinator = getattr(runtime, "coordinator", None)
            if coordinator is not None:
                brain_debug["coordinator_alive"] = coordinator.is_alive
                coordinator_runtime = getattr(coordinator, "_runtime", None)
                if coordinator_runtime is not None:
                    brain_debug["dropped_control_count"] = (
                        coordinator_runtime.dropped_control_count
                    )
        result.update(
            {
                "status": "failed",
                "error": {"type": type(error).__name__, "message": str(error)},
                "model_requests": recorder.requests,
                "model_results": recorder.results,
                "model_errors": recorder.errors,
                "runtime_commands": gateway.commands,
                "body_commands": gateway.body_commands,
                "body_events": body_events,
                "body_events_by_actor": body_events_by_actor,
                "body_input_events_by_actor": body_input_events_by_actor,
                "body_action_outcomes": body_action_outcomes,
                "sensory_checks": sensory_checks,
                "embodied_input_mode": (
                    str(
                        getattr(
                            getattr(
                                getattr(elfie, "_brain_runtime", None),
                                "embodied_input_mode",
                                None,
                            ),
                            "value",
                            "",
                        )
                    )
                    if elfie is not None
                    else ""
                ),
                "godot_report": (
                    json.loads(godot_report.read_text(encoding="utf-8"))
                    if godot_report.is_file()
                    else None
                ),
                "nest_lane_events": gateway.runtime_events,
                "trigger_receipts": _dump(trigger_receipts),
                "brain_debug": brain_debug,
            }
        )
        return 1, result
    finally:
        for actor_id, body_instance in bodies_by_actor.items():
            try:
                body_instance.transport.interrupt_pending("e2e cleanup")
                handler = body_event_handlers.get(actor_id)
                if handler is not None:
                    body_instance.transport.disconnect(handler)
                body_instance.disconnect()
            except Exception as error:  # noqa: BLE001
                cleanup[f"body:{actor_id}"] = (
                    f"cleanup_error:{type(error).__name__}:{error}"
                )
        if action_executor is not None:
            try:
                action_executor.shutdown(wait=True, cancel_futures=True)
                cleanup["action_executor"] = "stopped"
            except Exception as error:  # noqa: BLE001
                cleanup["action_executor"] = (
                    f"cleanup_error:{type(error).__name__}:{error}"
                )
        if elfie is not None:
            try:
                engine.session.stop_elfies()
                engine.session.join_elfies()
                cleanup["elfies"] = "stopped"
            except Exception as error:  # noqa: BLE001
                cleanup["elfies"] = f"cleanup_error:{type(error).__name__}:{error}"
        cleanup["godot_process"] = _stop_process(godot_process)
        try:
            gateway.stop()
            cleanup["gateway"] = "stopped"
        except Exception as error:  # noqa: BLE001
            cleanup["gateway"] = f"cleanup_error:{type(error).__name__}:{error}"
        try:
            server_socket.close()
        except OSError:
            pass
        result["cleanup"] = cleanup
        evidence_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--post-verify-seconds", type=float, default=30.0)
    args = parser.parse_args()
    code, result = run(args.timeout, args.post_verify_seconds)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str), flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
