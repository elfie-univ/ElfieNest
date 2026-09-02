from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from app.features.accounts import AccountPrincipal
from app.features.adoption import (
    AdoptionPolicyRecord,
    AdoptionPortError,
    AdoptionQuotaRecord,
    AdoptionService,
    CandidateAppearance,
    CreateCandidateSetCommand,
    ReplyToCandidatesCommand,
)
from app.orchestration.resident_admission import (
    ADMISSION_TRANSITIONS,
    AdmissionPublication,
    AdmissionRecord,
    AdmissionReservation,
    AdmitAcceptedAdoptionCommand,
    ResidentAdmissionPortError,
    ResidentAdmissionService,
    ResidentAdmissionUnavailable,
    idempotency_key_digest,
)
from elfie import Elfie
from elfie.genesis import (
    GenesisCompilation,
    GenesisCompileEnvelope,
    GenesisCompileInput,
    GenesisCompiler,
    output_ids_hash,
)
from infrastructure.persistence.configuration.species import (
    load_and_configure_species_catalog,
)
from infrastructure.persistence.configuration.world import load_genesis_source_package


class Policy:
    def load_policy(self) -> AdoptionPolicyRecord:
        return AdoptionPolicyRecord(3, ("好奇探索",))


class AdoptionPersistence:
    def get_quota(self, owner_user_id: int, default_limit: int) -> AdoptionQuotaRecord:
        return AdoptionQuotaRecord(0, default_limit)

    def get_nest_capacity(self):
        return type("Capacity", (), {"used": 0, "maximum": 8})()


class AdmissionStore:
    def __init__(self, events: list[str], *, fail_reserve: bool = False) -> None:
        self.events = events
        self.records: dict[str, AdmissionRecord] = {}
        self.fail_reserve = fail_reserve

    def reserve(
        self, reservation: AdmissionReservation, default_limit: int
    ) -> AdmissionRecord:
        del default_limit
        self.events.append("database:reserve")
        if self.fail_reserve:
            raise AdoptionPortError("database unavailable")
        current = self.records.get(reservation.admission_id)
        if current is not None:
            return current
        record = AdmissionRecord(
            admission_id=reservation.admission_id,
            idempotency_key_digest=reservation.idempotency_key_digest,
            elfie_id=reservation.elfie_id,
            owner_user_id=reservation.owner_user_id,
            state="reserved",
            display_name=reservation.display_name,
            species_id=reservation.species_id,
            gender=reservation.gender,
            age_years=reservation.age_years,
            candidate_set_id=reservation.candidate_set_id,
            candidate_id=reservation.candidate_id,
            adoption_anchor_at=reservation.adoption_anchor_at,
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )
        self.records[record.admission_id] = record
        return record

    def get(self, admission_id: str) -> AdmissionRecord | None:
        return self.records.get(admission_id)

    def list_incomplete(self) -> tuple[AdmissionRecord, ...]:
        return tuple(
            record
            for record in self.records.values()
            if record.state not in {"committed", "aborted"}
        )

    def transition(
        self,
        admission_id: str,
        expected_state: str,
        next_state: str,
        **metadata: object,
    ) -> AdmissionRecord:
        self.events.append(f"database:{next_state}")
        record = self.records[admission_id]
        if record.state == next_state:
            return record
        assert record.state == expected_state
        assert next_state in ADMISSION_TRANSITIONS[expected_state]  # type: ignore[index]
        values = {key: value for key, value in metadata.items() if value is not None}
        record = replace(record, state=cast(object, next_state), **values)
        self.records[admission_id] = record
        return record

    def commit(
        self, admission_id: str, publication: AdmissionPublication
    ) -> AdmissionRecord:
        self.events.append("database:commit")
        record = self.records[admission_id]
        if record.state == "committed":
            return record
        assert record.state == "publishing"
        record = replace(
            record,
            state="committed",
            manifest_id=publication.manifest_id,
            content_hash=publication.content_hash,
            output_ids_hash=publication.output_ids_hash,
            compiler_version=publication.compiler_version,
            schema_version=publication.schema_version,
            runtime_status="offline",
            display_name=None,
            species_id=None,
            gender=None,
            age_years=None,
            candidate_set_id=None,
            candidate_id=None,
            adoption_anchor_at=None,
            committed_at="2026-01-01T00:00:01+00:00",
        )
        self.records[admission_id] = record
        return record

    def abort(self, admission_id: str, *, error_code: str) -> AdmissionRecord:
        self.events.append("database:abort")
        record = self.records[admission_id]
        record = replace(
            record,
            state="aborted",
            error_code=error_code,
            display_name=None,
            species_id=None,
            gender=None,
            age_years=None,
            candidate_set_id=None,
            candidate_id=None,
            adoption_anchor_at=None,
            runtime_status="offline",
        )
        self.records[admission_id] = record
        return record

    def mark_runtime_registered(self, admission_id: str) -> AdmissionRecord:
        self.events.append("database:runtime-registered")
        record = replace(self.records[admission_id], runtime_status="registered")
        self.records[admission_id] = record
        return record


