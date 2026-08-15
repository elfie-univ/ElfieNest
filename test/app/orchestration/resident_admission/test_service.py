from __future__ import annotations

from typing import cast

import pytest

from app.features.accounts import AccountPrincipal
from app.features.adoption import (
    AdoptionPolicyRecord,
    AdoptionPortError,
    AdoptionQuotaRecord,
    AdoptionReservationRecord,
    AdoptionService,
    AdoptionUnavailable,
    CandidateAppearance,
    CandidateReveal,
    CreateCandidateSetCommand,
    ReplyToCandidatesCommand,
)
from app.orchestration.resident_admission import (
    AdmitAcceptedAdoptionCommand,
    ResidentAdmissionCompensationFailed,
    ResidentAdmissionPortError,
    ResidentAdmissionService,
    ResidentAdmissionUnavailable,
)
from elfie import Elfie


class Policy:
    def load_policy(self) -> AdoptionPolicyRecord:
        return AdoptionPolicyRecord(3, ("好奇探索",))


class Persistence:
    def __init__(self, events: list[str], *, fail: bool = False) -> None:
        self.events = events
        self.fail = fail
        self.reservations: list[AdoptionReservationRecord] = []
        self.released: list[str] = []

    def get_quota(self, owner_user_id: int, default_limit: int) -> AdoptionQuotaRecord:
        return AdoptionQuotaRecord(0, default_limit)

    def reserve(
        self, reservation: AdoptionReservationRecord, default_limit: int
    ) -> None:
        self.events.append("database")
        if self.fail:
            raise AdoptionPortError("unavailable")
        self.reservations.append(reservation)

    def release(self, elfie_id: str) -> None:
        self.released.append(elfie_id)


class Narrative:
    def is_ready(self) -> bool:
        return True

    def reveal(self, candidate, invitation_message: str) -> CandidateReveal:
        return CandidateReveal("Vulpes", "小狐", "我喜欢在安静的地方慢慢观察世界。")

    def reveal_many(self, candidates, invitation_message: str):
        return {
            candidate.candidate_id: self.reveal(candidate, invitation_message)
            for candidate in candidates
        }


class Workspace:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.released: list[str] = []

    def materialize(self, reservation) -> str:
        self.events.append("workspace")
        return f"/workspace/{reservation.elfie_id}"

    def release(self, elfie_id: str) -> None:
        self.events.append("workspace-release")
        self.released.append(elfie_id)


class Construction:
    def __init__(self, events: list[str], *, fail: bool = False) -> None:
        self.events = events
        self.fail = fail

    def restore(self, elfie_id: str, workspace: str) -> Elfie:
        self.events.append("restore")
        if self.fail:
            raise ResidentAdmissionPortError("unavailable")
        return cast(Elfie, object())


class Residents:
    def __init__(
        self,
        events: list[str],
        *,
        fail_register: bool = False,
        fail_remove: bool = False,
    ) -> None:
        self.events = events
        self.fail_register = fail_register
        self.fail_remove = fail_remove
        self.registered: list[str] = []

    def register_elfie(self, elfie_id: str, elfie: Elfie) -> None:
        self.events.append("runtime")
        if self.fail_register:
            raise RuntimeError("register unavailable")
        self.registered.append(elfie_id)

    def remove_elfie(self, elfie_id: str) -> None:
        self.events.append("runtime-remove")
        if self.fail_remove:
            raise RuntimeError("remove unavailable")
        self.registered.remove(elfie_id)


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
    events: list[str] = []
    persistence = Persistence(events)
    adoption = AdoptionService(Policy(), persistence, narrative=Narrative())
    workspace = Workspace(events)
    residents = Residents(events)
    principal = AccountPrincipal(7, "alice", "user", "chat")
    candidate_set_id, candidate_id = _accepted(adoption, principal)
    service = ResidentAdmissionService(
        adoption,
        workspace,
        Construction(events),
        residents,
    )

    result = service.admit(
        principal,
        AdmitAcceptedAdoptionCommand(candidate_set_id, candidate_id, "星砂"),
    )

    assert residents.registered == [result.elfie_id]
    assert workspace.released == []
    assert persistence.released == []
    assert events == ["workspace", "restore", "runtime", "database"]

    repeated = service.admit(
        principal,
        AdmitAcceptedAdoptionCommand(candidate_set_id, candidate_id, "另一个名字"),
    )
    assert repeated == result
    assert residents.registered == [result.elfie_id]
    assert events == ["workspace", "restore", "runtime", "database"]


