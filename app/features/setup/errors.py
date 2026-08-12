"""Business errors raised by Setup."""


class SetupError(RuntimeError):
    pass


class SetupForbidden(SetupError):
    pass


class SetupConflict(SetupError):
    pass


class SetupValidationError(SetupError):
    pass


class SetupUnavailable(SetupError):
    pass


__all__ = (
    "SetupConflict",
    "SetupError",
    "SetupForbidden",
    "SetupUnavailable",
    "SetupValidationError",
)
