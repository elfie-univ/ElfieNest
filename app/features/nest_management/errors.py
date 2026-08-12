"""Stable business errors for Nest Management."""


class NestManagementError(RuntimeError):
    """Base class for Nest Management use-case failures."""


class NestManagementForbidden(NestManagementError):
    """The authenticated principal cannot administer the Nest."""


class NestConfigurationInvalid(NestManagementError):
    """The requested Nest configuration violates the public Nest contract."""


class NestConfigurationConflict(NestManagementError):
    """The requested capacity conflicts with current assignments."""


class NestResidentNotFound(NestManagementError):
    """The requested Elfie is not a persisted Nest resident."""


class NestBedNotFound(NestManagementError):
    """The requested semantic bed is outside the configured Nest."""


class NestBedConflict(NestManagementError):
    """The requested semantic bed is already occupied."""


class NestManagementUnavailable(NestManagementError):
    """The persisted Nest projection is temporarily unavailable."""


__all__ = (
    "NestBedConflict",
    "NestBedNotFound",
    "NestConfigurationConflict",
    "NestConfigurationInvalid",
    "NestManagementError",
    "NestManagementForbidden",
    "NestManagementUnavailable",
    "NestResidentNotFound",
)
