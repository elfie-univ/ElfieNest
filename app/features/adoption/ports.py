"""Outbound Ports consumed by Adoption."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from elfie.public import GenesisCandidate

from .models import AdoptionSpeciesImage, AdoptionSpeciesImages, SpeciesImageKind
from .port_models import (
    AdoptionNestCapacityRecord,
    AdoptionPolicyRecord,
    AdoptionQuotaRecord,
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


class CandidatePortraitPort(Protocol):
    """Render two temporary candidate portraits from one Genesis appearance."""

    def render(self, candidate: GenesisCandidate) -> tuple[str, str]: ...


class SpeciesPresentationPort(Protocol):
    """Read presentation assets from the bundled species packages."""

    def urls(self, species_id: str) -> AdoptionSpeciesImages: ...

    def read(
        self, species_id: str, image_kind: SpeciesImageKind
    ) -> AdoptionSpeciesImage: ...


class SpeciesRuntimeReadinessPort(Protocol):
    """Expose only species packages proven usable by the active Godot runtime."""

    def available_species_ids(self) -> tuple[str, ...]: ...

    def is_available(self, species_id: str) -> bool: ...


@dataclass(frozen=True)
class StaticSpeciesRuntimeReadiness:
    """Small value adapter used by the composition root and focused tests."""

    species_ids: tuple[str, ...]

    def available_species_ids(self) -> tuple[str, ...]:
        return self.species_ids

    def is_available(self, species_id: str) -> bool:
        return species_id in self.species_ids


__all__ = (
    "AdoptionPersistencePort",
    "CandidatePortraitPort",
    "AdoptionPolicyPort",
    "AdoptionPortCapacityReached",
    "AdoptionPortNestCapacityReached",
    "AdoptionPortError",
    "AdoptionPortOwnerNotFound",
    "SpeciesPresentationPort",
    "SpeciesRuntimeReadinessPort",
    "StaticSpeciesRuntimeReadiness",
)