class Workspace:
    def __init__(self, events: list[str], *, fail_stage: bool = False) -> None:
        self.events = events
        self.fail_stage = fail_stage
        self.compilation: GenesisCompilation | None = None
        self.envelope: GenesisCompileEnvelope | None = None
        self.published = False
        self.aborted = False

    def stage(self, compilation: GenesisCompilation) -> str:
        self.events.append("workspace:stage")
        if self.fail_stage:
            raise ResidentAdmissionPortError("workspace unavailable")
        self.compilation = compilation
        return "/staging/elfie"

    def stage_envelope(self, envelope: GenesisCompileEnvelope) -> str:
        self.events.append("workspace:stage-envelope")
        self.envelope = envelope
        return "/staging/elfie/.genesis-compile-envelope.json"

    def load_envelope(self, elfie_id: str):
        del elfie_id
        return self.envelope

    def clear_envelope(self, elfie_id: str) -> None:
        del elfie_id
        self.envelope = None

    def reopen(self, elfie_id: str, **expected: object) -> str:
        del elfie_id, expected
        self.events.append("workspace:reopen")
        if self.compilation is None:
            raise ResidentAdmissionPortError("staged output missing")
        return "/final/elfie" if self.published else "/staging/elfie"

    def publication(self, elfie_id: str) -> AdmissionPublication:
        del elfie_id
        assert self.compilation is not None
        manifest = self.compilation.bundle.manifest
        return AdmissionPublication(
            manifest_id=manifest.manifest_id,
            content_hash=manifest.content_hash,
            output_ids_hash=output_ids_hash(manifest.output_ids),
            compiler_version=manifest.compiler_version,
            schema_version=manifest.schema_version,
        )

    def publish(self, elfie_id: str) -> str:
        del elfie_id
        self.events.append("workspace:publish")
        if self.compilation is None:
            raise ResidentAdmissionPortError("staged output missing")
        self.published = True
        return "/final/elfie"

    def final_workspace(self, elfie_id: str) -> str:
        del elfie_id
        return "/final/elfie"

    def load_profile(self, elfie_id: str):
        del elfie_id
        assert self.compilation is not None
        return self.compilation.profile

    def abort(self, elfie_id: str) -> None:
        del elfie_id
        self.events.append("workspace:abort")
        if self.published:
            raise ResidentAdmissionPortError("final workspace already published")
        self.aborted = True
        self.compilation = None
        self.envelope = None

    def finalize(self, elfie_id: str) -> None:
        del elfie_id
        self.events.append("workspace:finalize")


class Construction:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def restore(self, elfie_id: str, workspace: str) -> Elfie:
        self.events.append("restore")
        assert elfie_id and workspace
        return cast(Elfie, object())


class Residents:
    def __init__(self, events: list[str], *, fail_register: bool = False) -> None:
        self.events = events
        self.fail_register = fail_register
        self.registered: list[str] = []

    def register_elfie(self, elfie_id: str, elfie: Elfie) -> None:
        self.events.append("runtime")
        if self.fail_register:
            raise RuntimeError("register unavailable")
        del elfie
        self.registered.append(elfie_id)

    def remove_elfie(self, elfie_id: str) -> None:
        self.registered.remove(elfie_id)


class CountingCompiler:
    def __init__(self, compiler: GenesisCompiler) -> None:
        self.compiler = compiler
        self.calls = 0

    def compile(self, request):
        self.calls += 1
        return self.compiler.compile(request)

    def create_compile_envelope(self, request):
        return self.compiler.create_compile_envelope(request)

    def compile_envelope(self, envelope):
        self.calls += 1
        return self.compiler.compile_envelope(envelope)


