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
    AssignNestBedCommand,
    NestBed,
    NestBedAssignment,
    NestConfiguration,
    NestRoom,
    UpdateNestBedCountCommand,
)
from .ports import (
    NestBedRecord,
    NestManagementPort,
    NestPortBedNotFound,
    NestPortConflict,
    NestPortError,
    NestPortResidentNotFound,
    NestSnapshotRecord,
)
from .service import NestManagementService

__all__ = (
    "AssignNestBedCommand",
    "NestBed",
    "NestBedAssignment",
    "NestBedConflict",
    "NestBedNotFound",
    "NestBedRecord",
    "NestConfiguration",
    "NestConfigurationConflict",
    "NestConfigurationInvalid",
    "NestManagementForbidden",
    "NestManagementPort",
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
