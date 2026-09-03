"""Outbound Ports consumed by Resident Admission."""

from __future__ import annotations

from typing import Protocol

from elfie.public import (
    Elfie,
    ElfieProfile,
    GenesisCompilation,
    GenesisCompileEnvelope,
)

from .models import (
    AdmissionPublication,
    AdmissionRecord,
    AdmissionReservation,
    AdmissionState,
)


class ResidentAdmissionPortError(RuntimeError):
    """A technical admission boundary failed."""


class ResidentWorkspacePort(Protocol):
    def stage_envelope(self, envelope: GenesisCompileEnvelope) -> str: ...

    def stage(self, compilation: GenesisCompilation) -> str: ...

    def reopen(
        self,
        elfie_id: str,
        *,
        manifest_id: str | None = None,
        content_hash: str | None = None,
        output_ids_hash: str | None = None,
    ) -> str: ...

    def publication(self, elfie_id: str) -> AdmissionPublication: ...

    def publish(self, elfie_id: str) -> str: ...

    def final_workspace(self, elfie_id: str) -> str: ...

    def load_profile(self, elfie_id: str) -> ElfieProfile: ...

    def load_envelope(self, elfie_id: str) -> GenesisCompileEnvelope | None: ...

    def clear_envelope(self, elfie_id: str) -> None: ...

    def abort(self, elfie_id: str) -> None: ...

    def finalize(self, elfie_id: str) -> None: ...


class ResidentAdmissionStorePort(Protocol):
    """Durable Admission state and idempotency boundary."""

    def reserve(
        self,
        reservation: AdmissionReservation,
        default_limit: int,
    ) -> AdmissionRecord: ...

    def get(self, admission_id: str) -> AdmissionRecord | None: ...

    def list_incomplete(self) -> tuple[AdmissionRecord, ...]: ...

    def transition(
        self,
        admission_id: str,
        expected_state: AdmissionState,
        next_state: AdmissionState,
        *,
        manifest_id: str | None = None,
        content_hash: str | None = None,
        output_ids_hash: str | None = None,
        compiler_version: str | None = None,
        schema_version: int | None = None,
    ) -> AdmissionRecord: ...

    def commit(
        self,
        admission_id: str,
        publication: AdmissionPublication,
    ) -> AdmissionRecord: ...

    def abort(self, admission_id: str, *, error_code: str) -> AdmissionRecord: ...

    def mark_runtime_registered(self, admission_id: str) -> AdmissionRecord: ...


class ElfieConstructionPort(Protocol):
    def restore(self, elfie_id: str, workspace: str) -> Elfie: ...


class ResidentSessionPort(Protocol):
    def register_elfie(self, elfie_id: str, elfie: Elfie) -> None: ...

    def remove_elfie(self, elfie_id: str) -> None: ...


__all__ = (
    "ElfieConstructionPort",
    "ResidentAdmissionPortError",
    "ResidentAdmissionStorePort",
    "ResidentSessionPort",
    "ResidentWorkspacePort",
)