def _compiler() -> GenesisCompiler:
    catalog = load_and_configure_species_catalog()
    return GenesisCompiler(load_genesis_source_package(), catalog=catalog)


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


def _service(
    events: list[str],
    store: AdmissionStore,
    workspace: Workspace,
    residents: Residents | None,
    compiler: GenesisCompiler | CountingCompiler | None = None,
) -> ResidentAdmissionService:
    adoption = AdoptionService(Policy(), AdoptionPersistence())
    return ResidentAdmissionService(
        adoption,
        workspace,
        Construction(events),
        residents,
        compiler or _compiler(),
        admission_store=store,
    )


def test_admission_commits_before_runtime_registration_and_retries_idempotently() -> (
    None
):
    events: list[str] = []
    store = AdmissionStore(events)
    workspace = Workspace(events)
    residents = Residents(events)
    adoption = AdoptionService(Policy(), AdoptionPersistence())
    principal = AccountPrincipal(7, "alice", "user", "chat")
    candidate_set_id, candidate_id = _accepted(adoption, principal)
    service = ResidentAdmissionService(
        adoption,
        workspace,
        Construction(events),
        residents,
        _compiler(),
        admission_store=store,
    )

    result = service.admit(
        principal,
        AdmitAcceptedAdoptionCommand(candidate_set_id, candidate_id, "星砂"),
    )

    assert result.persistence_status == "committed"
    assert result.runtime_status == "registered"
    assert residents.registered == [result.elfie_id]
    assert store.records[next(iter(store.records))].state == "committed"
    assert events.index("database:commit") < events.index("runtime")

    repeated = service.admit(
        principal,
        AdmitAcceptedAdoptionCommand(candidate_set_id, candidate_id, "另一个名字"),
    )
    assert repeated == result
    assert events.count("workspace:stage") == 1


def test_workspace_failure_aborts_the_durable_reservation() -> None:
    events: list[str] = []
    store = AdmissionStore(events)
    workspace = Workspace(events, fail_stage=True)
    adoption = AdoptionService(Policy(), AdoptionPersistence())
    principal = AccountPrincipal(7, "alice", "user", "chat")
    candidate_set_id, candidate_id = _accepted(adoption, principal)
    service = ResidentAdmissionService(
        adoption,
        workspace,
        Construction(events),
        None,
        _compiler(),
        admission_store=store,
    )

    with pytest.raises(ResidentAdmissionUnavailable):
        service.admit(
            principal,
            AdmitAcceptedAdoptionCommand(candidate_set_id, candidate_id, "星砂"),
        )

    record = next(iter(store.records.values()))
    assert record.state == "aborted"
    assert workspace.aborted


def test_runtime_registration_failure_keeps_committed_owners() -> None:
    events: list[str] = []
    store = AdmissionStore(events)
    workspace = Workspace(events)
    adoption = AdoptionService(Policy(), AdoptionPersistence())
    principal = AccountPrincipal(7, "alice", "user", "chat")
    candidate_set_id, candidate_id = _accepted(adoption, principal)
    service = ResidentAdmissionService(
        adoption,
        workspace,
        Construction(events),
        Residents(events, fail_register=True),
        _compiler(),
        admission_store=store,
    )

    result = service.admit(
        principal,
        AdmitAcceptedAdoptionCommand(candidate_set_id, candidate_id, "星砂"),
    )

    assert result.runtime_status == "offline"
    assert next(iter(store.records.values())).state == "committed"


