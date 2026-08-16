"""Production composition for first-run Setup and its installation workflow."""

from __future__ import annotations

from dataclasses import dataclass

from app.features.accounts import AccountsService
from app.features.configuration import ProviderLocalStatePort
from app.features.setup import SetupService
from app.orchestration.setup_installation import SetupInstallationService
from infrastructure.models.food_technology import (
    FoodEvidencePort,
    ModelFoodTechnologyAdapter,
)
from infrastructure.models.providers.catalog import ProviderCatalog
from infrastructure.models.setup_catalog import ProviderSetupCatalogAdapter
from infrastructure.models.setup_food import SetupFoodAdapter
from infrastructure.models.setup_ollama import SetupOllamaAdapter
from infrastructure.models.setup_ollama_technology import (
    PublicOllamaSetupTechnologyAdapter,
)
from infrastructure.models.setup_provider import SetupProviderAdapter
from infrastructure.persistence.food import SQLiteFoodAdapter
from infrastructure.persistence.nest_db.nest_management import (
    SQLiteNestManagementAdapter,
)
from infrastructure.persistence.setup import SQLiteSetupAdapter
from infrastructure.persistence.setup_accounts import SetupAccountsAdapter
from infrastructure.persistence.setup_nest import SetupNestAdapter
from infrastructure.persistence.setup_nest_choices import NestConfigSetupChoiceAdapter
from infrastructure.platform.setup_runner import ThreadSetupInstallationRunner


@dataclass(frozen=True)
class SetupServices:
    setup: SetupService
    installation: SetupInstallationService


def build_setup_services(
    db_path: str,
    *,
    accounts: AccountsService,
    nest: SQLiteNestManagementAdapter,
    provider_state: ProviderLocalStatePort,
    food_evidence: FoodEvidencePort | None = None,
    catalog: ProviderCatalog | None = None,
) -> SetupServices:
    state = SQLiteSetupAdapter(db_path)
    setup_accounts = SetupAccountsAdapter(accounts)
    providers = SetupProviderAdapter(provider_state)
    ollama = SetupOllamaAdapter(
        technology=PublicOllamaSetupTechnologyAdapter(),
        load_binding=providers.load_ollama_binding,
        save_binding=providers.save_ollama_binding,
        save_model=providers.save_ollama_model,
    )
    food_persistence = SQLiteFoodAdapter(db_path)
    evidence_port = food_evidence
    if evidence_port is None:
        from app.bootstrap.app_wiring.food import build_food_evidence

        if catalog is None:
            raise ValueError("Setup composition requires an injected Provider catalog")
        evidence_port = build_food_evidence(db_path, provider_catalog=catalog)
    return SetupServices(
        setup=SetupService(
            state=state,
            owners=setup_accounts,
            ollama=ollama,
            nest_choices=NestConfigSetupChoiceAdapter(),
            models=ProviderSetupCatalogAdapter(catalog),
        ),
        installation=SetupInstallationService(
            key=db_path,
            state=state,
            accounts=setup_accounts,
            ollama=ollama,
            providers=providers,
            food=SetupFoodAdapter(
                catalog=food_persistence,
                technology=ModelFoodTechnologyAdapter(evidence_port),
                evidence=evidence_port,
            ),
            nest=SetupNestAdapter(nest),
            runner=ThreadSetupInstallationRunner(),
        ),
    )


__all__ = ("SetupServices", "build_setup_services")