def test_failed_construction_releases_workspace_and_ownership() -> None:
    events: list[str] = []
    persistence = Persistence(events)
    adoption = AdoptionService(Policy(), persistence, narrative=Narrative())
    workspace = Workspace(events)
    principal = AccountPrincipal(7, "alice", "user", "chat")
    candidate_set_id, candidate_id = _accepted(adoption, principal)
    service = ResidentAdmissionService(
        adoption,
        workspace,
        Construction(events, fail=True),
        Residents(events),
    )

    with pytest.raises(ResidentAdmissionUnavailable):
        service.admit(
            principal,
            AdmitAcceptedAdoptionCommand(candidate_set_id, candidate_id, "星砂"),
        )

    assert len(workspace.released) == 1
    assert persistence.reservations == []
    assert persistence.released == []
    assert events == ["workspace", "restore", "workspace-release"]


def test_failed_final_insert_removes_runtime_before_releasing_workspace() -> None:
    events: list[str] = []
    persistence = Persistence(events, fail=True)
    adoption = AdoptionService(Policy(), persistence, narrative=Narrative())
    workspace = Workspace(events)
    residents = Residents(events)
    principal = AccountPrincipal(7, "alice", "user", "chat")
    candidate_set_id, candidate_id = _accepted(adoption, principal)
    service = ResidentAdmissionService(
        adoption,
        workspace,
        Construction(events),
        residents,
    )

    with pytest.raises(AdoptionUnavailable):
        service.admit(
            principal,
            AdmitAcceptedAdoptionCommand(candidate_set_id, candidate_id, "星砂"),
        )

    assert residents.registered == []
    assert persistence.reservations == []
    assert events == [
        "workspace",
        "restore",
        "runtime",
        "database",
        "runtime-remove",
        "workspace-release",
    ]


def test_failed_runtime_registration_never_publishes_the_elfie() -> None:
    events: list[str] = []
    persistence = Persistence(events)
    adoption = AdoptionService(Policy(), persistence, narrative=Narrative())
    workspace = Workspace(events)
    principal = AccountPrincipal(7, "alice", "user", "chat")
    candidate_set_id, candidate_id = _accepted(adoption, principal)
    service = ResidentAdmissionService(
        adoption,
        workspace,
        Construction(events),
        Residents(events, fail_register=True),
    )

    with pytest.raises(ResidentAdmissionUnavailable):
        service.admit(
            principal,
            AdmitAcceptedAdoptionCommand(candidate_set_id, candidate_id, "星砂"),
        )

    assert persistence.reservations == []
    assert events == ["workspace", "restore", "runtime", "workspace-release"]


def test_failed_runtime_cleanup_preserves_its_workspace() -> None:
    events: list[str] = []
    persistence = Persistence(events, fail=True)
    adoption = AdoptionService(Policy(), persistence, narrative=Narrative())
    workspace = Workspace(events)
    residents = Residents(events, fail_remove=True)
    principal = AccountPrincipal(7, "alice", "user", "chat")
    candidate_set_id, candidate_id = _accepted(adoption, principal)
    service = ResidentAdmissionService(
        adoption,
        workspace,
        Construction(events),
        residents,
    )

    with pytest.raises(ResidentAdmissionCompensationFailed):
        service.admit(
            principal,
            AdmitAcceptedAdoptionCommand(candidate_set_id, candidate_id, "星砂"),
        )

    assert workspace.released == []
    assert len(residents.registered) == 1
    assert events == ["workspace", "restore", "runtime", "database", "runtime-remove"]