def test_recovery_finishes_existing_output_without_recompiling() -> None:
    events: list[str] = []
    store = AdmissionStore(events)
    workspace = Workspace(events)
    adoption = AdoptionService(Policy(), AdoptionPersistence())
    principal = AccountPrincipal(7, "alice", "user", "chat")
    candidate_set_id, candidate_id = _accepted(adoption, principal)
    # Produce a real compilation once, then simulate a process stop after the
    # workspace stage and before the durable state advanced to ``staged``.
    accepted = adoption.prepare_accepted(
        principal,
        __import__(
            "app.features.adoption", fromlist=["AcceptAdoptionCommand"]
        ).AcceptAdoptionCommand(candidate_set_id, candidate_id, "星砂"),
    )
    reservation = AdmissionReservation(
        admission_id=accepted.reservation_id,
        idempotency_key_digest=idempotency_key_digest(accepted.idempotency_key),
        elfie_id=accepted.elfie_id,
        owner_user_id=principal.user_id,
        candidate_set_id=candidate_set_id,
        candidate_id=candidate_id,
        display_name=accepted.name,
        species_id=accepted.species_id,
        gender=accepted.gender,
        age_years=accepted.candidate.age_years,
        adoption_anchor_at=accepted.adoption_anchor_at,
    )
    record = store.reserve(reservation, 3)
    record = store.transition(record.admission_id, "reserved", "compiling")
    compilation = _compiler().compile(
        __import__(
            "elfie.genesis", fromlist=["GenesisCompileInput"]
        ).GenesisCompileInput(
            elfie_id=accepted.elfie_id,
            owner_reference=str(principal.user_id),
            display_name=accepted.name,
            species_id=accepted.species_id,
            gender=accepted.gender,
            life_stage=accepted.candidate.life_stage,
            age_years_at_adoption=accepted.candidate.age_years,
            appearance_seed=accepted.candidate.seed,
            height="standard",
            build="standard",
            face="any",
            signature="any",
            candidate=accepted.candidate,
            adoption_anchor_at=accepted.adoption_anchor_at,
            reservation_id=accepted.reservation_id,
            idempotency_key=accepted.idempotency_key,
        ),
    )
    workspace.stage(compilation)
    assert record.state == "compiling"

    counting = CountingCompiler(_compiler())
    service = ResidentAdmissionService(
        adoption,
        workspace,
        Construction(events),
        None,
        counting,  # type: ignore[arg-type]
        admission_store=store,
    )
    recovered = service.recover_pending()

    assert len(recovered) == 1
    assert counting.calls == 0
    assert next(iter(store.records.values())).state == "committed"


def test_recovery_recompiles_only_from_the_private_compile_envelope() -> None:
    events: list[str] = []
    store = AdmissionStore(events)
    workspace = Workspace(events)
    adoption = AdoptionService(Policy(), AdoptionPersistence())
    principal = AccountPrincipal(7, "alice", "user", "chat")
    candidate_set_id, candidate_id = _accepted(adoption, principal)
    accepted = adoption.prepare_accepted(
        principal,
        __import__(
            "app.features.adoption", fromlist=["AcceptAdoptionCommand"]
        ).AcceptAdoptionCommand(candidate_set_id, candidate_id, "星砂"),
    )
    reservation = AdmissionReservation(
        admission_id=accepted.reservation_id,
        idempotency_key_digest=idempotency_key_digest(accepted.idempotency_key),
        elfie_id=accepted.elfie_id,
        owner_user_id=principal.user_id,
        candidate_set_id=candidate_set_id,
        candidate_id=candidate_id,
        display_name=accepted.name,
        species_id=accepted.species_id,
        gender=accepted.gender,
        age_years=accepted.candidate.age_years,
        adoption_anchor_at=accepted.adoption_anchor_at,
    )
    record = store.reserve(reservation, 3)
    record = store.transition(record.admission_id, "reserved", "compiling")
    request = GenesisCompileInput(
        elfie_id=accepted.elfie_id,
        owner_reference=str(principal.user_id),
        display_name=accepted.name,
        species_id=accepted.species_id,
        gender=accepted.gender,
        life_stage=accepted.candidate.life_stage,
        age_years_at_adoption=accepted.candidate.age_years,
        appearance_seed=accepted.candidate.seed,
        height="standard",
        build="standard",
        face="any",
        signature="any",
        candidate=accepted.candidate,
        adoption_anchor_at=accepted.adoption_anchor_at,
        reservation_id=accepted.reservation_id,
        idempotency_key=accepted.idempotency_key,
    )
    workspace.stage_envelope(_compiler().create_compile_envelope(request))

    counting = CountingCompiler(_compiler())
    service = ResidentAdmissionService(
        adoption,
        workspace,
        Construction(events),
        None,
        counting,  # type: ignore[arg-type]
        admission_store=store,
    )

    recovered = service.recover_pending()

    assert len(recovered) == 1
    assert counting.calls == 1
    assert next(iter(store.records.values())).state == "committed"
    assert workspace.envelope is None
