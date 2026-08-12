"""Public Resident Admission workflow boundary."""

from .errors import (
    ResidentAdmissionCompensationFailed,
    ResidentAdmissionError,
    ResidentAdmissionUnavailable,
)
from .models import AdmitAcceptedAdoptionCommand, ResidentAdmissionResult
from .ports import (
    ElfieConstructionPort,
    ResidentAdmissionPortError,
    ResidentSessionPort,
    ResidentWorkspacePort,
)
from .service import ResidentAdmissionService

__all__ = (
    "AdmitAcceptedAdoptionCommand",
    "ElfieConstructionPort",
    "ResidentAdmissionCompensationFailed",
    "ResidentAdmissionError",
    "ResidentAdmissionPortError",
    "ResidentAdmissionResult",
    "ResidentAdmissionService",
    "ResidentAdmissionUnavailable",
    "ResidentSessionPort",
    "ResidentWorkspacePort",
)
