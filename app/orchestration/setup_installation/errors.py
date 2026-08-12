"""Workflow errors for Setup installation."""


class SetupInstallationError(RuntimeError):
    pass


class SetupInstallationForbidden(SetupInstallationError):
    pass


class SetupInstallationConflict(SetupInstallationError):
    pass


class SetupInstallationInvalid(SetupInstallationError):
    pass


class SetupInstallationUnavailable(SetupInstallationError):
    pass


__all__ = tuple(name for name in globals() if name.startswith("SetupInstallation"))
