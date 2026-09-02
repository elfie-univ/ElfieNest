"""Public Resident Admission workflow boundary."""

from .errors import (
    ResidentAdmissionCompensationFailed,
    ResidentAdmissionError,
    ResidentAdmissionUnavailable,
)
from .models import (
    ACTIVE_ADMISSION_STATES,
    ADMISSION_TRANSITIONS,
    AdmissionPublication,
    AdmissionRecord,
    AdmissionReservation,
    AdmissionRuntimeStatus,
    AdmissionState,
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
from .service import ResidentAdmissionService

__all__ = (
    "AdmitAcceptedAdoptionCommand",
    "ACTIVE_ADMISSION_STATES",
    "ADMISSION_TRANSITIONS",
    "AdmissionPublication",
    "AdmissionRecord",
    "AdmissionReservation",
    "AdmissionRuntimeStatus",
    "AdmissionState",
    "ElfieConstructionPort",
    "ResidentAdmissionCompensationFailed",
    "ResidentAdmissionError",
    "ResidentAdmissionPortError",
    "ResidentAdmissionStorePort",
    "ResidentAdmissionResult",
    "ResidentAdmissionService",
    "ResidentAdmissionUnavailable",
    "ResidentSessionPort",
    "ResidentWorkspacePort",
    "idempotency_key_digest",
)
