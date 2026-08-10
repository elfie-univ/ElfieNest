"""Setup Port Adapter delegating emergency Food planning to the current runtime."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from ai_runtime.food.evidence import record_model_evidence
from ai_runtime.food.planner import ModelEvidence
from ai_runtime.models.capabilities import canonical_display_name, known_capabilities
from app.features.configuration.food import FoodPortError
from app.orchestration.setup_installation import SetupInstallationPortError
from infrastructure.persistence.food import SQLiteFoodAdapter

from .food_technology import RuntimeFoodTechnologyAdapter


class SetupFoodAdapter:
    def __init__(
        self,
        *,
        catalog: SQLiteFoodAdapter,
        technology: RuntimeFoodTechnologyAdapter,
    ) -> None:
        self._catalog = catalog
        self._technology = technology

    def ensure_emergency_food(self, model_reference: str) -> None:
        try:
            evidence = ModelEvidence(
                model=model_reference,
                display_name=canonical_display_name(model_reference, model_reference),
                capabilities=frozenset({"text"})
                | known_capabilities(model_reference, model_reference),
                verified=True,
                cost_grade=0,
                local=True,
                observed_at=datetime.now(timezone.utc).isoformat(),
            )
            record_model_evidence(
                (evidence,),
                scope=f"setup:{model_reference}",
                trigger="setup",
            )
            defaults = self._technology.food_defaults()
            package = self._catalog.get_package(defaults.emergency_food_id)
            if package is None:
                raise SetupInstallationPortError(
                    "Setup emergency Food package is missing"
                )
            connection_id = model_reference.split("/", 1)[0]
            proposal = self._technology.propose_package(
                package,
                self._technology.list_model_evidence(),
                connection_ids=(connection_id,),
                local_first=True,
                allow_remote=False,
            )
            self._catalog.update_package(proposal.package)
        except SetupInstallationPortError:
            raise
        except (
            FoodPortError,
            OSError,
            RuntimeError,
            ValueError,
            sqlite3.Error,
        ) as error:
            raise SetupInstallationPortError(
                "unable to prepare emergency Food"
            ) from error


__all__ = ("SetupFoodAdapter",)
