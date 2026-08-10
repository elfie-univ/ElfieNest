"""Outbound Ports consumed by Resident Admission."""

from __future__ import annotations

from typing import Protocol

from app.features.adoption import AcceptedAdoptionReservation
from elfie import Elfie


class ResidentAdmissionPortError(RuntimeError):
    """A technical admission boundary failed."""


class ResidentWorkspacePort(Protocol):
    def materialize(self, reservation: AcceptedAdoptionReservation) -> str: ...

    def release(self, elfie_id: str) -> None: ...


class ElfieConstructionPort(Protocol):
    def restore(self, elfie_id: str, workspace: str) -> Elfie: ...


class ResidentSessionPort(Protocol):
    def register_elfie(self, elfie_id: str, elfie: Elfie) -> None: ...


__all__ = (
    "ElfieConstructionPort",
    "ResidentAdmissionPortError",
    "ResidentSessionPort",
    "ResidentWorkspacePort",
)
