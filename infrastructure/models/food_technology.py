"""Strict Food Port Adapter over the existing AI Runtime implementation."""

from __future__ import annotations

import sqlite3
from typing import Optional, cast

from ai_runtime.food.evidence import query_model_evidence
from ai_runtime.food.health import project_food_health
from ai_runtime.food.models import (
    FOOD_COMMON_ID,
    FOOD_EMERGENCY_ID,
    SYSTEM_FOOD_IDS,
    FoodPackage,
    ModelAssignment,
)
from ai_runtime.food.planner import FoodPlanner, ModelEvidence
from ai_runtime.food.store import (
    FOOD_CATALOG_VERSION,
    FoodCatalog,
    validate_food_catalog_model_references,
)
from ai_runtime.models.model_reference import ModelReferenceError
from ai_runtime.storage.provider_connections import ProviderConnectionStoreError
from app.features.configuration.food import (
    FoodPortError,
    FoodPortInvalid,
    FoodSystemRole,
    FoodVisibilityMode,
    StoredFoodChange,
    StoredFoodDefaults,
    StoredFoodHealth,
    StoredFoodPackage,
    StoredFoodProposal,
    StoredModelEvidence,
)


class RuntimeFoodTechnologyAdapter:
    """Delegate algorithms to their one current implementation during migration."""

    def food_defaults(self) -> StoredFoodDefaults:
        return StoredFoodDefaults(
            catalog_version=FOOD_CATALOG_VERSION,
            default_food_id=FOOD_COMMON_ID,
            emergency_food_id=FOOD_EMERGENCY_ID,
            system_food_ids=SYSTEM_FOOD_IDS,
        )

    def list_model_evidence(self) -> tuple[StoredModelEvidence, ...]:
        try:
            evidence = query_model_evidence()
        except (
            OSError,
            ValueError,
            sqlite3.Error,
            ProviderConnectionStoreError,
        ) as error:
            raise FoodPortError("Unable to read model evidence") from error
        return tuple(self._stored_evidence(item) for item in evidence.values())

    def validate_package(self, package: StoredFoodPackage) -> None:
        try:
            runtime = self._runtime_package(package)
            validate_food_catalog_model_references(
                FoodCatalog(packages={runtime.key: runtime})
            )
        except (
            ModelReferenceError,
            OSError,
            ValueError,
            ProviderConnectionStoreError,
        ) as error:
            raise FoodPortInvalid(str(error)) from error

    def project_health(
        self,
        package: StoredFoodPackage,
        evidence: tuple[StoredModelEvidence, ...],
    ) -> StoredFoodHealth:
        try:
            result = project_food_health(
                self._runtime_package(package),
                {item.reference: self._runtime_evidence(item) for item in evidence},
            )
        except (TypeError, ValueError) as error:
            raise FoodPortError("Unable to project Food health") from error
        return StoredFoodHealth(
            status=result.status,
            locality=result.locality,
            latest_evidence_at=result.latest_evidence_at,
        )

    def propose_package(
        self,
        package: StoredFoodPackage,
        evidence: tuple[StoredModelEvidence, ...],
        *,
        connection_ids: tuple[str, ...],
        local_first: bool,
        allow_remote: bool,
    ) -> StoredFoodProposal:
        try:
            proposal = FoodPlanner().propose_package(
                self._runtime_package(package),
                tuple(self._runtime_evidence(item) for item in evidence),
                connection_ids=connection_ids,
                local_first=local_first,
                allow_remote=allow_remote,
            )
        except (TypeError, ValueError) as error:
            raise FoodPortError("Unable to generate Food preview") from error
        return StoredFoodProposal(
            package=self._stored_package(proposal.package),
            changes=tuple(
                StoredFoodChange(item.role, item.old_model, item.new_model)
                for item in proposal.changes
            ),
            warnings=proposal.warnings,
        )

    @staticmethod
    def _runtime_package(package: StoredFoodPackage) -> FoodPackage:
        return FoodPackage(
            key=package.food_id,
            display_name=package.display_name,
            system_role=package.system_role,
            enabled=package.enabled,
            archived=package.archived,
            primary=_assignment(package.primary_model),
            reasoning=_assignment(package.reasoning_model),
            vision=_assignment(package.vision_model),
            tool=_assignment(package.tool_model),
            fallback=_assignment(package.fallback_model),
            visibility_mode=package.visibility_mode,
            visible_user_ids=package.visible_user_ids,
        )

    @staticmethod
    def _stored_package(package: FoodPackage) -> StoredFoodPackage:
        return StoredFoodPackage(
            food_id=package.key,
            display_name=package.display_name,
            system_role=cast(Optional[FoodSystemRole], package.system_role),
            enabled=package.enabled,
            archived=package.archived,
            primary_model=_reference(package.primary),
            reasoning_model=_reference(package.reasoning),
            vision_model=_reference(package.vision),
            tool_model=_reference(package.tool),
            fallback_model=_reference(package.fallback),
            visibility_mode=cast(FoodVisibilityMode, package.visibility_mode),
            visible_user_ids=package.visible_user_ids,
        )

    @staticmethod
    def _stored_evidence(evidence: ModelEvidence) -> StoredModelEvidence:
        return StoredModelEvidence(
            reference=evidence.model,
            display_name=evidence.display_name or evidence.model,
            capabilities=evidence.capabilities,
            verified=evidence.verified,
            cost_grade=evidence.cost_grade,
            latency_ms=evidence.latency_ms,
            tool_test_passed=evidence.tool_test_passed,
            local=evidence.local,
            observed_at=evidence.observed_at,
            status=evidence.status,
            fresh=evidence.is_fresh(),
        )

    @staticmethod
    def _runtime_evidence(evidence: StoredModelEvidence) -> ModelEvidence:
        return ModelEvidence(
            model=evidence.reference,
            display_name=evidence.display_name,
            capabilities=evidence.capabilities,
            verified=evidence.verified,
            cost_grade=evidence.cost_grade,
            latency_ms=evidence.latency_ms,
            tool_test_passed=evidence.tool_test_passed,
            local=evidence.local,
            observed_at=evidence.observed_at,
            status=evidence.status,
        )


def _assignment(reference: str | None) -> ModelAssignment | None:
    return None if reference is None else ModelAssignment(reference)


def _reference(assignment: ModelAssignment | None) -> str | None:
    return None if assignment is None else assignment.model


__all__ = ("RuntimeFoodTechnologyAdapter",)
