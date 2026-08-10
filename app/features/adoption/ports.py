"""Outbound Ports consumed by Adoption."""

from __future__ import annotations

from typing import Protocol

from .port_models import (
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

    def reserve(
        self,
        reservation: AdoptionReservationRecord,
        default_limit: int,
    ) -> None: ...

    def release(self, elfie_id: str) -> None: ...


__all__ = (
    "AdoptionPersistencePort",
    "AdoptionPolicyPort",
    "AdoptionPortCapacityReached",
    "AdoptionPortError",
    "AdoptionPortOwnerNotFound",
)
