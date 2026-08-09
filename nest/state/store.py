"""Nest 运行状态存储。"""

from __future__ import annotations

from dataclasses import replace
from typing import Dict

from nest.state.config import NestConfig
from nest.state.models import (
    AnchorKind,
    HomeAssignment,
    ResidentState,
    RuntimeResidentMirror,
    WorldCatalog,
)


class UnknownResidentError(RuntimeError):
    """请求引用了不存在的 Nest resident。"""

    def __init__(self, elfie_id: str) -> None:
        super().__init__(elfie_id)
        self.elfie_id = elfie_id

    def __str__(self) -> str:
        return f"未知 Nest resident: {self.elfie_id}"


class NoHomeAvailableError(RuntimeError):
    """Runtime catalog 中没有可分配的空床。"""

    def __str__(self) -> str:
        return "没有可分配的 home bed"


class UnknownAnchorError(RuntimeError):
    """请求引用了不存在或不可用的 semantic anchor。"""

    def __init__(self, anchor_id: str) -> None:
        super().__init__(anchor_id)
        self.anchor_id = anchor_id

    def __str__(self) -> str:
        return f"未知或不可用 anchor: {self.anchor_id}"


class ReconciliationRequiredError(RuntimeError):
    """Runtime catalog no longer contains an assigned home."""

    def __str__(self) -> str:
        return "Nest home assignments require owner reconciliation"


class BedConflictError(RuntimeError):
    """home bed 已经被其他 resident 占用。"""

    def __init__(self, anchor_id: str, occupant_id: str) -> None:
        super().__init__(anchor_id, occupant_id)
        self.anchor_id = anchor_id
        self.occupant_id = occupant_id

    def __str__(self) -> str:
        return f"home bed {self.anchor_id} 已被 {self.occupant_id} 占用"


class NestState:  # noqa: MUTABLE_OK - 这是单个 Nest 的运行中状态容器。
    """维护居民与巢内语义状态，不持有精灵实例或引擎几何。"""

    def __init__(self, config: NestConfig) -> None:
        self.config = config
        self.residents: Dict[str, ResidentState] = {}
        self.home_assignments: Dict[str, HomeAssignment] = {}
        self.runtime_mirrors: Dict[str, RuntimeResidentMirror] = {}
        self.world_catalog: WorldCatalog | None = None
        self.reconciliation_required = False
        self.elapsed_seconds = 0.0
        self.clock_paused = False
        self.time_scale = 1.0

    def register_resident(self, elfie_id: str) -> None:
        if elfie_id in self.residents:
            return
        self.residents[elfie_id] = ResidentState(elfie_id=elfie_id)

    def remove_resident(self, elfie_id: str) -> None:
        self.residents.pop(elfie_id, None)
        self.home_assignments.pop(elfie_id, None)
        self.runtime_mirrors.pop(elfie_id, None)

    def update_resident(
        self,
        elfie_id: str,
        posture: str,
    ) -> None:
        current = self.residents.get(elfie_id)
        if current is None:
            raise UnknownResidentError(elfie_id)
        self.residents[elfie_id] = replace(
            current,
            posture=posture,
        )

    def apply_catalog(self, catalog: WorldCatalog) -> None:
        self.world_catalog = catalog
        valid_beds = self._active_bed_anchor_ids()
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
            for anchor_id in self._ordered_active_bed_anchor_ids():
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
        zone_id = self._zone_id_for_active_bed(anchor_id)
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
        if assignment is None:
            return None
        return assignment.home_anchor_id

    def apply_runtime_mirrors(
        self,
        mirrors: tuple[RuntimeResidentMirror, ...],
    ) -> None:
        self.runtime_mirrors = {
            mirror.elfie_id: mirror
            for mirror in mirrors
            if mirror.elfie_id in self.residents
        }

    def _ordered_active_bed_anchor_ids(self) -> tuple[str, ...]:
        catalog = self.world_catalog
        if catalog is None:
            return ()
        ordered = []
        for zone in sorted(catalog.zones, key=lambda item: (item.order, item.zone_id)):
            for anchor in sorted(
                zone.anchors, key=lambda item: (item.order, item.anchor_id)
            ):
                if anchor.kind is AnchorKind.BED and anchor.active:
                    ordered.append(anchor.anchor_id)
        return tuple(ordered)

    def _active_bed_anchor_ids(self) -> frozenset[str]:
        return frozenset(self._ordered_active_bed_anchor_ids())

    def _occupied_home_anchor_ids(self) -> frozenset[str]:
        return frozenset(
            assignment.home_anchor_id for assignment in self.home_assignments.values()
        )

    def _zone_id_for_active_bed(self, anchor_id: str) -> str:
        catalog = self.world_catalog
        if catalog is None:
            raise UnknownAnchorError(anchor_id)
        for zone in catalog.zones:
            for anchor in zone.anchors:
                if (
                    anchor.anchor_id == anchor_id
                    and anchor.kind is AnchorKind.BED
                    and anchor.active
                ):
                    return zone.zone_id
        raise UnknownAnchorError(anchor_id)
