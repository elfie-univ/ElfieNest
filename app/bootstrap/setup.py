"""Production composition for first-run Setup and its installation workflow."""

from __future__ import annotations

from dataclasses import dataclass

from app.features.accounts import AccountsService
from app.features.configuration import ProviderLocalStatePort
from app.features.setup import SetupService
from app.orchestration.setup_installation import SetupInstallationService
from infrastructure.models.food_technology import RuntimeFoodTechnologyAdapter
from infrastructure.models.setup_catalog import ProviderSetupCatalogAdapter
from infrastructure.models.setup_food import SetupFoodAdapter
from infrastructure.models.setup_ollama import SetupOllamaAdapter
from infrastructure.models.setup_ollama_technology import (
    PublicOllamaSetupTechnologyAdapter,
)
from infrastructure.models.setup_provider import SetupProviderAdapter
from infrastructure.persistence.food import SQLiteFoodAdapter
from infrastructure.persistence.nest_management import SQLiteNestManagementAdapter
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
    return SetupServices(
        setup=SetupService(
            state=state,
            owners=setup_accounts,
            ollama=ollama,
            nest_choices=NestConfigSetupChoiceAdapter(),
            models=ProviderSetupCatalogAdapter(),
        ),
        installation=SetupInstallationService(
            key=db_path,
            state=state,
            accounts=setup_accounts,
            ollama=ollama,
            providers=providers,
            food=SetupFoodAdapter(
                catalog=food_persistence,
                technology=RuntimeFoodTechnologyAdapter(),
            ),
            nest=SetupNestAdapter(nest),
            runner=ThreadSetupInstallationRunner(),
        ),
    )


__all__ = ("SetupServices", "build_setup_services")
