"""Run a real Python WebSocket to Godot protocol-v2 acceptance scenario."""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable
from typing import List
from unittest.mock import MagicMock

from app.orchestration.nest_session import ElfieNestEngine
from elfie import Elfie
from elfie.profile import ElfieProfile, create_visual_profile
from infrastructure.godot.gateway.api import GodotAPIServer
from infrastructure.godot.gateway.messages import (
    CommandName,
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


def _terminal(command_id: str) -> Callable[[List[RuntimeEventFrame]], bool]:
    return lambda events: any(
        event.name is EventName.INTENT_TERMINAL
        and event.payload.get("command_id") == command_id
        for event in events
    )


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
        server.send_runtime_command(
            CommandName.EXECUTE_INTENT,
            {
                "command_id": speech_id,
                "actor_id": "fox-1",
                "intent": "speak",
                "text": "Hello from the real runtime path",
                "deadline_seconds": 5.0,
            },
            world_revision=revision,
            correlation_id=speech_id,
        )
        speech = _wait_for(engine, server, _terminal(speech_id), timeout=10.0)
        audience = next(
            event for event in speech if event.name is EventName.SPEECH_AUDIENCE
        )
        if audience.payload.get("audience_actor_ids") != ["dog-1"]:
            raise RuntimeError("speech audience mismatch")

        move_id = "real-move-1"
        server.send_runtime_command(
            CommandName.EXECUTE_INTENT,
            {
                "command_id": move_id,
                "actor_id": "fox-1",
                "intent": "move_to_anchor",
                "anchor_id": "activity-01/activity",
                "deadline_seconds": 20.0,
            },
            world_revision=revision,
            correlation_id=move_id,
        )
        movement = _wait_for(engine, server, _terminal(move_id), timeout=25.0)
        move_terminal = next(
            event
            for event in movement
            if event.name is EventName.INTENT_TERMINAL
            and event.payload.get("command_id") == move_id
        )
        if move_terminal.payload.get("status") != "completed":
            physical_events = [
                {
                    "name": event.name.value,
                    "payload": event.payload,
                }
                for event in movement
                if event.name
                in {
                    EventName.MOVEMENT_BLOCKED,
                    EventName.TACTILE_CONTACT,
                    EventName.INTENT_TERMINAL,
                }
            ]
            raise RuntimeError(f"movement failed: {physical_events}")

        cancel_id = "real-cancel-1"
        server.send_runtime_command(
            CommandName.EXECUTE_INTENT,
            {
                "command_id": cancel_id,
                "actor_id": "dog-1",
                "intent": "move_to_anchor",
                "anchor_id": "activity-01/activity",
                "deadline_seconds": 20.0,
            },
            world_revision=revision,
            correlation_id=cancel_id,
        )
        _wait_for(
            engine,
            server,
            lambda events: any(
                event.name is EventName.INTENT_STARTED
                and event.payload.get("command_id") == cancel_id
                for event in events
            ),
            timeout=5.0,
        )
        server.send_runtime_command(
            CommandName.CANCEL_INTENT,
            {"command_id": cancel_id, "actor_id": "dog-1"},
            world_revision=revision,
            correlation_id=cancel_id,
        )
        cancelled = _wait_for(engine, server, _terminal(cancel_id), timeout=5.0)
        cancel_terminal = next(
            event
            for event in cancelled
            if event.name is EventName.INTENT_TERMINAL
            and event.payload.get("command_id") == cancel_id
        )
        if cancel_terminal.payload.get("status") != "cancelled":
            raise RuntimeError(f"cancel failed: {cancel_terminal.payload}")
        result: dict[str, object] = {
            "runtime_id": server.runtime_connection.runtime_id
            if server.runtime_connection is not None
            else None,
            "world_revision": revision,
            "startup_events": [event.name.value for event in startup],
            "speech_audience": audience.payload["audience_actor_ids"],
            "move_terminal": move_terminal.payload["status"],
            "cancel_terminal": cancel_terminal.payload["status"],
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
