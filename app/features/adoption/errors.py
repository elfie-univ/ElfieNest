"""Stable product errors raised by the Adoption facade."""


class AdoptionError(Exception):
    """Base class for Adoption use-case failures."""


class AdoptionCandidateSetExpired(AdoptionError):
    """The short-lived candidate set is absent, expired, or belongs to another user."""


class AdoptionSessionBusy(AdoptionError):
    """The short-lived adoption session is already processing another action."""


class AdoptionCandidateNotAccepted(AdoptionError):
    """The selected candidate has not accepted the invitation."""


class AdoptionCapacityReached(AdoptionError):
    """The current member has no remaining ownership quota."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        super().__init__(f"每用户最多领养 {limit} 只精灵")


class AdoptionNestCapacityReached(AdoptionError):
    """The Nest has no globally available bed."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        super().__init__(f"当前 Nest 最多容纳 {limit} 只精灵")


class AdoptionInvalid(AdoptionError):
    """The requested adoption value violates current product policy."""


class AdoptionOwnerNotFound(AdoptionError):
    """The authenticated account no longer exists in the ownership store."""


class AdoptionUnavailable(AdoptionError):
    """An authoritative Adoption dependency is unavailable."""


__all__ = (
    "AdoptionCandidateNotAccepted",
    "AdoptionCandidateSetExpired",
    "AdoptionSessionBusy",
    "AdoptionCapacityReached",
    "AdoptionError",
    "AdoptionInvalid",
    "AdoptionNestCapacityReached",
    "AdoptionOwnerNotFound",
    "AdoptionUnavailable",
)
