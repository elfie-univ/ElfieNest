"""Technical Ports consumed by Food configuration."""

from __future__ import annotations

from typing import Protocol

from .port_models import (
    StoredElfieFoodAssignment,
    StoredFoodDefaults,
    StoredFoodHealth,
    StoredFoodPackage,
    StoredFoodProposal,
    StoredModelEvidence,
)


class FoodPortError(RuntimeError):
    """A Food technical boundary could not complete an operation."""


class FoodPortNotFound(FoodPortError):
    """A requested persisted Food fact is absent."""


class FoodPortConflict(FoodPortError):
    """A Food write conflicts with persisted references or lifecycle state."""


class FoodPortInvalid(FoodPortError):
    """A Food record is invalid for the current persistent facts."""


class FoodCatalogPort(Protocol):
    def list_packages(self) -> tuple[StoredFoodPackage, ...]: ...

    def get_package(self, food_id: str) -> StoredFoodPackage | None: ...

    def create_package(self, package: StoredFoodPackage) -> StoredFoodPackage: ...

    def update_package(self, package: StoredFoodPackage) -> StoredFoodPackage: ...

    def delete_package(self, food_id: str) -> None: ...


class FoodTechnologyPort(Protocol):
    def food_defaults(self) -> StoredFoodDefaults: ...

    def list_model_evidence(self) -> tuple[StoredModelEvidence, ...]: ...

    def validate_package(self, package: StoredFoodPackage) -> None: ...

    def project_health(
        self,
        package: StoredFoodPackage,
        evidence: tuple[StoredModelEvidence, ...],
    ) -> StoredFoodHealth: ...

    def propose_package(
        self,
        package: StoredFoodPackage,
        evidence: tuple[StoredModelEvidence, ...],
        *,
        connection_ids: tuple[str, ...],
        local_first: bool,
        allow_remote: bool,
    ) -> StoredFoodProposal: ...


class ElfieFoodAssignmentPort(Protocol):
    def list_assignments(self) -> tuple[StoredElfieFoodAssignment, ...]: ...

    def get_assignment(self, elfie_id: str) -> StoredElfieFoodAssignment | None: ...

    def list_assignments(self) -> tuple[StoredElfieFoodAssignment, ...]: ...

    def set_main_food(self, elfie_id: str, food_id: str) -> None: ...


__all__ = (
    "ElfieFoodAssignmentPort",
    "FoodCatalogPort",
    "FoodTechnologyPort",
    "FoodPortConflict",
    "FoodPortError",
    "FoodPortInvalid",
    "FoodPortNotFound",
)
