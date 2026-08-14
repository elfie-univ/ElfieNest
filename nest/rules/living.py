"""Resident membership, Home authority and transient physical mirrors."""

from __future__ import annotations

from dataclasses import dataclass, replace

from nest.space.catalog import SpaceFacilitiesState
from nest.state.errors import (
    BedConflictError,
    NoHomeAvailableError,
    ReconciliationRequiredError,
    UnknownResidentError,
)
from nest.state.models import (
    AnchorKind,
    HomeAssignment,
    ResidentState,
    RuntimeResidentMirror,
)


@dataclass
class LivingRulesState:
    space: SpaceFacilitiesState
    residents: dict[str, ResidentState]
    home_assignments: dict[str, HomeAssignment]
    runtime_mirrors: dict[str, RuntimeResidentMirror]
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

    def _occupied_home_anchor_ids(self) -> frozenset[str]:
        return frozenset(
            assignment.home_anchor_id for assignment in self.home_assignments.values()
        )


__all__ = ("LivingRulesState",)
