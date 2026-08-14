"""Outbound Ports consumed by Adoption."""

from __future__ import annotations

from typing import Protocol

from elfie.genesis import CandidateReveal, GenesisCandidate

from .port_models import (
    AdoptionNestCapacityRecord,
    AdoptionPolicyRecord,
    AdoptionQuotaRecord,
    AdoptionReservationRecord,
)


class AdoptionPortError(RuntimeError):
    """An Adoption authority failed at a technical boundary."""


class AdoptionPortCapacityReached(AdoptionPortError):
    def __init__(self, limit: int) -> None:
        self.limit = limit
        super().__init__(f"adoption quota reached: {limit}")


class AdoptionPortNestCapacityReached(AdoptionPortError):
    def __init__(self, limit: int) -> None:
        self.limit = limit
        super().__init__(f"Nest adoption capacity reached: {limit}")


class AdoptionPortOwnerNotFound(AdoptionPortError):
    """The requested account row does not exist."""


class AdoptionPolicyPort(Protocol):
    def load_policy(self) -> AdoptionPolicyRecord: ...


class AdoptionPersistencePort(Protocol):
    def get_quota(
        self,
        owner_user_id: int,
        default_limit: int,
    ) -> AdoptionQuotaRecord | None: ...

    def get_nest_capacity(self) -> AdoptionNestCapacityRecord: ...

    def reserve(
        self,
        reservation: AdoptionReservationRecord,
        default_limit: int,
    ) -> None: ...

    def release(self, elfie_id: str) -> None: ...


class CandidatePortraitPort(Protocol):
    """Render two temporary candidate portraits from one Genesis appearance."""

    def render(self, candidate: GenesisCandidate) -> tuple[str, str]: ...


class AdoptionNarrativePort(Protocol):
    """Strong-model boundary for post-acceptance names and personal stories."""

    def is_ready(self) -> bool: ...

    def reveal(
        self,
        candidate: GenesisCandidate,
        invitation_message: str,
    ) -> CandidateReveal: ...


__all__ = (
    "AdoptionPersistencePort",
    "CandidatePortraitPort",
    "AdoptionNarrativePort",
    "AdoptionPolicyPort",
    "AdoptionPortCapacityReached",
    "AdoptionPortNestCapacityReached",
    "AdoptionPortError",
    "AdoptionPortOwnerNotFound",
)
