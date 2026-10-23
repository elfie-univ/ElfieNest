"""Real Gateway/NativeBody acceptance against a separately started main.tscn.

The registered Elfies are identity-only MagicMock fixtures, not real Brain or
Provider instances. No production ELFIE_HOME or persistent state store is used.
Connect Godot with ELFIENEST_GODOT_WS, ELFIENEST_GODOT_NONCE and
ELFIENEST_GODOT_MODE=authority after nest_e2e_ready is printed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path
from threading import Event, Thread
from typing import List, TypeVar, cast
from unittest.mock import MagicMock

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, PROJECT_ROOT)

from app.orchestration.nest_session import ElfieNestEngine
from elfie import Elfie
from elfie.body import BodyId, CapabilityCommand, CommandStatus
from elfie.message_types import CommandId, IntentId, TurnId
from elfie.profile import ElfieProfile, create_visual_profile
from infrastructure.godot.body_transport import GodotTransport, RuntimeIntentPayload
from infrastructure.godot.gateway.api import GodotAPIServer
from infrastructure.godot.gateway.messages import (
    EventName,
    RuntimeEventFrame,
)
from infrastructure.godot.native_body import NativeBody
from infrastructure.godot.nest_session import GodotNestSessionAdapter
from infrastructure.godot.nest_session.mapper import (
    map_runtime_event,
    parse_scene_manifest,
    parse_world_snapshot,
)
from infrastructure.persistence.configuration.species import (
    load_and_configure_species_catalog,
)
from nest.public import NestConfig

_Result = TypeVar("_Result")


@dataclass
class _ObserverRecording:
    """Optional fixture-only output of the existing geometry-free App projection."""

    path: Path
    sequence: int = 0
    _last_state: str = ""
    pending_events: List[RuntimeEventFrame] = field(default_factory=list)

    def capture(
        self, engine: ElfieNestEngine, server: GodotAPIServer, status: str = "running"
    ) -> None:
        connection = server.runtime_connection
        if connection is None or server.runtime_world_revision is None:
            return
        projected = engine.session.observer_semantic_entities()
        entities = {
            entity_id: entity.model_dump(mode="json")
            for entity_id, entity in projected.items()
        }
        state = json.dumps(
            {
                "status": status,
                "generation": connection.generation,
                "entities": entities,
            },
            sort_keys=True,
        )
        if state == self._last_state:
            return
        self._last_state = state
        self.sequence += 1
        room_id = (
            next(iter(projected.values())).room_id
            if projected
            else engine.nest.config.nest_id
        )
        envelope = {
            "status": status,
            "identity_fixture": "identity_only_magicmock_no_brain_or_provider",
            "world_config": {
                "channel": "elfienest.observer",
                "version": 1,
                "kind": "world_config",
                "nest_id": room_id,
                "bed_count": engine.nest.config.bed_count,
            },
            "snapshot": {
                "channel": "elfienest.observer",
                "version": 1,
                "kind": "semantic_snapshot",
                "protocol": 3,
                "generation": connection.generation,
                "sequence": self.sequence,
                "scope": {"kind": "room", "room_id": room_id},
                "entities": entities,
                "entity_revisions": dict.fromkeys(entities, self.sequence),
            },
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        pending = self.path.with_name(self.path.name + ".tmp")
        pending.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
        pending.replace(self.path)


def _profile(elfie_id: str, species: str, seed: int) -> ElfieProfile:
    return create_visual_profile(
        elfie_id=elfie_id,
        display_name=elfie_id,
        species_id=species,
        seed=seed,
        catalog=load_and_configure_species_catalog(),
        appearance_overrides={
            "macro": {
                "stature_z": 0.0,
                "frame_size_z": 0.0,
                "body_fat_z": 0.0,
                "muscularity_z": 0.0,
            }
        },
    )


def _elfie(elfie_id: str, species: str, seed: int) -> Elfie:
    """Register identity/appearance only; this scenario never executes a Brain."""
    elfie = MagicMock(spec=Elfie)
    elfie.profile = _profile(elfie_id, species, seed)
    return elfie


def _pump(
    engine: ElfieNestEngine,
    server: GodotAPIServer,
    recording: _ObserverRecording | None = None,
) -> List[RuntimeEventFrame]:
    engine.session.poll_runtime_connection()
    events = list(server.drain_runtime_events())
    for event in events:
        engine.session.consume_runtime_event(map_runtime_event(event))
    engine.session.flush_runtime_state()
    if recording is not None:
        recording.capture(engine, server)
    return events


def _run_action(
    engine: ElfieNestEngine,
    server: GodotAPIServer,
    recording: _ObserverRecording | None,
    invoke: Callable[[], _Result],
) -> _Result:
    # Production cognition and the Nest poller are independently scheduled. In
    # this fixture, keep one owner pumping Nest while a blocking Body call runs.
    if recording is None:
        return invoke()
    values: List[_Result] = []
    errors: List[BaseException] = []

    def execute() -> None:
        try:
            values.append(invoke())
        except BaseException as error:
            errors.append(error)

    worker = Thread(target=execute, daemon=True)
    worker.start()
    while worker.is_alive():
        recording.pending_events.extend(_pump(engine, server, recording))
        time.sleep(0.02)
    worker.join()
    recording.pending_events.extend(_pump(engine, server, recording))
    if errors:
        raise errors[0]
    if not values:
        raise RuntimeError("Body acceptance returned no result")
    return values[0]


def _wait_for(
    engine: ElfieNestEngine,
    server: GodotAPIServer,
    predicate: Callable[[List[RuntimeEventFrame]], bool],
    *,
    timeout: float,
    recording: _ObserverRecording | None = None,
) -> List[RuntimeEventFrame]:
    observed: List[RuntimeEventFrame] = []
    if recording is not None:
        observed.extend(recording.pending_events)
        recording.pending_events.clear()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = _pump(engine, server, recording)
        observed.extend(current)
        for event in current:
            if event.name is EventName.STARTUP_ERROR:
                raise RuntimeError(f"runtime startup failed: {event.payload['code']}")
        if predicate(observed):
            return observed
        time.sleep(0.02)
    names = [event.name.value for event in observed]
    raise RuntimeError(f"timed out waiting for runtime events; observed={names}")


def _has_two_actor_snapshot(events: List[RuntimeEventFrame]) -> bool:
    for event in events:
        actors = event.payload.get("actors")
        if event.name is EventName.WORLD_SNAPSHOT and isinstance(actors, list):
            return len(actors) == 2
    return False


def _has_action_snapshot(
    events: List[RuntimeEventFrame],
    command_id: str,
    posture: str,
    anchor_id: str | None = None,
    actor_id: str = "saevi-1",
) -> bool:
    for event in events:
        if event.name is not EventName.WORLD_SNAPSHOT or event.cause_id != command_id:
            continue
        _, residents = parse_world_snapshot(event.payload)
        if any(
            resident.elfie_id == actor_id
            and resident.posture == posture
            and (anchor_id is None or resident.action_anchor_id == anchor_id)
            for resident in residents
        ):
            return True
    return False


def _visible_semantic_ids(
    visual_event: RuntimeEventFrame,
    startup: List[RuntimeEventFrame],
) -> tuple[str, ...]:
    """Check actual FOV results against this Runtime's manifest and actor facts."""
    manifest = next(
        (
            event
            for event in reversed(startup)
            if event.name is EventName.SCENE_MANIFEST
            and (event.runtime_id, event.generation, event.world_revision)
            == (
                visual_event.runtime_id,
                visual_event.generation,
                visual_event.world_revision,
            )
        ),
        None,
    )
    if manifest is None:
        raise RuntimeError("visual observation has no matching scene manifest")
    catalog = parse_scene_manifest(manifest.payload)
    zone_id = visual_event.payload.get("zone_id")
    zone = next((zone for zone in catalog.zones if zone.zone_id == zone_id), None)
    if visual_event.payload.get("actor_id") != "saevi-1" or zone is None:
        raise RuntimeError("visual observation has invalid actor or zone")
    valid_ids = {
        f"anchor/{anchor.anchor_id}" for anchor in zone.anchors if anchor.active
    } | {
        f"facility/{facility.facility_id}"
        for facility in catalog.facilities
        if facility.active and facility.zone_id == zone_id
    }
    snapshot = next(
        (
            event
            for event in reversed(startup)
            if event.name is EventName.WORLD_SNAPSHOT
            and (event.runtime_id, event.generation, event.world_revision)
            == (
                visual_event.runtime_id,
                visual_event.generation,
                visual_event.world_revision,
            )
        ),
        None,
    )
    if snapshot is not None:
        _, residents = parse_world_snapshot(snapshot.payload)
        valid_ids.update(
            f"actor/{resident.elfie_id}"
            for resident in residents
            if resident.elfie_id != "saevi-1" and resident.current_zone_id == zone_id
        )
    visible = visual_event.payload.get("visible_semantic_ids")
    if (
        not isinstance(visible, list)
        or not visible
        or len(visible) > 32
        or any(
            not isinstance(value, str) or value not in valid_ids for value in visible
        )
        or len(set(visible)) != len(visible)
    ):
        raise RuntimeError(
            f"visual observation returned invalid semantic targets: {visible}"
        )
    return tuple(cast(List[str], visible))


