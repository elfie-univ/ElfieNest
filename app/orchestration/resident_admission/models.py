"""Typed records owned by the one-time Resident Admission workflow."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

from app.features.adoption import SpeciesId

AdmissionState = Literal[
    "reserved",
    "compiling",
    "staged",
    "publishing",
    "committed",
    "aborted",
]
AdmissionRuntimeStatus = Literal["pending", "registered", "offline"]

ACTIVE_ADMISSION_STATES: frozenset[AdmissionState] = frozenset(
    {"reserved", "compiling", "staged", "publishing", "committed"}
)

ADMISSION_TRANSITIONS: dict[AdmissionState, frozenset[AdmissionState]] = {
    "reserved": frozenset({"compiling", "aborted"}),
    "compiling": frozenset({"staged", "aborted"}),
    "staged": frozenset({"publishing", "aborted"}),
    "publishing": frozenset({"committed"}),
    "committed": frozenset(),
    "aborted": frozenset(),
}


def idempotency_key_digest(value: str) -> str:
    """Return the only form of an Admission idempotency key allowed to persist."""

    normalized = value.strip()
    if not normalized:
        raise ValueError("idempotency key must not be blank")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AdmitAcceptedAdoptionCommand:
    candidate_set_id: str
    candidate_id: str
    name: str
    full_body_image_url: str = ""
    headshot_image_url: str = ""


@dataclass(frozen=True)
class AdmissionReservation:
    """Bounded transaction input retained only until Genesis is committed."""

    admission_id: str
    idempotency_key_digest: str
    elfie_id: str
    owner_user_id: int
    candidate_set_id: str
    candidate_id: str
    display_name: str
    species_id: str
    gender: str
    age_years: int
    adoption_anchor_at: str


@dataclass(frozen=True)
class AdmissionRecord:
    """Durable state-machine record; transient identity fields are nullable."""

    admission_id: str
    idempotency_key_digest: str
    elfie_id: str
    owner_user_id: int
    state: AdmissionState
    display_name: str | None = None
    species_id: str | None = None
    gender: str | None = None
    age_years: int | None = None
    candidate_set_id: str | None = None
    candidate_id: str | None = None
    adoption_anchor_at: str | None = None
    manifest_id: str | None = None
    content_hash: str | None = None
    output_ids_hash: str | None = None
    compiler_version: str | None = None
    schema_version: int | None = None
    runtime_status: AdmissionRuntimeStatus = "pending"
    error_code: str | None = None
    created_at: str = ""
    updated_at: str = ""
    committed_at: str | None = None


@dataclass(frozen=True)
class AdmissionPublication:
    """Commit metadata produced after a staged workspace is verified."""

    manifest_id: str
    content_hash: str
    output_ids_hash: str
    compiler_version: str
    schema_version: int
    adopted_at: str = ""


@dataclass(frozen=True)
class ResidentAdmissionResult:
    elfie_id: str
    name: str
    species_id: SpeciesId
    persistence_status: Literal["committed"] = "committed"
    runtime_status: Literal["registered", "offline"] = "registered"


__all__ = (
    "ACTIVE_ADMISSION_STATES",
    "ADMISSION_TRANSITIONS",
    "AdmissionPublication",
    "AdmissionRecord",
    "AdmissionReservation",
    "AdmissionRuntimeStatus",
    "AdmissionState",
    "AdmitAcceptedAdoptionCommand",
    "idempotency_key_digest",
    "ResidentAdmissionResult",
)
