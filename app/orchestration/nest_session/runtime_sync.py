"""Deterministic desired-state synchronization with the Godot Runtime."""

from __future__ import annotations

from collections.abc import Callable

from app.orchestration.nest_session.models import (
    ActorDescriptor,
    ResidentMirror,
    RuntimeActor,
    SceneManifest,
    SemanticWorldCatalog,
    WorldConfigured,
    WorldEvent,
    WorldEventName,
    WorldSnapshot,
)
from app.orchestration.nest_session.ports import (
    NestStateStoreError,
    NestStateStorePort,
    WorldSynchronizationPort,
)
from nest.public import (
    AnchorKind,
    BedConflictError,
    FacilityDescriptor,
    FacilityKind,
    InteractionAnchor,
    Nest,
    NestSnapshot,
    NoHomeAvailableError,
    PersistentResidentState,
    RuntimeResidentMirror,
    UnknownAnchorError,
    WorldCatalog,
    ZoneDescriptor,
)
from nest.public import (
    RuntimeMockMotion as NestRuntimeMockMotion,
)

ActorCatalogProvider = Callable[[], tuple[ActorDescriptor, ...]]


class NestRuntimeSynchronizer:
    """Merge desired residents until one authoritative Runtime is ready."""

    def __init__(
        self,
        *,
        nest: Nest,
        world_runtime: WorldSynchronizationPort,
        actor_catalog_provider: ActorCatalogProvider,
        state_store: NestStateStorePort | None = None,
    ) -> None:
        self._nest = nest
        self._world_runtime = world_runtime
        self._actor_catalog_provider = actor_catalog_provider
        self._state_store = state_store
        catalog = nest.world_catalog
        catalog_revision = 0 if catalog is None else catalog.revision
        catalog_matches_desired = (
            catalog is not None and _active_bed_count(catalog) == nest.desired_bed_count
        )
        self._desired_world_revision = max(
            1,
            catalog_revision if catalog_matches_desired else catalog_revision + 1,
        )
        self._minimum_world_revision = self._desired_world_revision
        self._observed_connection: tuple[str, int] | None = None
        self._manifest_revision: int | None = None
        self._configured_revision: int | None = None
        self._configuration_pending = True
        self._bed_count_change_pending = (
            nest.desired_bed_count != nest.config.bed_count
            if catalog is None
            else not catalog_matches_desired
        )
        self._actor_catalog_dirty = True

    def mark_actor_catalog_dirty(self) -> None:
        self._actor_catalog_dirty = True

    def request_world_reconfiguration(self) -> None:
        """Schedule one newer world revision using the live Nest desired state."""
        catalog = self._nest.world_catalog
        catalog_revision = 0 if catalog is None else catalog.revision
        self._desired_world_revision = (
            max(
                self._desired_world_revision,
                self._manifest_revision or 0,
                self._configured_revision or 0,
                catalog_revision,
            )
            + 1
        )
        self._minimum_world_revision = self._desired_world_revision
        self._manifest_revision = None
        self._configured_revision = None
        self._configuration_pending = True
        self._bed_count_change_pending = True
        self._actor_catalog_dirty = True
        self._nest.invalidate_runtime_state()

    @property
    def configured_revision(self) -> int | None:
        return self._configured_revision

    def poll_connection(self) -> None:
        connection = self._world_runtime.runtime_connection
        if connection is None:
            self._observed_connection = None
            self._manifest_revision = None
            self._configured_revision = None
            self._configuration_pending = True
            return
        token = (connection.runtime_id, connection.generation)
        if token != self._observed_connection:
            self._observed_connection = token
            self._manifest_revision = None
            self._configured_revision = None
            self._configuration_pending = True
            self._actor_catalog_dirty = True
        if not self._configuration_pending:
            return
        command_id = self._world_runtime.configure_world(
            nest_id=self._nest.config.nest_id,
            bed_count=self._nest.desired_bed_count,
            world_revision=self._desired_world_revision,
        )
        if command_id is not None:
            self._configuration_pending = False

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
            if event.world_revision < self._minimum_world_revision:
                return
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
            if (
                self._bed_count_change_pending
                and _active_bed_count(catalog) != self._nest.desired_bed_count
            ):
                self._configuration_pending = True
                return
            revision_changed = (
                self._manifest_revision is not None
                and event.world_revision != self._manifest_revision
            )
            previous_snapshot = self._nest.export_snapshot()
            if revision_changed:
                self._nest.invalidate_runtime_state()
                self._configured_revision = None
            self._nest.apply_catalog(catalog)
            self._manifest_revision = catalog.revision
            self._desired_world_revision = max(
                self._desired_world_revision,
                catalog.revision,
            )
            self._minimum_world_revision = max(
                self._minimum_world_revision,
                catalog.revision,
            )
            self._bed_count_change_pending = False
            try:
                self._assign_missing_homes()
            except NoHomeAvailableError:
                self._nest.set_reconciliation_required(True)
                return
            if not self._save_snapshot(previous_snapshot):
                return
            self._actor_catalog_dirty = True
        elif event.name is WorldEventName.WORLD_CONFIGURED:
            if (
                isinstance(event.payload, WorldConfigured)
                and event.payload.configured
                and event.payload.navigation_ready
                and self._manifest_revision == event.world_revision
            ):
                self._configured_revision = event.world_revision
        elif event.name is WorldEventName.WORLD_SNAPSHOT:
            if not isinstance(event.payload, WorldSnapshot):
                return
            revision = event.payload.revision
            if not (
                revision == event.world_revision
                and revision == self._configured_revision
            ):
                return
            mirrors = tuple(
                _nest_mirror(
                    mirror,
                    runtime_id=event.connection.runtime_id,
                    runtime_generation=event.connection.generation,
                    world_revision=event.world_revision,
                )
                for mirror in event.payload.residents
            )
            self._nest.apply_runtime_mirrors(mirrors)

    def flush(self) -> None:
        if not self._actor_catalog_dirty:
            return
        if self._configured_revision is None or self._nest.reconciliation_required:
            return
        actors: list[RuntimeActor] = []
        for descriptor in self._actor_catalog_provider():
            spawn_anchor_id = self._nest.home_anchor_id(descriptor.actor_id)
            if spawn_anchor_id is None:
                return
            actors.append(
                RuntimeActor(
                    actor_id=descriptor.actor_id,
                    species=descriptor.species,
                    appearance=descriptor.appearance,
                    spawn_anchor_id=spawn_anchor_id,
                )
            )
        command_id = self._world_runtime.synchronize_actors(
            tuple(actors),
            world_revision=self._configured_revision,
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
                        self._nest.assign_home(
                            descriptor.actor_id,
                            saved.home_anchor_id,
                        )
                    except (BedConflictError, UnknownAnchorError):
                        self._nest.set_reconciliation_required(True)
                        return
                else:
                    self._nest.admit_resident(descriptor.actor_id)

    def _save_snapshot(self, previous: NestSnapshot) -> bool:
        if self._state_store is None:
            return True
        try:
            self._state_store.save_snapshot(self._nest.export_snapshot())
        except NestStateStoreError:
            self._nest.restore_snapshot(previous)
            return False
        return True

    def _persisted_home_assignments(
        self,
    ) -> dict[str, PersistentResidentState]:
        if self._state_store is None:
            return {}
        return {
            resident.elfie_id: resident
            for resident in self._state_store.load_snapshot().residents
            if resident.home_anchor_id is not None
        }


__all__ = ("ActorDescriptor", "NestRuntimeSynchronizer")


def _active_bed_count(catalog: WorldCatalog) -> int:
    return sum(
        1
        for zone in catalog.zones
        for anchor in zone.anchors
        if anchor.kind is AnchorKind.BED and anchor.active
    )


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
        facilities=tuple(
            FacilityDescriptor(
                facility_id=facility.facility_id,
                zone_id=facility.zone_id,
                kind=FacilityKind(facility.kind),
                label=facility.label,
                capabilities=facility.capabilities,
                active=facility.active,
            )
            for facility in catalog.facilities
        ),
    )


def _nest_mirror(
    mirror: ResidentMirror,
    *,
    runtime_id: str,
    runtime_generation: int,
    world_revision: int,
) -> RuntimeResidentMirror:
    return RuntimeResidentMirror(
        elfie_id=mirror.elfie_id,
        current_zone_id=mirror.current_zone_id,
        posture=mirror.posture,
        active_command_id=mirror.active_command_id,
        mock_motion=(
            NestRuntimeMockMotion(
                waypoint=mirror.mock_motion.waypoint,
                sequence=mirror.mock_motion.sequence,
            )
            if mirror.mock_motion is not None
            else None
        ),
        runtime_id=runtime_id,
        runtime_generation=runtime_generation,
        world_revision=world_revision,
    )
