"""Stable public facade for Nest Management."""

from .errors import (
    NestBedConflict,
    NestBedNotFound,
    NestConfigurationConflict,
    NestConfigurationInvalid,
    NestManagementForbidden,
    NestManagementUnavailable,
    NestResidentNotFound,
)
from .models import (
    AssignNestHomeCommand,
    NestBed,
    NestBedAssignment,
    NestConfiguration,
    NestRoom,
    UpdateNestBedCountCommand,
)
from .ports import (
    NestBedRecord,
    NestManagementCommandPort,
    NestManagementQueryPort,
    NestPortBedNotFound,
    NestPortConflict,
    NestPortError,
    NestPortResidentNotFound,
    NestSnapshotRecord,
)
from .service import NestManagementService

__all__ = (
    "AssignNestHomeCommand",
    "NestBed",
    "NestBedAssignment",
    "NestBedConflict",
    "NestBedNotFound",
    "NestBedRecord",
    "NestConfiguration",
    "NestConfigurationConflict",
    "NestConfigurationInvalid",
    "NestManagementForbidden",
    "NestManagementCommandPort",
    "NestManagementQueryPort",
    "NestManagementService",
    "NestManagementUnavailable",
    "NestPortBedNotFound",
    "NestPortConflict",
    "NestPortError",
    "NestPortResidentNotFound",
    "NestResidentNotFound",
    "NestRoom",
    "NestSnapshotRecord",
    "UpdateNestBedCountCommand",
)
