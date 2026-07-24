"""Deterministic desired-state synchronization with the Godot Runtime."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import JsonValue

from app.orchestration.runtime_gateway import RuntimeGateway
from app.orchestration.scene_manifest import (
    parse_scene_manifest,
    parse_world_snapshot,
)
from nest import Nest
from nest.godot.messages import CommandName, EventName, JsonObject, RuntimeEventFrame
from nest.state.models import PersistentResidentState, ResidentPresence
from nest.state.repository import NestPersistenceError, NestRepository
from nest.state.store import NoHomeAvailableError


@dataclass(frozen=True)
class ActorDescriptor:
    """Render-stable actor identity owned by orchestration."""

    actor_id: str
    species: str
    appearance: JsonObject


ActorCatalogProvider = Callable[[], tuple[ActorDescriptor, ...]]


class NestRuntimeSynchronizer:  # noqa: MUTABLE_OK - runtime reconciliation state machine.
    """Merge desired residents until one authoritative Runtime is ready."""

    def __init__(
        self,
        *,
        nest: Nest,
        gateway: RuntimeGateway,
        actor_catalog_provider: ActorCatalogProvider,
        desired_bed_count: int = 4,
        repository: NestRepository | None = None,
    ) -> None:
        self._nest = nest
        self._gateway = gateway
        self._actor_catalog_provider = actor_catalog_provider
        self._desired_bed_count = desired_bed_count
        self._repository = repository
        self._desired_world_revision = 1
        self._observed_connection: tuple[str, int] | None = None
        self._manifest_revision: int | None = None
        self._ready_revision: int | None = None
        self._actor_catalog_dirty = True

    def mark_actor_catalog_dirty(self) -> None:
        self._actor_catalog_dirty = True

    @property
    def ready_revision(self) -> int | None:
        return self._ready_revision

    def poll_connection(self) -> None:
        connection = self._gateway.runtime_connection
        if connection is None:
            self._observed_connection = None
            self._manifest_revision = None
            self._ready_revision = None
            return
        token = (connection.runtime_id, connection.generation)
        if token == self._observed_connection:
            return
        self._observed_connection = token
        self._manifest_revision = None
        self._ready_revision = None
        self._actor_catalog_dirty = True
        self._gateway.send_runtime_command(
            CommandName.CONFIGURE_WORLD,
            {
                "nest_id": "local-nest",
                "bed_count": self._desired_bed_count,
                "world_revision": self._desired_world_revision,
            },
            world_revision=self._desired_world_revision,
        )

    def consume(self, event: RuntimeEventFrame) -> None:
        connection = self._gateway.runtime_connection
        if connection is None:
            return
        if (
            event.runtime_id != connection.runtime_id
            or event.generation != connection.generation
        ):
            return
        if event.name is EventName.SCENE_MANIFEST:
            if (
                self._manifest_revision is not None
                and event.world_revision <= self._manifest_revision
            ):
                return
            catalog = parse_scene_manifest(event.payload)
            if catalog.revision != event.world_revision:
                return
            if self._repository is not None:
                try:
                    self._repository.save_catalog(catalog)
                except NestPersistenceError:
                    return
            self._nest.apply_catalog(catalog)
            self._manifest_revision = catalog.revision
            try:
                self._assign_missing_homes()
            except NoHomeAvailableError:
                self._nest.state.reconciliation_required = True
                return
            self._actor_catalog_dirty = True
        elif event.name is EventName.WORLD_READY:
            if self._manifest_revision == event.world_revision:
                self._ready_revision = event.world_revision
        elif event.name is EventName.WORLD_SNAPSHOT:
            revision, mirrors = parse_world_snapshot(event.payload)
            if revision == event.world_revision and revision == self._ready_revision:
                self._nest.apply_runtime_mirrors(mirrors)

    def flush(self) -> None:
        if not self._actor_catalog_dirty:
            return
        if self._ready_revision is None or self._nest.state.reconciliation_required:
            return
        actors: list[JsonValue] = []
        for descriptor in self._actor_catalog_provider():
            home_anchor_id = self._nest.home_anchor_id(descriptor.actor_id)
            if home_anchor_id is None:
                return
            actors.append(
                {
                    "actor_id": descriptor.actor_id,
                    "species": descriptor.species,
                    "appearance": descriptor.appearance,
                    "home_anchor_id": home_anchor_id,
                }
            )
        command_id = self._gateway.send_runtime_command(
            CommandName.SYNC_ACTORS,
            {"actors": actors},
            world_revision=self._ready_revision,
        )
        if command_id is not None:
            self._actor_catalog_dirty = False

    def _assign_missing_homes(self) -> None:
        for descriptor in self._actor_catalog_provider():
            if self._nest.home_anchor_id(descriptor.actor_id) is None:
                assignment = self._nest.admit_resident(descriptor.actor_id)
                if self._repository is None:
                    continue
                try:
                    self._repository.save_resident(
                        PersistentResidentState(
                            elfie_id=descriptor.actor_id,
                            presence=ResidentPresence.ACTIVE,
                            home_zone_id=assignment.home_zone_id,
                            home_anchor_id=assignment.home_anchor_id,
                        )
                    )
                except NestPersistenceError:
                    self._nest.release_home(descriptor.actor_id)
                    return


__all__ = ("ActorDescriptor", "NestRuntimeSynchronizer")
