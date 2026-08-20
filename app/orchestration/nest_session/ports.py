"""Outbound ports owned by the live Nest Session workflow."""

from __future__ import annotations

from typing import Protocol

from app.orchestration.nest_session.models import (
    RuntimeActor,
    RuntimeConnection,
    WorldEvent,
)
from elfie.public import ModelPort
from nest.public import NestSnapshot


class NestStateStoreError(RuntimeError):
    """Application-facing failure from the injected Nest state store."""


class NestStateStorePort(Protocol):
    """Durable snapshot store owned by Nest Session orchestration."""

    def load_snapshot(self) -> NestSnapshot: ...

    def initialize_snapshot(self, snapshot: NestSnapshot) -> None: ...

    def save_snapshot(self, snapshot: NestSnapshot) -> None: ...


class ModelPortFactory(Protocol):
    """Create the already-configured cognition boundary for one real Elfie."""

    def __call__(self, elfie_id: str) -> ModelPort: ...


class RuntimeConnectionPort(Protocol):
    """Read-only identity of the current authoritative Runtime."""

    @property
    def runtime_connection(self) -> RuntimeConnection | None: ...


class RuntimeEventPort(RuntimeConnectionPort, Protocol):
    """Lifecycle/event capability consumed by the tick and event router."""

    def drain_events(self) -> tuple[WorldEvent, ...]: ...

    def mark_world_configured(
        self,
        connection: RuntimeConnection,
        *,
        world_revision: int,
    ) -> None: ...


class WorldSynchronizationPort(RuntimeConnectionPort, Protocol):
    """World manifest and Actor catalog synchronization capability."""

    def configure_world(
        self,
        *,
        nest_id: str,
        bed_count: int,
        world_revision: int,
    ) -> str | None: ...

    def synchronize_actors(
        self,
        actors: tuple[RuntimeActor, ...],
        *,
        world_revision: int,
    ) -> str | None: ...


class SpeechReachPort(Protocol):
    """Semantic speech reachability request capability."""

    def request_speech_reach(
        self,
        *,
        command_id: str,
        actor_id: str,
        acoustic_profile: str = "normal",
        world_revision: int,
    ) -> str | None: ...


class VisualObservationPort(Protocol):
    """Bounded semantic observation request capability."""

    def request_visual_observation(
        self,
        *,
        observation_id: str,
        actor_id: str,
        max_results: int = 32,
        world_revision: int,
    ) -> str | None: ...


class EnvironmentControlPort(Protocol):
    """Desired-to-actual environment synchronization capability."""

    def apply_environment(
        self,
        *,
        object_id: str,
        command_id: str,
        lights_on: bool,
        quiet_mode: bool,
        world_revision: int,
    ) -> str | None: ...


class NestSessionRuntimePort(
    RuntimeEventPort,
    Protocol,
):
    """Capabilities needed by the live Nest Session composition."""

    @property
    def runtime_ready(self) -> bool: ...

    def request_speech_reach(
        self,
        *,
        command_id: str,
        actor_id: str,
        acoustic_profile: str = "normal",
        world_revision: int,
    ) -> str | None: ...

    def request_visual_observation(
        self,
        *,
        observation_id: str,
        actor_id: str,
        max_results: int = 32,
        world_revision: int,
    ) -> str | None: ...

    def apply_environment(
        self,
        *,
        object_id: str,
        command_id: str,
        lights_on: bool,
        quiet_mode: bool,
        world_revision: int,
    ) -> str | None: ...


__all__ = (
    "EnvironmentControlPort",
    "ModelPortFactory",
    "NestStateStoreError",
    "NestStateStorePort",
    "NestSessionRuntimePort",
    "RuntimeConnectionPort",
    "RuntimeEventPort",
    "SpeechReachPort",
    "VisualObservationPort",
    "WorldSynchronizationPort",
)
