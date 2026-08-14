"""Run a real Python WebSocket to Godot protocol-v3 acceptance scenario."""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable
from threading import Thread
from typing import List, cast
from unittest.mock import MagicMock

from app.orchestration.nest_session import ElfieNestEngine
from elfie import Elfie
from elfie.profile import ElfieProfile, create_visual_profile
from infrastructure.godot.body_transport import GodotTransport, RuntimeIntentPayload
from infrastructure.godot.gateway.api import GodotAPIServer
from infrastructure.godot.gateway.messages import (
    EventName,
    RuntimeEventFrame,
)
from infrastructure.godot.nest_session import GodotNestSessionAdapter
from infrastructure.godot.nest_session.mapper import map_runtime_event


def _profile(elfie_id: str, species: str, seed: int) -> ElfieProfile:
    return create_visual_profile(
        elfie_id=elfie_id,
        display_name=elfie_id,
        species_id=species,
        seed=seed,
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
    elfie = MagicMock(spec=Elfie)
    elfie.character_profile = _profile(elfie_id, species, seed)
    return elfie


def _pump(
    engine: ElfieNestEngine,
    server: GodotAPIServer,
) -> List[RuntimeEventFrame]:
    engine.session.poll_runtime_connection()
    events = list(server.drain_runtime_events())
    for event in events:
        engine.session.consume_runtime_event(map_runtime_event(event))
    engine.session.flush_runtime_state()
    return events


def _wait_for(
    engine: ElfieNestEngine,
    server: GodotAPIServer,
    predicate: Callable[[List[RuntimeEventFrame]], bool],
    *,
    timeout: float,
) -> List[RuntimeEventFrame]:
    observed: List[RuntimeEventFrame] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        observed.extend(_pump(engine, server))
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


def run(port: int, nonce: str, *, verify_reconnect: bool) -> dict[str, object]:
    server = GodotAPIServer(
        port=port,
        handshake_nonce=nonce,
        allowed_origins={""},
    )
    engine = ElfieNestEngine(GodotNestSessionAdapter(gateway=server))
    engine.session.register_elfie("fox-1", _elfie("fox-1", "fox", 101))
    engine.session.register_elfie("dog-1", _elfie("dog-1", "dog", 202))
    server.start()
    print(
        json.dumps(
            {
                "event": "nest_e2e_ready",
                "ws_url": f"ws://127.0.0.1:{port}",
                "nonce": nonce,
            }
        ),
        flush=True,
    )
    try:
        startup = _wait_for(
            engine,
            server,
            _has_two_actor_snapshot,
            timeout=45.0,
        )
        revision = server.runtime_world_revision
        if revision is None:
            raise RuntimeError("runtime never became ready")
        speech_id = "real-speech-1"
        server.request_speech_reach(
            command_id=speech_id,
            actor_id="fox-1",
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
        )
        audience = next(
            event for event in speech if event.name is EventName.SPEECH_REACH
        )
        if audience.payload.get("audience_actor_ids") != ["dog-1"]:
            raise RuntimeError("speech audience mismatch")

        # The real Body path first lets Nest persist the utterance and ask
        # Godot for reachability, then sends a content-free direct Body
        # animation command.  This proves the full SpeechBridge without
        # leaking speech content into Godot.
        speech_body_events: list[RuntimeEventFrame] = []
        speech_transport = GodotTransport(
            server,
            actor_id="fox-1",
            speech_intent=cast(
                Callable[[RuntimeIntentPayload], bool], engine.session.prepare_speech
            ),
        )
        speech_transport.connect(speech_body_events.append)
        speak_id = "real-speak-body-1"
        speak_result = speech_transport.execute_intent(
            RuntimeIntentPayload(
                command_id=speak_id,
                actor_id="fox-1",
                intent="speak",
                text="hello from Nest",
                deadline_seconds=10.0,
            ),
            timeout_seconds=15.0,
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
        )
        speech_body_reach_event = next(
            event
            for event in speech_body_reach
            if event.name is EventName.SPEECH_REACH
            and event.payload.get("command_id") == speak_id
        )
        if speech_body_reach_event.payload.get("audience_actor_ids") != ["dog-1"]:
            raise RuntimeError("speech body audience mismatch")

        observation_id = "real-visual-1"
        server.request_visual_observation(
            observation_id=observation_id,
            actor_id="fox-1",
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
        )
        visual_event = next(
            event
            for event in visual
            if event.name is EventName.VISUAL_OBSERVATION
            and event.payload.get("observation_id") == observation_id
        )
        visible_ids_value = visual_event.payload.get("visible_semantic_ids", [])
        if not isinstance(visible_ids_value, list):
            raise RuntimeError("visual observation returned invalid semantic IDs")
        visible_ids = tuple(str(value) for value in visible_ids_value)
        # The default authored dorm scene deliberately leaves actor facing under
        # the scene/actor authority.  A visual query therefore may legitimately
        # return only semantic facilities when the observer is resting.  The
        # positive actor/FOV/occlusion path is exercised by the real Godot
        # interaction contract; this cross-boundary E2E asserts the stable
        # semantic observation route without making Python own orientation.
        if not visible_ids:
            raise RuntimeError(
                f"visual observation returned no semantic IDs: {visible_ids}"
            )
        if "facility/dorm-01/rest" not in visible_ids:
            raise RuntimeError(
                f"visual observation omitted the dorm facility: {visible_ids}"
            )

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
        fox_transport = GodotTransport(server, actor_id="fox-1")
        fox_transport.connect(body_events.append)
        move_id = "real-move-1"
        move_result = fox_transport.execute_intent(
            RuntimeIntentPayload(
                command_id=move_id,
                actor_id="fox-1",
                intent="move_to_anchor",
                anchor_id="activity-01/activity",
                deadline_seconds=20.0,
            ),
            timeout_seconds=25.0,
        )
        fox_transport.disconnect(body_events.append)
        if move_result.terminal_status != "completed":
            raise RuntimeError(f"movement failed: {move_result}")

        cancel_id = "real-cancel-1"
        dog_events: list[RuntimeEventFrame] = []
        dog_transport = GodotTransport(server, actor_id="dog-1")
        dog_transport.connect(dog_events.append)
        cancel_result: dict[str, object] = {}

        def run_cancelled_move() -> None:
            cancel_result["result"] = dog_transport.execute_intent(
                RuntimeIntentPayload(
                    command_id=cancel_id,
                    actor_id="dog-1",
                    intent="move_to_anchor",
                    anchor_id="activity-01/activity",
                    deadline_seconds=20.0,
                ),
                timeout_seconds=10.0,
            )

        worker = Thread(target=run_cancelled_move, daemon=True)
        worker.start()
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not any(
            event.name is EventName.INTENT_STARTED
            and event.payload.get("command_id") == cancel_id
            for event in dog_events
        ):
            time.sleep(0.02)
        if not server.cancel_body_command(command_id=cancel_id, actor_id="dog-1"):
            raise RuntimeError("cancel command was not accepted by the Gateway")
        worker.join(timeout=10.0)
        dog_transport.disconnect(dog_events.append)
        cancel_runtime_result = cancel_result.get("result")
        if (
            cancel_runtime_result is None
            or getattr(cancel_runtime_result, "terminal_status", None) != "cancelled"
        ):
            raise RuntimeError(f"cancel failed: {cancel_runtime_result}")
        result: dict[str, object] = {
            "runtime_id": server.runtime_connection.runtime_id
            if server.runtime_connection is not None
            else None,
            "world_revision": revision,
            "startup_events": [event.name.value for event in startup],
            "speech_audience": audience.payload["audience_actor_ids"],
            "speak_terminal": speak_result.terminal_status,
            "visual_count": len(visible_ids),
            "environment_applied": environment_event.payload["applied"],
            "move_terminal": move_result.terminal_status,
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

            _wait_for(engine, server, reconnected, timeout=90.0)
            active = server.runtime_connection
            if active is None:
                raise RuntimeError("runtime disconnected after reconnect check")
            result["reconnect_runtime_id"] = active.runtime_id
            result["reconnect_generation"] = active.generation
        return result
    finally:
        server.stop()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18765)
    parser.add_argument("--nonce", default="nest-real-e2e")
    parser.add_argument("--verify-reconnect", action="store_true")
    args = parser.parse_args()
    try:
        result = run(
            args.port,
            args.nonce,
            verify_reconnect=args.verify_reconnect,
        )
    except Exception as exc:
        print(json.dumps({"event": "nest_e2e_failed", "error": str(exc)}))
        return 1
    print(json.dumps({"event": "nest_e2e_passed", **result}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
