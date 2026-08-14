"""Domain errors shared by the Nest owner states."""

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


class UnknownAnchorError(RuntimeError):
    def __init__(self, anchor_id: str) -> None:
        super().__init__(anchor_id)
        self.anchor_id = anchor_id

    def __str__(self) -> str:
        return f"未知或不可用 anchor: {self.anchor_id}"


class ReconciliationRequiredError(RuntimeError):
    def __str__(self) -> str:
        return "Nest home assignments require owner reconciliation"


class BedConflictError(RuntimeError):
    def __init__(self, anchor_id: str, occupant_id: str) -> None:
        super().__init__(anchor_id, occupant_id)
        self.anchor_id = anchor_id
        self.occupant_id = occupant_id

    def __str__(self) -> str:
        return f"home bed {self.anchor_id} 已被 {self.occupant_id} 占用"


__all__ = (
    "BedConflictError",
    "NoHomeAvailableError",
    "ReconciliationRequiredError",
    "UnknownAnchorError",
    "UnknownResidentError",
)
