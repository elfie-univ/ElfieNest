"""Developer-only controller that maps Lab controls to Godot protocol v2."""

from __future__ import annotations

from functools import wraps
from pathlib import Path
from secrets import token_urlsafe
from threading import RLock
from typing import Any, Callable

from app.orchestration.scene_manifest import parse_scene_manifest, parse_world_snapshot
from devtools.nest_lab.actor_sync import sync_actors
from devtools.nest_lab.event_log import LabEventLog
from devtools.nest_lab.models import LabActor, LabSpecies, NestLabConflictError
from devtools.nest_lab.residents import assign_missing_homes, clear_home_assignments
from devtools.nest_lab.simulation import WanderScheduler
from nest import Nest, NestConfig
from nest.godot.api import GodotAPIServer
from nest.godot.messages import CommandName, EventName, RuntimeEventFrame


def _synchronized(method: Callable[..., Any]) -> Callable[..., Any]:
    """Serialize HTTP requests and the WebSocket gateway callback thread."""

    @wraps(method)
    def locked(world: NestLabWorld, *args: Any, **kwargs: Any) -> Any:
        with world._lock:
            return method(world, *args, **kwargs)

    return locked


class NestLabWorld:
    """Own a disposable Nest model and translate Lab actions into v2 commands."""

    def __init__(
        self,
        *,
        http_port: int,
        websocket_port: int,
        data_dir: Path,
        gateway: GodotAPIServer | None = None,
    ) -> None:
        self._lock = RLock()
        self._gateway = gateway or GodotAPIServer(
            port=websocket_port,
            http_port=http_port,
            handshake_nonce=token_urlsafe(32),
        )
        self._data_dir = data_dir
        self._nest = Nest(NestConfig(max_residents=32))
        self._bed_count = 4
        self._world_revision = 1
        self._actors: dict[str, LabActor] = {}
        self._events = LabEventLog()
        self._wander_scheduler = WanderScheduler(
            self._gateway, self._nest, self._events
        )
        self._next_actor_sequence = 0
        self._connection_token: tuple[str, int] | None = None
        self._manifest_revision: int | None = None
        self._ready_revision: int | None = None
        self._actor_catalog_dirty = True
        self._wandering = False
        self._paused = False

    @property
    def websocket_url(self) -> str:
        """Return the browser-safe loopback URL for the embedded runtime."""
        return f"ws://127.0.0.1:{self._gateway.port}"

    @property
    def nonce(self) -> str:
        """Return the per-process handshake nonce used by the iframe."""
        return self._gateway.handshake_nonce

    @_synchronized
    def start(self) -> None:
        """Start the Lab-owned Runtime gateway."""
        self._gateway.start()
        self._events.append("gateway_started", self.websocket_url)

    @_synchronized
    def stop(self) -> None:
        """Stop the Lab-owned Runtime gateway."""
        self._gateway.stop()

    @_synchronized
    def status(self) -> dict[str, bool | int | str]:
        """Poll the Runtime before exposing the latest Lab state."""
        self.poll()
        return {
            "scope": "developer",
            "protocol": 2,
            "websocket_url": self.websocket_url,
            "nonce": self.nonce,
            "runtime_connected": self._gateway.runtime_connection is not None,
            "runtime_ready": self._ready_revision is not None,
            "paused": self._paused,
            "wandering": self._wandering,
        }

    @_synchronized
    def world(self) -> dict[str, bool | int | str]:
        """Return the semantic Lab world state without spatial coordinates."""
        self.poll()
        return {
            "module": "elfienest-world",
            "runtime": "isolated",
            "production_engine": False,
            "max_elfies": 32,
            "bed_count": self._bed_count,
            "world_revision": self._world_revision,
            "actor_count": len(self._actors),
            "paused": self._paused,
            "wandering": self._wandering,
            "data_dir": str(self._data_dir),
        }

    @_synchronized
    def actors(self) -> tuple[LabActor, ...]:
        """Return Lab actors in stable insertion order."""
        self.poll()
        return tuple(self._actors.values())

    @_synchronized
    def events(self) -> tuple[dict[str, str | int], ...]:
        """Return the bounded developer timeline."""
        self.poll()
        return tuple(event.to_dict() for event in self._events.items())

    @_synchronized
    def set_bed_count(self, bed_count: int) -> dict[str, bool | int | str]:
        """Reconfigure the fixed room when all residents still fit."""
        self.poll()
        if bed_count < len(self._actors):
            raise NestLabConflictError("床位数不能小于当前角色数量")
        if bed_count != self._bed_count:
            self._bed_count = bed_count
            self._world_revision += 1
            clear_home_assignments(self._nest, self._actors)
            self._manifest_revision = None
            self._ready_revision = None
            self._actor_catalog_dirty = True
            self._connection_token = None
            self._events.append("world_reconfigured", f"bed_count={bed_count}")
        self.poll()
        return self.world()

    @_synchronized
    def add_actor(self, species: LabSpecies) -> LabActor:
        """Add one actor if the configured room has a free bed."""
        self.poll()
        if len(self._actors) >= self._bed_count:
            raise NestLabConflictError("当前床位已满，不能再添加角色")
        self._next_actor_sequence += 1
        actor = LabActor(f"lab-{species}-{self._next_actor_sequence:03d}", species)
        self._actors[actor.actor_id] = actor
        self._nest.register_resident(actor.actor_id)
        assign_missing_homes(self._nest, self._actors)
        self._actor_catalog_dirty = True
        self._events.append("actor_added", f"{actor.actor_id} ({species})")
        self.poll()
        return actor

    @_synchronized
    def set_wandering(self) -> dict[str, bool]:
        """Enable bounded Python-side random semantic movement."""
        self.poll()
        self._wandering = True
        self._wander_scheduler.enable()
        self._events.append("wander_enabled", "Python scheduler enabled")
        self.poll()
        return {"wandering": True}

    @_synchronized
    def pause(self) -> dict[str, bool]:
        """Stop scheduling and cancel active Godot movement commands."""
        self.poll()
        self._paused = True
        self._wander_scheduler.cancel_active(self._ready_revision)
        self._events.append("simulation_paused", "active moves cancelled")
        return {"paused": True}

    @_synchronized
    def resume(self) -> dict[str, bool]:
        """Resume the scheduler without changing the wander preference."""
        self.poll()
        self._paused = False
        self._wander_scheduler.resume()
        self._events.append("simulation_resumed", "scheduler resumed")
        return {"paused": False}

    @_synchronized
    def reset(self) -> dict[str, int]:
        """Clear the disposable actor set and request a new world revision."""
        self.pause()
        for actor_id in tuple(self._actors):
            self._nest.remove_resident(actor_id)
        self._actors.clear()
        self._wander_scheduler.clear()
        self._wandering = False
        self._paused = False
        self._world_revision += 1
        self._manifest_revision = None
        self._ready_revision = None
        self._actor_catalog_dirty = True
        self._connection_token = None
        self._events.append("simulation_reset", f"revision={self._world_revision}")
        self.poll()
        return {"actor_count": 0, "world_revision": self._world_revision}

    @_synchronized
    def poll(self) -> None:
        """Drain Runtime facts, converge desired state, then run Lab scheduling."""
        self._observe_connection()
        for event in self._gateway.drain_runtime_events():
            self._consume_runtime_event(event)
        if self._actor_catalog_dirty and self._ready_revision is not None:
            self._actor_catalog_dirty = not sync_actors(
                self._gateway,
                self._nest,
                self._events,
                self._actors.values(),
                world_revision=self._ready_revision,
            )
        self._wander_scheduler.schedule(
            self._actors.values(),
            ready_revision=self._ready_revision,
            enabled=self._wandering,
            paused=self._paused,
        )

    def _observe_connection(self) -> None:
        connection = self._gateway.runtime_connection
        token = (
            (connection.runtime_id, connection.generation)
            if connection is not None
            else None
        )
        if token == self._connection_token:
            return
        self._connection_token = token
        self._manifest_revision = None
        self._ready_revision = None
        self._actor_catalog_dirty = True
        self._wander_scheduler.clear()
        if token is None:
            self._events.append("runtime_disconnected", "waiting for Godot Web")
            return
        self._events.append("runtime_connected", f"{token[0]} generation={token[1]}")
        self._send_world_configuration()

    def _send_world_configuration(self) -> None:
        message_id = self._gateway.send_runtime_command(
            CommandName.CONFIGURE_WORLD,
            {
                "nest_id": "nest-lab",
                "bed_count": self._bed_count,
                "world_revision": self._world_revision,
            },
            world_revision=self._world_revision,
        )
        if message_id is not None:
            self._events.append("configure_world", f"revision={self._world_revision}")

    def _consume_runtime_event(self, event: RuntimeEventFrame) -> None:
        self._events.append(event.name.value, event.message_id)
        if event.name is EventName.SCENE_MANIFEST:
            catalog = parse_scene_manifest(event.payload)
            if catalog.revision != self._world_revision:
                return
            self._nest.apply_catalog(catalog)
            self._manifest_revision = catalog.revision
            assign_missing_homes(self._nest, self._actors)
            self._actor_catalog_dirty = True
        elif event.name is EventName.WORLD_READY:
            if event.world_revision == self._manifest_revision:
                self._ready_revision = event.world_revision
                connection = self._gateway.runtime_connection
                if connection is not None:
                    self._gateway.mark_runtime_ready(
                        connection,
                        world_revision=event.world_revision,
                    )
        elif event.name is EventName.WORLD_SNAPSHOT:
            revision, mirrors = parse_world_snapshot(event.payload)
            if revision == self._ready_revision:
                self._nest.apply_runtime_mirrors(mirrors)
        elif event.name is EventName.INTENT_TERMINAL:
            command_id = event.payload.get("command_id")
            if isinstance(command_id, str):
                self._wander_scheduler.complete(command_id)
