from __future__ import annotations

from typing import cast

import pytest

from app.features.accounts import AccountPrincipal
from app.features.adoption import (
    AdoptionPolicyRecord,
    AdoptionQuotaRecord,
    AdoptionReservationRecord,
    AdoptionService,
    CandidateAppearance,
    CreateCandidateSetCommand,
    ReplyToCandidatesCommand,
)
from app.orchestration.resident_admission import (
    AdmitAcceptedAdoptionCommand,
    ResidentAdmissionPortError,
    ResidentAdmissionService,
    ResidentAdmissionUnavailable,
)
from elfie import Elfie


class Policy:
    def load_policy(self) -> AdoptionPolicyRecord:
        return AdoptionPolicyRecord(3, ("fox",), ("好奇探索",))


class Persistence:
    def __init__(self) -> None:
        self.released: list[str] = []

    def get_quota(self, owner_user_id: int, default_limit: int) -> AdoptionQuotaRecord:
        return AdoptionQuotaRecord(0, default_limit)

    def reserve(
        self, reservation: AdoptionReservationRecord, default_limit: int
    ) -> None:
        pass

    def release(self, elfie_id: str) -> None:
        self.released.append(elfie_id)


class Workspace:
    def __init__(self) -> None:
        self.released: list[str] = []

    def materialize(self, reservation) -> str:
        return f"/workspace/{reservation.elfie_id}"

    def release(self, elfie_id: str) -> None:
        self.released.append(elfie_id)


class Construction:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def restore(self, elfie_id: str, workspace: str) -> Elfie:
        if self.fail:
            raise ResidentAdmissionPortError("unavailable")
        return cast(Elfie, object())


class Residents:
    def __init__(self) -> None:
        self.registered: list[str] = []

    def register_elfie(self, elfie_id: str, elfie: Elfie) -> None:
        self.registered.append(elfie_id)


def _accepted(
    adoption: AdoptionService, principal: AccountPrincipal
) -> tuple[str, str]:
    candidates = adoption.create_candidate_set(
        principal,
        CreateCandidateSetCommand(
            species_id="fox",
            life_stage="any",
            gender="any",
            appearance=CandidateAppearance("any", "any", "any", "any", "face"),
            answers=("any", "any", "any", "any", "any"),
        ),
    )
    candidate_id = candidates.candidates[0].candidate_id
    adoption.reply_to_candidates(
        principal,
        ReplyToCandidatesCommand(candidates.candidate_set_id, (candidate_id,)),
    )
    return candidates.candidate_set_id, candidate_id


def test_admission_constructs_and_registers_the_accepted_elfie() -> None:
    persistence = Persistence()
    adoption = AdoptionService(Policy(), persistence)
    workspace = Workspace()
    residents = Residents()
    principal = AccountPrincipal(7, "alice", "user", "chat")
    candidate_set_id, candidate_id = _accepted(adoption, principal)
    service = ResidentAdmissionService(
        adoption,
        workspace,
        Construction(),
        residents,
    )

    result = service.admit(
        principal,
        AdmitAcceptedAdoptionCommand(candidate_set_id, candidate_id, "星砂"),
    )

    assert residents.registered == [result.elfie_id]
    assert workspace.released == []
    assert persistence.released == []


def test_failed_construction_releases_workspace_and_ownership() -> None:
    persistence = Persistence()
    adoption = AdoptionService(Policy(), persistence)
    workspace = Workspace()
    principal = AccountPrincipal(7, "alice", "user", "chat")
    candidate_set_id, candidate_id = _accepted(adoption, principal)
    service = ResidentAdmissionService(
        adoption,
        workspace,
        Construction(fail=True),
        Residents(),
    )

    with pytest.raises(ResidentAdmissionUnavailable):
        service.admit(
            principal,
            AdmitAcceptedAdoptionCommand(candidate_set_id, candidate_id, "星砂"),
        )

    assert workspace.released == persistence.released
    assert len(workspace.released) == 1