def _use_furniture(
    server: GodotAPIServer,
    anchor_id: str,
) -> dict[str, object]:
    """Require NativeBody receipts backed by the matching Runtime wire events."""
    connection = server.runtime_connection
    if connection is None:
        raise RuntimeError("runtime disconnected before furniture action")
    runtime_token = (
        connection.runtime_id,
        connection.generation,
        server.runtime_world_revision,
    )
    transport = GodotTransport(server, actor_id="saevi-1")
    body = NativeBody("saevi-1", transport)
    events: list[RuntimeEventFrame] = []
    terminal_seen = Event()

    def observe(event: RuntimeEventFrame) -> None:
        events.append(event)
        if event.name is EventName.INTENT_TERMINAL:
            terminal_seen.set()

    transport.connect(observe)
    body.connect()
    now = datetime.now(timezone.utc)
    command = CapabilityCommand(
        command_type="capability",
        command_id=CommandId(f"real-use-{anchor_id}"),
        intent_id=IntentId(f"intent-use-{anchor_id}"),
        turn_id=TurnId("nest-e2e-furniture"),
        body_id=BodyId("saevi-1"),
        body_generation=1,
        issued_at=now,
        deadline=now + timedelta(seconds=120),
        capability_revision=body.capabilities.revision,
        capability_id="furniture.use",
        arguments={"anchor_id": anchor_id},
    )
    try:
        receipts = body.execute(command)
        # The transport wakes execute() before dispatching its event handlers.
        if not terminal_seen.wait(timeout=1.0):
            raise RuntimeError(f"furniture action has no wire terminal at {anchor_id}")
    finally:
        body.disconnect()
        transport.disconnect(observe)
    expected = [CommandStatus.ACCEPTED, CommandStatus.STARTED, CommandStatus.COMPLETED]
    if [receipt.status for receipt in receipts] != expected:
        raise RuntimeError(f"furniture action failed at {anchor_id}: {receipts}")
    wire = [
        event
        for event in events
        if event.name
        in {
            EventName.INTENT_ACCEPTED,
            EventName.INTENT_STARTED,
            EventName.INTENT_TERMINAL,
        }
    ]
    if (
        [event.name for event in wire]
        != [
            EventName.INTENT_ACCEPTED,
            EventName.INTENT_STARTED,
            EventName.INTENT_TERMINAL,
        ]
        or any(
            event.target_actor_id != str(command.body_id)
            or event.payload.get("command_id") != str(command.command_id)
            or event.payload.get("intent_id") != str(command.intent_id)
            or event.payload.get("body_generation") != command.body_generation
            or (event.runtime_id, event.generation, event.world_revision)
            != runtime_token
            for event in wire
        )
        or wire[-1].payload.get("status") != "completed"
    ):
        raise RuntimeError(f"furniture wire lifecycle mismatch at {anchor_id}: {wire}")

    return {
        "anchor_id": anchor_id,
        "command_id": str(command.command_id),
        "receipts": [receipt.status.value for receipt in receipts],
        "wire_events": [event.name.value for event in wire],
    }


