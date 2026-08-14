"""Semantic space/facility owner; no geometry or Runtime objects."""

from __future__ import annotations

from dataclasses import dataclass

from nest.space_facilities.errors import UnknownAnchorError
from nest.space_facilities.models import (
    AnchorKind,
    EnvironmentActualState,
    FacilityDescriptor,
    WorldCatalog,
)


@dataclass
class SpaceFacilitiesState:
    world_catalog: WorldCatalog | None = None
    environment_actual: EnvironmentActualState | None = None

    def apply_catalog(self, catalog: WorldCatalog) -> None:
        self.world_catalog = catalog

    def apply_environment_actual(self, actual: EnvironmentActualState) -> None:
        """Record the Runtime fact for the addressed physical environment group."""
        self.environment_actual = actual

    def clear_runtime_projections(self) -> None:
        self.environment_actual = None

    def facility(self, facility_id: str) -> FacilityDescriptor | None:
        if self.world_catalog is None:
            return None
        return next(
            (
                facility
                for facility in self.world_catalog.facilities
                if facility.facility_id == facility_id and facility.active
            ),
            None,
        )

    def facilities(self) -> tuple[FacilityDescriptor, ...]:
        if self.world_catalog is None:
            return ()
        return tuple(
            facility for facility in self.world_catalog.facilities if facility.active
        )

    def ordered_active_bed_anchor_ids(self) -> tuple[str, ...]:
        if self.world_catalog is None:
            return ()
        ordered: list[str] = []
        for zone in sorted(
            self.world_catalog.zones,
            key=lambda item: (item.order, item.zone_id),
        ):
            for anchor in sorted(
                zone.anchors,
                key=lambda item: (item.order, item.anchor_id),
            ):
                if anchor.kind is AnchorKind.BED and anchor.active:
                    ordered.append(anchor.anchor_id)
        return tuple(ordered)

    def zone_id_for_active_bed(self, anchor_id: str) -> str:
        if self.world_catalog is not None:
            for zone in self.world_catalog.zones:
                for anchor in zone.anchors:
                    if (
                        anchor.anchor_id == anchor_id
                        and anchor.kind is AnchorKind.BED
                        and anchor.active
                    ):
                        return zone.zone_id
        raise UnknownAnchorError(anchor_id)

    def is_active_anchor_in_zone(
        self,
        anchor_id: str,
        zone_id: str | None,
    ) -> bool:
        if zone_id is None or self.world_catalog is None:
            return False
        return any(
            anchor.anchor_id == anchor_id and anchor.active and zone.zone_id == zone_id
            for zone in self.world_catalog.zones
            for anchor in zone.anchors
        )


__all__ = ("SpaceFacilitiesState",)
