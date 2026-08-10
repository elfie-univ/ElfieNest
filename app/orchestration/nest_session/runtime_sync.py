"""Deterministic desired-state synchronization with the Godot Runtime."""

from __future__ import annotations

from collections.abc import Callable

from app.orchestration.nest_session.models import (
    ActorDescriptor,
    ResidentMirror,
    RuntimeActor,
    SceneManifest,
    SemanticWorldCatalog,
    WorldEvent,
    WorldEventName,
    WorldSnapshot,
)
from app.orchestration.nest_session.ports import WorldRuntimePort
from nest import Nest
from nest.state.models import (
    AnchorKind,
    InteractionAnchor,
    PersistentResidentState,
    ResidentPresence,
    RuntimeResidentMirror,
    WorldCatalog,
    ZoneDescriptor,
)
from nest.state.repository import NestPersistenceError, NestRepository
from nest.state.store import BedConflictError, NoHomeAvailableError, UnknownAnchorError

ActorCatalogProvider = Callable[[], tuple[ActorDescriptor, ...]]


class NestRuntimeSynchronizer:
    """Merge desired residents until one authoritative Runtime is ready."""

    def __init__(
        self,
        *,
        nest: Nest,
        world_runtime: WorldRuntimePort,
        actor_catalog_provider: ActorCatalogProvider,
        desired_bed_count: int = 4,
        repository: NestRepository | None = None,
    ) -> None:
        self._nest = nest
        self._world_runtime = world_runtime
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
        connection = self._world_runtime.runtime_connection
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
        self._world_runtime.configure_world(
            nest_id=self._nest.state.config.nest_id,
            bed_count=self._desired_bed_count,
            world_revision=self._desired_world_revision,
        )

    def consume(self, event: WorldEvent) -> None:
        connection = self._world_runtime.runtime_connection
        if connection is None:
            return
        if (
            event.connection.runtime_id != connection.runtime_id
            or event.connection.generation != connection.generation
        ):
            return
        if event.name is WorldEventName.SCENE_MANIFEST:
            if (
                self._manifest_revision is not None
                and event.world_revision <= self._manifest_revision
            ):
                return
            if not isinstance(event.payload, SceneManifest):
                return
            catalog = _nest_catalog(event.payload.catalog)
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
        elif event.name is WorldEventName.WORLD_READY:
            if self._manifest_revision == event.world_revision:
                self._ready_revision = event.world_revision
        elif event.name is WorldEventName.WORLD_SNAPSHOT:
            if not isinstance(event.payload, WorldSnapshot):
                return
            revision = event.payload.revision
            mirrors = tuple(_nest_mirror(mirror) for mirror in event.payload.residents)
            if revision == event.world_revision and revision == self._ready_revision:
                self._nest.apply_runtime_mirrors(mirrors)

    def flush(self) -> None:
        if not self._actor_catalog_dirty:
            return
        if self._ready_revision is None or self._nest.state.reconciliation_required:
            return
        actors: list[RuntimeActor] = []
        for descriptor in self._actor_catalog_provider():
            home_anchor_id = self._nest.home_anchor_id(descriptor.actor_id)
            if home_anchor_id is None:
                return
            actors.append(
                RuntimeActor(
                    actor_id=descriptor.actor_id,
                    species=descriptor.species,
                    appearance=descriptor.appearance,
                    home_anchor_id=home_anchor_id,
                )
            )
        command_id = self._world_runtime.synchronize_actors(
            tuple(actors),
            world_revision=self._ready_revision,
        )
        if command_id is not None:
            self._actor_catalog_dirty = False

    def _assign_missing_homes(self) -> None:
        persisted = self._persisted_home_assignments()
        for descriptor in self._actor_catalog_provider():
            if self._nest.home_anchor_id(descriptor.actor_id) is None:
                saved = persisted.get(descriptor.actor_id)
                if saved is not None and saved.home_anchor_id is not None:
                    try:
                        assignment = self._nest.assign_home(
                            descriptor.actor_id,
                            saved.home_anchor_id,
                        )
                    except (BedConflictError, UnknownAnchorError):
                        self._nest.state.reconciliation_required = True
                        return
                else:
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

    def _persisted_home_assignments(
        self,
    ) -> dict[str, PersistentResidentState]:
        if self._repository is None:
            return {}
        return self._repository.load_home_assignments()


__all__ = ("ActorDescriptor", "NestRuntimeSynchronizer")


def _nest_catalog(catalog: SemanticWorldCatalog) -> WorldCatalog:
    return WorldCatalog(
        nest_id=catalog.nest_id,
        revision=catalog.revision,
        zones=tuple(
            ZoneDescriptor(
                zone_id=zone.zone_id,
                label=zone.label,
                order=zone.order,
                anchors=tuple(
                    InteractionAnchor(
                        anchor_id=anchor.anchor_id,
                        kind=AnchorKind(anchor.kind),
                        label=anchor.label,
                        order=anchor.order,
                        active=anchor.active,
                    )
                    for anchor in zone.anchors
                ),
            )
            for zone in catalog.zones
        ),
    )


def _nest_mirror(mirror: ResidentMirror) -> RuntimeResidentMirror:
    return RuntimeResidentMirror(
        elfie_id=mirror.elfie_id,
        current_zone_id=mirror.current_zone_id,
        posture=mirror.posture,
        active_command_id=mirror.active_command_id,
    )
