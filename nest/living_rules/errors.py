"""Errors owned by Household Living Rules."""

from __future__ import annotations


class UnknownResidentError(RuntimeError):
    def __init__(self, elfie_id: str) -> None:
        super().__init__(elfie_id)
        self.elfie_id = elfie_id

    def __str__(self) -> str:
        return f"未知 Nest resident: {self.elfie_id}"


class NoHomeAvailableError(RuntimeError):
    def __str__(self) -> str:
        return "没有可分配的 home bed"


class ReconciliationRequiredError(RuntimeError):
    def __str__(self) -> str:
        return "Nest home assignments require owner reconciliation"


class BedCapacityError(RuntimeError):
    def __init__(
        self,
        bed_count: int,
        resident_count: int,
        invalid_home_anchor_ids: tuple[str, ...] = (),
    ) -> None:
        super().__init__(bed_count, resident_count, invalid_home_anchor_ids)
        self.bed_count = bed_count
        self.resident_count = resident_count
        self.invalid_home_anchor_ids = invalid_home_anchor_ids

    def __str__(self) -> str:
        if self.invalid_home_anchor_ids:
            anchors = ", ".join(self.invalid_home_anchor_ids)
            return f"bed_count {self.bed_count} would remove assigned homes: {anchors}"
        return (
            f"bed_count {self.bed_count} is below resident count {self.resident_count}"
        )


class BedConflictError(RuntimeError):
    def __init__(self, anchor_id: str, occupant_id: str) -> None:
        super().__init__(anchor_id, occupant_id)
        self.anchor_id = anchor_id
        self.occupant_id = occupant_id

    def __str__(self) -> str:
        return f"home bed {self.anchor_id} 已被 {self.occupant_id} 占用"


__all__ = (
    "BedCapacityError",
    "BedConflictError",
    "NoHomeAvailableError",
    "ReconciliationRequiredError",
    "UnknownResidentError",
)
