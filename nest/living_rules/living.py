"""Resident membership, Home authority and transient physical mirrors."""

from __future__ import annotations

from dataclasses import dataclass, replace

from nest.living_rules.errors import (
    BedConflictError,
    NoHomeAvailableError,
    ReconciliationRequiredError,
    UnknownResidentError,
)
from nest.living_rules.models import (
    HomeAssignment,
    ResidentState,
    RuntimeResidentMirror,
)
from nest.space_facilities.catalog import SpaceFacilitiesState
from nest.space_facilities.models import AnchorKind, FacilityDescriptor
from nest.time_environment.models import EnvironmentDesiredState


@dataclass
class LivingRulesState:
    space: SpaceFacilitiesState
    residents: dict[str, ResidentState]
    home_assignments: dict[str, HomeAssignment]
    runtime_mirrors: dict[str, RuntimeResidentMirror]
    environment_override: EnvironmentDesiredState | None = None
    reconciliation_required: bool = False

    @classmethod
    def create(cls, space: SpaceFacilitiesState) -> LivingRulesState:
        return cls(space, {}, {}, {})

    def register_resident(self, elfie_id: str) -> None:
        if elfie_id not in self.residents:
            self.residents[elfie_id] = ResidentState(elfie_id=elfie_id)

    def remove_resident(self, elfie_id: str) -> None:
        self.residents.pop(elfie_id, None)
        self.home_assignments.pop(elfie_id, None)
        self.runtime_mirrors.pop(elfie_id, None)

    def update_resident(self, elfie_id: str, posture: str) -> None:
        current = self.residents.get(elfie_id)
        if current is None:
            raise UnknownResidentError(elfie_id)
        self.residents[elfie_id] = replace(current, posture=posture)

    def apply_catalog(self) -> None:
        valid_beds = frozenset(self.space.ordered_active_bed_anchor_ids())
        self.reconciliation_required = any(
            assignment.home_anchor_id not in valid_beds
            for assignment in self.home_assignments.values()
        )

    def admit_resident(self, elfie_id: str) -> HomeAssignment:
        if self.reconciliation_required:
            raise ReconciliationRequiredError()
        was_registered = elfie_id in self.residents
        self.register_resident(elfie_id)
        try:
            if elfie_id in self.home_assignments:
                return self.home_assignments[elfie_id]
            for anchor_id in self.space.ordered_active_bed_anchor_ids():
                if anchor_id not in self._occupied_home_anchor_ids():
                    return self.assign_home(elfie_id, anchor_id)
            raise NoHomeAvailableError()
        except NoHomeAvailableError:
            if not was_registered:
                self.remove_resident(elfie_id)
            raise

    def assign_home(self, elfie_id: str, anchor_id: str) -> HomeAssignment:
        if elfie_id not in self.residents:
            raise UnknownResidentError(elfie_id)
        zone_id = self.space.zone_id_for_active_bed(anchor_id)
        for occupant_id, assignment in self.home_assignments.items():
            if occupant_id != elfie_id and assignment.home_anchor_id == anchor_id:
                raise BedConflictError(anchor_id, occupant_id)
        assignment = HomeAssignment(
            elfie_id=elfie_id,
            home_zone_id=zone_id,
            home_anchor_id=anchor_id,
            anchor_kind=AnchorKind.BED,
        )
        self.home_assignments[elfie_id] = assignment
        return assignment

    def release_home(self, elfie_id: str) -> None:
        if elfie_id not in self.residents:
            raise UnknownResidentError(elfie_id)
        self.home_assignments.pop(elfie_id, None)

    def home_anchor_id(self, elfie_id: str) -> str | None:
        assignment = self.home_assignments.get(elfie_id)
        return assignment.home_anchor_id if assignment is not None else None

    def apply_runtime_mirrors(
        self,
        mirrors: tuple[RuntimeResidentMirror, ...],
    ) -> None:
        self.runtime_mirrors = {
            mirror.elfie_id: mirror
            for mirror in mirrors
            if mirror.elfie_id in self.residents
        }

    def clear_runtime_mirrors(self) -> None:
        self.runtime_mirrors.clear()

    def is_present(self, elfie_id: str) -> bool:
        """Whether a registered resident may participate in Nest interactions."""
        resident = self.residents.get(elfie_id)
        return resident is not None and resident.active and resident.posture != "away"

    def eligible_event_audience(
        self,
        candidate_ids: tuple[str, ...] | None = None,
        *,
        sender_id: str | None = None,
    ) -> tuple[str, ...]:
        """Apply one household audience rule to an explicit candidate set.

        Godot may only return physical candidates. Living Rules decides which
        registered, present residents may receive the semantic event. A
        missing candidate set means a Nest broadcast to all present residents.
        """
        source = candidate_ids if candidate_ids is not None else tuple(self.residents)
        return tuple(
            elfie_id
            for elfie_id in dict.fromkeys(source)
            if elfie_id != sender_id and self.is_present(elfie_id)
        )

    def home_occupant(self, anchor_id: str) -> str | None:
        """Return the resident holding the unique home reservation."""
        return next(
            (
                elfie_id
                for elfie_id, assignment in self.home_assignments.items()
                if assignment.home_anchor_id == anchor_id
            ),
            None,
        )

    def is_home_reserved(self, anchor_id: str) -> bool:
        return self.home_occupant(anchor_id) is not None

    def can_access_home(self, elfie_id: str, anchor_id: str) -> bool:
        """A home is reserved to its owner and only usable while present."""
        assignment = self.home_assignments.get(elfie_id)
        return (
            self.is_present(elfie_id)
            and assignment is not None
            and assignment.home_anchor_id == anchor_id
        )

    def can_access_shared_facility(
        self,
        elfie_id: str,
        facility: FacilityDescriptor | None,
    ) -> bool:
        """All active facilities are shared household resources in the MVP."""
        return self.is_present(elfie_id) and facility is not None and facility.active

    def authorize_semantic_target(
        self,
        *,
        elfie_id: str,
        target: str,
        resolved_anchor_id: str,
    ) -> bool:
        """Authorize a resolved semantic action without creating Body intent."""
        if target in {"home", "my_home"}:
            return self.can_access_home(elfie_id, resolved_anchor_id)

        facility_id = target.removeprefix("facility/")
        facility = self.space.facility(facility_id)
        if not (target.startswith("facility/") or target == facility_id):
            return False
        if not self.can_access_shared_facility(elfie_id, facility):
            return False
        return self.space.is_active_anchor_in_zone(
            resolved_anchor_id,
            facility.zone_id if facility is not None else None,
        )

    def set_environment_override(self, desired: EnvironmentDesiredState) -> None:
        """Set the household-wide environment decision that wins over schedules."""
        self.environment_override = desired

    def clear_environment_override(self) -> None:
        self.environment_override = None

    def _occupied_home_anchor_ids(self) -> frozenset[str]:
        return frozenset(
            assignment.home_anchor_id for assignment in self.home_assignments.values()
        )


__all__ = ("LivingRulesState",)
