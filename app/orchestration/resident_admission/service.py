"""Accepted-adoption construction, live Nest admission and compensation."""

from __future__ import annotations

import threading
from collections import OrderedDict

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
        self._admission_lock = threading.RLock()
        self._completed: OrderedDict[tuple[int, str], ResidentAdmissionResult] = (
            OrderedDict()
        )

    def admit(
        self,
        principal: AccountPrincipal,
        command: AdmitAcceptedAdoptionCommand,
    ) -> ResidentAdmissionResult:
        commit_key = (principal.user_id, command.candidate_set_id)
        with self._admission_lock:
            existing = self._completed.get(commit_key)
            if existing is not None:
                self._completed.move_to_end(commit_key)
                return existing

            reservation = self._adoption.prepare_accepted(
                principal,
                ReserveAcceptedAdoptionCommand(
                    candidate_set_id=command.candidate_set_id,
                    candidate_id=command.candidate_id,
                    name=command.name,
                    full_body_image_url=command.full_body_image_url,
                    headshot_image_url=command.headshot_image_url,
                ),
            )
            registered = False
            try:
                workspace = self._workspace.materialize(reservation)
                if self._residents is not None:
                    elfie = self._elfies.restore(reservation.elfie_id, workspace)
                    self._residents.register_elfie(reservation.elfie_id, elfie)
                    registered = True
                self._adoption.publish_accepted(reservation)
            except (
                AdoptionError,
                ResidentAdmissionPortError,
                AttributeError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ) as error:
                compensation_errors: list[Exception] = []
                runtime_removed = not registered
                if registered and self._residents is not None:
                    try:
                        self._residents.remove_elfie(reservation.elfie_id)
                        runtime_removed = True
                    except (AttributeError, OSError, RuntimeError) as cleanup_error:
                        compensation_errors.append(cleanup_error)
                if runtime_removed:
                    try:
                        self._workspace.release(reservation.elfie_id)
                    except (
                        ResidentAdmissionPortError,
                        OSError,
                        RuntimeError,
                    ) as cleanup_error:
                        compensation_errors.append(cleanup_error)
                if compensation_errors:
                    raise ResidentAdmissionCompensationFailed(
                        "领养接纳失败，且补偿未能完整完成"
                    ) from error
                if isinstance(error, AdoptionError):
                    raise
                raise ResidentAdmissionUnavailable("精灵未能加入运行时") from error
            result = ResidentAdmissionResult(
                elfie_id=reservation.elfie_id,
                name=reservation.name,
                species_id=reservation.species_id,
            )
            self._completed[commit_key] = result
            self._completed.move_to_end(commit_key)
            while len(self._completed) > 64:
                self._completed.popitem(last=False)
            return result


__all__ = ("ResidentAdmissionService",)
