"""Stable Providers use-case errors."""


class ProvidersError(RuntimeError):
    """Base class for Provider administration failures."""


class ProvidersForbidden(ProvidersError):
    """The principal cannot administer Provider resources."""


class ProviderProductNotFound(ProvidersError):
    """The requested Provider product is not in the authoritative catalog."""


class ProviderConnectionNotFound(ProvidersError):
    """The requested Provider connection does not exist."""


class ProviderModelNotFound(ProvidersError):
    """The requested endpoint model does not exist."""


class ProvidersValidationError(ProvidersError):
    """The requested Provider mutation is invalid."""


class ProvidersConflict(ProvidersError):
    """The requested mutation conflicts with current product facts."""


class ProvidersUnavailable(ProvidersError):
    """A Provider technology boundary is unavailable."""


__all__ = (
    "ProviderConnectionNotFound",
    "ProviderModelNotFound",
    "ProviderProductNotFound",
    "ProvidersConflict",
    "ProvidersError",
    "ProvidersForbidden",
    "ProvidersUnavailable",
    "ProvidersValidationError",
)
