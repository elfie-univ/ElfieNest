"""Accepted-adoption construction, live Nest admission and compensation."""

from __future__ import annotations

from app.features.accounts import AccountPrincipal
from app.features.adoption import (
    AdoptionError,
    AdoptionService,
    ReserveAcceptedAdoptionCommand,
)

from .errors import (
    ResidentAdmissionCompensationFailed,
    ResidentAdmissionUnavailable,
)
from .models import AdmitAcceptedAdoptionCommand, ResidentAdmissionResult
from .ports import (
    ElfieConstructionPort,
    ResidentAdmissionPortError,
    ResidentSessionPort,
    ResidentWorkspacePort,
)


class ResidentAdmissionService:
    """Coordinate only the existing accepted-adoption admission workflow."""

    def __init__(
        self,
        adoption: AdoptionService,
        workspace: ResidentWorkspacePort,
        elfies: ElfieConstructionPort,
        residents: ResidentSessionPort | None,
    ) -> None:
        self._adoption = adoption
        self._workspace = workspace
        self._elfies = elfies
        self._residents = residents

    def admit(
        self,
        principal: AccountPrincipal,
        command: AdmitAcceptedAdoptionCommand,
    ) -> ResidentAdmissionResult:
        reservation = self._adoption.reserve_accepted(
            principal,
            ReserveAcceptedAdoptionCommand(
                candidate_set_id=command.candidate_set_id,
                candidate_id=command.candidate_id,
                name=command.name,
            ),
        )
        try:
            workspace = self._workspace.materialize(reservation)
            if self._residents is not None:
                elfie = self._elfies.restore(reservation.elfie_id, workspace)
                self._residents.register_elfie(reservation.elfie_id, elfie)
        except (
            ResidentAdmissionPortError,
            AttributeError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as error:
            compensation_errors: list[Exception] = []
            try:
                self._workspace.release(reservation.elfie_id)
            except (ResidentAdmissionPortError, OSError, RuntimeError) as cleanup_error:
                compensation_errors.append(cleanup_error)
            try:
                self._adoption.release_reservation(reservation)
            except AdoptionError as cleanup_error:
                compensation_errors.append(cleanup_error)
            if compensation_errors:
                raise ResidentAdmissionCompensationFailed(
                    "领养接纳失败，且补偿未能完整完成"
                ) from error
            raise ResidentAdmissionUnavailable("精灵未能加入运行时") from error
        return ResidentAdmissionResult(
            elfie_id=reservation.elfie_id,
            name=reservation.name,
            species_id=reservation.species_id,
        )


__all__ = ("ResidentAdmissionService",)