def run(
    port: int,
    nonce: str,
    *,
    verify_reconnect: bool,
    observer_recording: _ObserverRecording | None = None,
    observer_hold_seconds: float = 0.0,
) -> dict[str, object]:
    server = GodotAPIServer(
        port=port,
        handshake_nonce=nonce,
        allowed_origins={""},
    )
    engine = ElfieNestEngine(
        GodotNestSessionAdapter(gateway=server), nest_config=NestConfig(bed_count=32)
    )
    engine.session.register_elfie("saevi-1", _elfie("saevi-1", "saevi", 101))
    engine.session.register_elfie("tovren-1", _elfie("tovren-1", "tovren", 202))
    server.start()
    print(
        json.dumps(
            {
                "event": "nest_e2e_ready",
                "ws_url": f"ws://127.0.0.1:{port}",
                "nonce": nonce,
                "elfie_fixture": "identity_only_magicmock_no_brain_or_provider",
            }
        ),
        flush=True,
    )
    try:
        startup = _wait_for(
            engine,
            server,
            _has_two_actor_snapshot,
            timeout=90.0,
            recording=observer_recording,
        )
        revision = server.runtime_world_revision
        if revision is None:
            raise RuntimeError("runtime never became ready")
        speech_id = "real-speech-1"
        server.request_speech_reach(
            command_id=speech_id,
            actor_id="saevi-1",
            acoustic_profile="normal",
            world_revision=revision,
        )
        speech = _wait_for(
            engine,
            server,
            lambda events: any(
                event.name is EventName.SPEECH_REACH
                and event.payload.get("command_id") == speech_id
                for event in events
            ),
            timeout=10.0,
            recording=observer_recording,
        )
        audience = next(
            event for event in speech if event.name is EventName.SPEECH_REACH
        )
        if audience.payload.get("audience_actor_ids") != ["tovren-1"]:
            raise RuntimeError("speech audience mismatch")

        # The real Body path first lets Nest persist the utterance and ask
        # Godot for reachability, then sends a content-free direct Body
        # animation command.  This proves the full SpeechBridge without
        # leaking speech content into Godot.
        speech_body_events: list[RuntimeEventFrame] = []
        speech_transport = GodotTransport(
            server,
            actor_id="saevi-1",
            speech_intent=cast(
                Callable[[RuntimeIntentPayload], bool], engine.session.prepare_speech
            ),
        )
        speech_transport.connect(speech_body_events.append)
        speak_id = "real-speak-body-1"
        speak_result = _run_action(
            engine,
            server,
            observer_recording,
            partial(
                speech_transport.execute_intent,
                RuntimeIntentPayload(
                    command_id=speak_id,
                    intent_id=f"intent-{speak_id}",
                    actor_id="saevi-1",
                    body_generation=1,
                    initiator="elfie",
                    intent="speak",
                    text="hello from Nest",
                    deadline_seconds=10.0,
                ),
                timeout_seconds=15.0,
            ),
        )
        speech_transport.disconnect(speech_body_events.append)
        if speak_result.terminal_status != "completed":
            raise RuntimeError(f"speech body action failed: {speak_result}")
        speech_body_reach = _wait_for(
            engine,
            server,
            lambda events: any(
                event.name is EventName.SPEECH_REACH
                and event.payload.get("command_id") == speak_id
                for event in events
            ),
            timeout=10.0,
            recording=observer_recording,
        )
        speech_body_reach_event = next(
            event
            for event in speech_body_reach
            if event.name is EventName.SPEECH_REACH
            and event.payload.get("command_id") == speak_id
        )
        if speech_body_reach_event.payload.get("audience_actor_ids") != ["tovren-1"]:
            raise RuntimeError("speech body audience mismatch")

        observation_id = "real-visual-1"
        server.request_visual_observation(
            observation_id=observation_id,
            actor_id="saevi-1",
            max_results=32,
            world_revision=revision,
        )
        visual = _wait_for(
            engine,
            server,
            lambda events: any(
                event.name is EventName.VISUAL_OBSERVATION
                and event.payload.get("observation_id") == observation_id
                for event in events
            ),
            timeout=10.0,
            recording=observer_recording,
        )
        visual_event = next(
            event
            for event in visual
            if event.name is EventName.VISUAL_OBSERVATION
            and event.payload.get("observation_id") == observation_id
        )
        # Godot owns facing, FOV and occlusion. Validate nonempty actual targets
        # in the reported zone, rather than forcing a particular facility into view.
        visible_ids = _visible_semantic_ids(visual_event, startup)

        environment_id = "real-environment-1"
        server.apply_environment(
            object_id="nest/environment",
            command_id=environment_id,
            lights_on=False,
            quiet_mode=True,
            world_revision=revision,
        )
        environment = _wait_for(
            engine,
            server,
            lambda events: any(
                event.name is EventName.ENVIRONMENT_STATE
                and event.payload.get("command_id") == environment_id
                for event in events
            ),
            timeout=10.0,
            recording=observer_recording,
        )
        environment_event = next(
            event
            for event in environment
            if event.name is EventName.ENVIRONMENT_STATE
            and event.payload.get("command_id") == environment_id
        )
        if environment_event.payload.get("applied") is not True:
            raise RuntimeError(
                f"environment command was not applied: {environment_event.payload}"
            )

        body_events: list[RuntimeEventFrame] = []
        saevi_transport = GodotTransport(server, actor_id="saevi-1")
        saevi_transport.connect(body_events.append)
        move_targets: dict[str, str] = {}
        try:
            for index, anchor_id in enumerate(
                ("central-01/activity", "courtyard/activity"), 1
            ):
                move_id = f"real-move-{index}"
                move_result = _run_action(
                    engine,
                    server,
                    observer_recording,
                    partial(
                        saevi_transport.execute_intent,
                        RuntimeIntentPayload(
                            command_id=move_id,
                            intent_id=f"intent-{move_id}",
                            actor_id="saevi-1",
                            body_generation=1,
                            initiator="elfie",
                            intent="move_to_anchor",
                            anchor_id=anchor_id,
                            deadline_seconds=120.0,
                        ),
                        timeout_seconds=125.0,
                    ),
                )
                if move_result.terminal_status != "completed":
                    raise RuntimeError(f"movement failed at {anchor_id}: {move_result}")
                move_targets[anchor_id] = move_result.terminal_status
        finally:
            saevi_transport.disconnect(body_events.append)

        furniture = []
        for anchor, posture in (
            ("dorm-01/bed-01", "sleeping"),
            ("dorm-01/chair-01", "sitting"),
        ):
            used = _run_action(
                engine,
                server,
                observer_recording,
                partial(_use_furniture, server, anchor),
            )
            _wait_for(
                engine,
                server,
                partial(
                    _has_action_snapshot,
                    command_id=str(used["command_id"]),
                    posture=posture,
                    anchor_id=anchor,
                ),
                timeout=3.0,
                recording=observer_recording,
            )
            projected = engine.session.observer_semantic_entities()["saevi-1"]
            if projected.action_anchor_id != anchor or projected.posture != posture:
                raise RuntimeError(
                    f"Observer projection disagrees with furniture: {projected}"
                )
            hold_until = time.monotonic() + observer_hold_seconds
            while time.monotonic() < hold_until:
                _pump(engine, server, observer_recording)
                time.sleep(0.02)
            used["world_posture"] = posture
            furniture.append(used)

        cancel_id = "real-cancel-1"
        tovren_events: list[RuntimeEventFrame] = []
        tovren_transport = GodotTransport(server, actor_id="tovren-1")
        tovren_transport.connect(tovren_events.append)
        cancel_result: dict[str, object] = {}

        def run_cancelled_move() -> None:
            cancel_result["result"] = tovren_transport.execute_intent(
                RuntimeIntentPayload(
                    command_id=cancel_id,
                    intent_id=f"intent-{cancel_id}",
                    actor_id="tovren-1",
                    body_generation=1,
                    initiator="elfie",
                    intent="move_to_anchor",
                    anchor_id="central-01/activity",
                    deadline_seconds=120.0,
                ),
                timeout_seconds=10.0,
            )

        worker = Thread(target=run_cancelled_move, daemon=True)
        worker.start()
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not any(
            event.name is EventName.INTENT_STARTED
            and event.payload.get("command_id") == cancel_id
            for event in tovren_events
        ):
            time.sleep(0.02)
        if not any(
            event.name is EventName.INTENT_STARTED
            and event.payload.get("command_id") == cancel_id
            for event in tovren_events
        ):
            raise RuntimeError("cancel target never started moving")
        if not server.cancel_body_command(command_id=cancel_id, actor_id="tovren-1"):
            raise RuntimeError("cancel command was not accepted by the Gateway")
        worker.join(timeout=10.0)
        tovren_transport.disconnect(tovren_events.append)
        cancel_runtime_result = cancel_result.get("result")
        if (
            cancel_runtime_result is None
            or getattr(cancel_runtime_result, "terminal_status", None) != "cancelled"
        ):
            raise RuntimeError(f"cancel failed: {cancel_runtime_result}")
        _wait_for(
            engine,
            server,
            partial(
                _has_action_snapshot,
                command_id=cancel_id,
                posture="idle",
                actor_id="tovren-1",
            ),
            timeout=3.0,
            recording=observer_recording,
        )
        cancelled_view = engine.session.observer_semantic_entities()["tovren-1"]
        if (
            cancelled_view.active_command_id is not None
            or cancelled_view.action_anchor_id is not None
        ):
            raise RuntimeError(
                "cancelled action remained active in the Observer projection"
            )
        result: dict[str, object] = {
            "runtime_id": server.runtime_connection.runtime_id
            if server.runtime_connection is not None
            else None,
            "world_revision": revision,
            "startup_events": [event.name.value for event in startup],
            "speech_audience": audience.payload["audience_actor_ids"],
            "speak_terminal": speak_result.terminal_status,
            "visual_count": len(visible_ids),
            "visible_semantic_ids": list(visible_ids),
            "environment_applied": environment_event.payload["applied"],
            "move_terminal": move_result.terminal_status,
            "move_targets": move_targets,
            "furniture": furniture,
            "elfie_fixture": "identity_only_magicmock_no_brain_or_provider",
            "cancel_terminal": getattr(cancel_runtime_result, "terminal_status", None),
        }
        if verify_reconnect:
            connection = server.runtime_connection
            if connection is None:
                raise RuntimeError("runtime disconnected before reconnect check")
            first_runtime_id = connection.runtime_id
            first_generation = connection.generation
            print(json.dumps({"event": "nest_e2e_restart_requested"}), flush=True)
            saw_disconnect = False

            def reconnected(events: List[RuntimeEventFrame]) -> bool:
                nonlocal saw_disconnect
                active = server.runtime_connection
                saw_disconnect = saw_disconnect or active is None
                return (
                    saw_disconnect
                    and active is not None
                    and (
                        active.runtime_id != first_runtime_id
                        or active.generation > first_generation
                    )
                    and _has_two_actor_snapshot(events)
                )

            _wait_for(
                engine, server, reconnected, timeout=90.0, recording=observer_recording
            )
            active = server.runtime_connection
            if active is None:
                raise RuntimeError("runtime disconnected after reconnect check")
            result["reconnect_runtime_id"] = active.runtime_id
            result["reconnect_generation"] = active.generation
        _pump(engine, server, observer_recording)
        if observer_recording is not None:
            observer_recording.capture(engine, server, "passed")
        return result
    finally:
        server.stop()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18765)
    parser.add_argument("--nonce", default="nest-real-e2e")
    parser.add_argument("--verify-reconnect", action="store_true")
    parser.add_argument("--observer-output", type=Path)
    parser.add_argument("--observer-hold-seconds", type=float, default=0.0)
    args = parser.parse_args()
    recording = None
    if args.observer_output is not None:
        output = args.observer_output.resolve()
        build_root = Path(__file__).resolve().parents[3] / "build"
        if build_root not in output.parents:
            parser.error("--observer-output must be inside this repository's build/")
        recording = _ObserverRecording(output)
    if not 0.0 <= args.observer_hold_seconds <= 10.0:
        parser.error("--observer-hold-seconds must be between 0 and 10")
    if args.observer_hold_seconds and recording is None:
        parser.error("--observer-hold-seconds requires --observer-output")
    try:
        result = run(
            args.port,
            args.nonce,
            verify_reconnect=args.verify_reconnect,
            observer_recording=recording,
            observer_hold_seconds=args.observer_hold_seconds,
        )
    except Exception as exc:
        print(json.dumps({"event": "nest_e2e_failed", "error": str(exc)}))
        return 1
    print(json.dumps({"event": "nest_e2e_passed", **result}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
