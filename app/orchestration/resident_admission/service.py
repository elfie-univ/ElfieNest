"""The single, durable Resident Admission workflow."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Callable, Literal, Protocol, TypedDict, Union

from app.features.accounts import AccountPrincipal
from app.features.adoption import (
    AcceptAdoptionCommand,
    AdoptionCapacityReached,
    AdoptionError,
    AdoptionNestCapacityReached,
    AdoptionOwnerNotFound,
    AdoptionPortCapacityReached,
    AdoptionPortError,
    AdoptionPortNestCapacityReached,
    AdoptionPortOwnerNotFound,
    AdoptionService,
)
from elfie.public import (
    GenesisCompilation,
    GenesisCompileEnvelope,
    GenesisCompileInput,
)

from .errors import (
    ResidentAdmissionCompensationFailed,
    ResidentAdmissionUnavailable,
)
from .models import (
    AdmissionPublication,
    AdmissionRecord,
    AdmissionReservation,
    AdmitAcceptedAdoptionCommand,
    ResidentAdmissionResult,
    idempotency_key_digest,
)
from .ports import (
    ElfieConstructionPort,
    ResidentAdmissionPortError,
    ResidentAdmissionStorePort,
    ResidentSessionPort,
    ResidentWorkspacePort,
)


class _GenesisCompilerPort(Protocol):
    def create_compile_envelope(
        self, request: GenesisCompileInput
    ) -> GenesisCompileEnvelope: ...

    def compile(self, request: GenesisCompileInput) -> GenesisCompilation: ...

    def compile_envelope(
        self, envelope: GenesisCompileEnvelope
    ) -> GenesisCompilation: ...


class _PublicationFields(TypedDict):
    manifest_id: str
    content_hash: str
    output_ids_hash: str
    compiler_version: str
    schema_version: int


GenesisCompilerProvider = Union[
    _GenesisCompilerPort,
    Callable[[], _GenesisCompilerPort],
]


class ResidentAdmissionService:
    """Coordinate reservation, Genesis publication, recovery and registration.

    The service has one path for both a first request and a retry.  The
    persistent Admission row is the retry identity; the in-memory lock only
    prevents duplicate work inside this process and is never the source of
    truth.
    """

    def __init__(
        self,
        adoption: AdoptionService,
        workspace: ResidentWorkspacePort,
        elfies: ElfieConstructionPort,
        residents: ResidentSessionPort | None,
        compiler: GenesisCompilerProvider,
        *,
        admission_store: ResidentAdmissionStorePort,
    ) -> None:
        self._adoption = adoption
        self._workspace = workspace
        self._elfies = elfies
        self._residents = residents
        self._compiler = compiler
        self._admission_store = admission_store
        self._admission_lock = threading.RLock()

    def admit(
        self,
        principal: AccountPrincipal,
        command: AdmitAcceptedAdoptionCommand,
    ) -> ResidentAdmissionResult:
        """Accept one candidate and drive it to a durable committed state."""

        with self._admission_lock:
            accepted = self._adoption.prepare_accepted(
                principal,
                AcceptAdoptionCommand(
                    candidate_set_id=command.candidate_set_id,
                    candidate_id=command.candidate_id,
                    name=command.name,
                    full_body_image_url=command.full_body_image_url,
                    headshot_image_url=command.headshot_image_url,
                ),
            )
            reservation = AdmissionReservation(
                admission_id=accepted.reservation_id,
                idempotency_key_digest=idempotency_key_digest(accepted.idempotency_key),
                elfie_id=accepted.elfie_id,
                owner_user_id=accepted.owner_user_id,
                candidate_set_id=command.candidate_set_id,
                candidate_id=command.candidate_id,
                display_name=accepted.name,
                species_id=accepted.species_id,
                gender=accepted.gender,
                age_years=accepted.candidate.age_years,
                adoption_anchor_at=accepted.adoption_anchor_at,
            )
            record = self._reserve(reservation)
            if record.state == "committed":
                return self._finish_committed(record)
            if record.state == "aborted":
                raise ResidentAdmissionUnavailable("该领养决定已经终止，不能重复提交")
            return self._drive_new_admission(record, accepted)

    def recover_pending(self) -> tuple[ResidentAdmissionResult, ...]:
        """Finish or terminate durable pre-commit records after a restart.

        Recovery first reuses a valid staged output.  If the process stopped
        during compilation, it reuses the same private envelope and compiler
        binding; it never reconstructs a new request from current UI input.
        A reservation with neither output nor envelope is safely terminated.
        """

        recovered: list[ResidentAdmissionResult] = []
        with self._admission_lock:
            pending = self._admission_store.list_incomplete()
            for record in pending:
                try:
                    result = self._recover_record(record)
                except (
                    AdoptionError,
                    ResidentAdmissionPortError,
                    OSError,
                    RuntimeError,
                    TypeError,
                    ValueError,
                ):
                    # A malformed or externally interrupted record remains in
                    # its durable state for the next bounded recovery attempt.
                    # We do not invent a replacement life or delete a final
                    # workspace while the publication outcome is uncertain.
                    continue
                if result is not None:
                    recovered.append(result)
        return tuple(recovered)

    def _reserve(self, reservation: AdmissionReservation) -> AdmissionRecord:
        try:
            return self._admission_store.reserve(
                reservation,
                self._adoption.get_default_elfie_limit(),
            )
        except AdoptionPortCapacityReached as error:
            raise AdoptionCapacityReached(error.limit) from error
        except AdoptionPortNestCapacityReached as error:
            raise AdoptionNestCapacityReached(error.limit) from error
        except AdoptionPortOwnerNotFound as error:
            raise AdoptionOwnerNotFound("用户不存在") from error
        except AdoptionPortError as error:
            raise ResidentAdmissionUnavailable("领养预约暂不可用") from error

    def _drive_new_admission(
        self, record: AdmissionRecord, accepted
    ) -> ResidentAdmissionResult:
        current = record
        try:
            if current.state == "reserved":
                current = self._admission_store.transition(
                    current.admission_id,
                    "reserved",
                    "compiling",
                )

            if current.state == "compiling":
                compile_input = self._compile_input(accepted, current)
                envelope = self._create_compile_envelope(compile_input)
                self._workspace.stage_envelope(envelope)
                compilation = self._compile_envelope(envelope)
                self._workspace.stage(compilation)
                current = self._admission_store.transition(
                    current.admission_id,
                    "compiling",
                    "staged",
                    **_publication_fields(compilation),
                )

            if current.state == "staged":
                self._workspace.reopen(
                    current.elfie_id,
                    manifest_id=current.manifest_id,
                    content_hash=current.content_hash,
                    output_ids_hash=current.output_ids_hash,
                )
                current = self._admission_store.transition(
                    current.admission_id,
                    "staged",
                    "publishing",
                )

            if current.state != "publishing":
                raise ResidentAdmissionPortError(
                    f"unexpected Admission state: {current.state}"
                )
            self._workspace.reopen(
                current.elfie_id,
                manifest_id=current.manifest_id,
                content_hash=current.content_hash,
                output_ids_hash=current.output_ids_hash,
            )
            self._workspace.publish(current.elfie_id)
            current = self._admission_store.commit(
                current.admission_id,
                _publication_from_record(current),
            )
        except AdoptionError:
            self._terminate_precommit(current, error_code="adoption_failure")
            raise
        except (
            ResidentAdmissionPortError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as error:
            latest = self._latest(current)
            if latest.state in {"reserved", "compiling", "staged"}:
                self._terminate_precommit(latest, error_code="genesis_failure")
                raise ResidentAdmissionUnavailable("精灵 Genesis 未能提交") from error
            # A publishing record is deliberately retained.  The rename or
            # SQLite commit may have completed just before the exception, so a
            # destructive compensation would risk deleting a valid resident.
            raise ResidentAdmissionUnavailable(
                "精灵正在完成持久化；下次启动将继续同一预约"
            ) from error

        # The final owners are durable before this point.  Marker cleanup is a
        # best-effort post-commit detail and can never roll the resident back.
        try:
            self._workspace.clear_envelope(current.elfie_id)
        except (ResidentAdmissionPortError, OSError, RuntimeError):
            pass
        try:
            self._workspace.finalize(current.elfie_id)
        except (ResidentAdmissionPortError, OSError, RuntimeError):
            pass
        return self._finish_committed(current)

    def _recover_record(
        self, record: AdmissionRecord
    ) -> ResidentAdmissionResult | None:
        current = record
        if current.state in {"reserved", "compiling"}:
            try:
                self._workspace.reopen(current.elfie_id)
                publication = self._workspace.publication(current.elfie_id)
            except (
                ResidentAdmissionPortError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ):
                envelope = self._workspace.load_envelope(current.elfie_id)
                if envelope is None:
                    self._terminate_precommit(current, error_code="recovery_no_output")
                    return None
                if current.state == "reserved":
                    current = self._admission_store.transition(
                        current.admission_id,
                        "reserved",
                        "compiling",
                    )
                compilation = self._compile_envelope(envelope)
                self._workspace.stage(compilation)
                publication = self._workspace.publication(current.elfie_id)
            if current.state == "reserved":
                current = self._admission_store.transition(
                    current.admission_id,
                    "reserved",
                    "compiling",
                )
            current = self._admission_store.transition(
                current.admission_id,
                "compiling",
                "staged",
                manifest_id=publication.manifest_id,
                content_hash=publication.content_hash,
                output_ids_hash=publication.output_ids_hash,
                compiler_version=publication.compiler_version,
                schema_version=publication.schema_version,
            )

        if current.state == "staged":
            self._workspace.reopen(
                current.elfie_id,
                manifest_id=current.manifest_id,
                content_hash=current.content_hash,
                output_ids_hash=current.output_ids_hash,
            )
            current = self._admission_store.transition(
                current.admission_id,
                "staged",
                "publishing",
            )

        if current.state == "publishing":
            self._workspace.reopen(
                current.elfie_id,
                manifest_id=current.manifest_id,
                content_hash=current.content_hash,
                output_ids_hash=current.output_ids_hash,
            )
            self._workspace.publish(current.elfie_id)
            current = self._admission_store.commit(
                current.admission_id,
                _publication_from_record(current),
            )

        if current.state != "committed":
            return None
        try:
            self._workspace.clear_envelope(current.elfie_id)
        except (ResidentAdmissionPortError, OSError, RuntimeError):
            pass
        try:
            self._workspace.finalize(current.elfie_id)
        except (ResidentAdmissionPortError, OSError, RuntimeError):
            pass
        return self._finish_committed(current)

    def _compile(self, accepted, record: AdmissionRecord) -> GenesisCompilation:
        return self._compiler_instance().compile(self._compile_input(accepted, record))

    def _compile_input(self, accepted, record: AdmissionRecord) -> GenesisCompileInput:
        anchor = record.adoption_anchor_at or accepted.adoption_anchor_at
        return GenesisCompileInput(
            elfie_id=record.elfie_id,
            owner_reference=str(record.owner_user_id),
            display_name=record.display_name or accepted.name,
            species_id=record.species_id or accepted.species_id,
            gender=record.gender or accepted.gender,
            life_stage=accepted.candidate.life_stage,
            age_years_at_adoption=record.age_years or accepted.candidate.age_years,
            appearance_seed=accepted.candidate.seed,
            height=_height_direction(accepted.candidate),
            build=_build_direction(accepted.candidate),
            face="any",
            signature="any",
            candidate=accepted.candidate,
            original_name="",
            adoption_anchor_at=anchor,
            reservation_id=record.admission_id,
            idempotency_key=accepted.idempotency_key,
            full_body_image_url=accepted.full_body_image_url,
            headshot_image_url=accepted.headshot_image_url,
        )

    def _compiler_instance(self):
        compiler = self._compiler
        if callable(compiler) and not hasattr(compiler, "compile"):
            compiler = compiler()
        return compiler

    def _create_compile_envelope(
        self, request: GenesisCompileInput
    ) -> GenesisCompileEnvelope:
        compiler = self._compiler_instance()
        method = getattr(compiler, "create_compile_envelope", None)
        if not callable(method):
            raise ResidentAdmissionPortError(
                "Genesis compiler does not provide a recovery envelope"
            )
        return method(request)

    def _compile_envelope(self, envelope: GenesisCompileEnvelope) -> GenesisCompilation:
        compiler = self._compiler_instance()
        method = getattr(compiler, "compile_envelope", None)
        if not callable(method):
            raise ResidentAdmissionPortError(
                "Genesis compiler does not provide envelope compilation"
            )
        return method(envelope)

    def _finish_committed(self, record: AdmissionRecord) -> ResidentAdmissionResult:
        profile = self._workspace.load_profile(record.elfie_id)
        runtime_status: Literal["registered", "offline"] = "offline"
        if self._residents is not None:
            try:
                workspace = self._workspace.final_workspace(record.elfie_id)
                elfie = self._elfies.restore(record.elfie_id, workspace)
                self._residents.register_elfie(record.elfie_id, elfie)
                self._admission_store.mark_runtime_registered(record.admission_id)
                runtime_status = "registered"
            except (
                ResidentAdmissionPortError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ):
                # The durable owner remains committed and is retried by the
                # normal startup/runtime recovery path.
                runtime_status = "offline"
        return ResidentAdmissionResult(
            elfie_id=profile.identity.elfie_id,
            name=profile.identity.display_name,
            species_id=profile.identity.species_id,
            persistence_status="committed",
            runtime_status=runtime_status,
        )

    def _latest(self, record: AdmissionRecord) -> AdmissionRecord:
        try:
            return self._admission_store.get(record.admission_id) or record
        except (AdoptionError, AdoptionPortError, OSError, RuntimeError):
            return record

    def _terminate_precommit(self, record: AdmissionRecord, *, error_code: str) -> None:
        if record.state in {"committed", "aborted", "publishing"}:
            return
        failures: list[Exception] = []
        try:
            self._workspace.abort(record.elfie_id)
        except (ResidentAdmissionPortError, OSError, RuntimeError, ValueError) as error:
            failures.append(error)
        if not failures:
            try:
                self._admission_store.abort(record.admission_id, error_code=error_code)
            except (AdoptionPortError, OSError, RuntimeError, ValueError) as error:
                failures.append(error)
        if failures:
            raise ResidentAdmissionCompensationFailed(
                "领养失败，且未能完整清理预约输出"
            ) from failures[0]


def _publication_fields(compilation: GenesisCompilation) -> _PublicationFields:
    manifest = compilation.bundle.manifest
    return {
        "manifest_id": manifest.manifest_id,
        "content_hash": manifest.content_hash,
        "output_ids_hash": compilation.output_ids_hash,
        "compiler_version": manifest.compiler_version,
        "schema_version": manifest.schema_version,
    }


def _publication_from_record(record: AdmissionRecord) -> AdmissionPublication:
    if (
        record.manifest_id is None
        or record.content_hash is None
        or record.output_ids_hash is None
        or record.compiler_version is None
        or record.schema_version is None
    ):
        raise ResidentAdmissionPortError("Admission publication metadata is incomplete")
    return AdmissionPublication(
        manifest_id=str(record.manifest_id),
        content_hash=str(record.content_hash),
        output_ids_hash=str(record.output_ids_hash),
        compiler_version=str(record.compiler_version),
        schema_version=record.schema_version,
        adopted_at=record.created_at or datetime.now(timezone.utc).isoformat(),
    )


def _height_direction(candidate) -> str:
    value = candidate.appearance.macro.stature_z
    return "short" if value <= -0.35 else "tall" if value >= 0.35 else "standard"


def _build_direction(candidate) -> str:
    value = candidate.appearance.macro.body_fat_z
    return "slim" if value <= -0.35 else "plump" if value >= 0.35 else "standard"


__all__ = ("ResidentAdmissionService",)
