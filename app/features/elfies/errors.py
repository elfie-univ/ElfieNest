"""Stable business errors for authorized Elfie projections."""


class ElfiesError(RuntimeError):
    """Base class for Elfies query failures."""


class ElfiesForbidden(ElfiesError):
    """The principal cannot access the requested projection."""


class ElfieNotFound(ElfiesError):
    """The requested Elfie is not visible to the principal."""


class ElfiesUnavailable(ElfiesError):
    """An authoritative read source could not be queried safely."""


__all__ = (
    "ElfieNotFound",
    "ElfiesError",
    "ElfiesForbidden",
    "ElfiesUnavailable",
)
