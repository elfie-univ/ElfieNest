"""Typed application container assembled at the production composition root."""

from __future__ import annotations

from dataclasses import dataclass

from ai_runtime.storage.data_home import data_home_from_db_path, get_config_path
from ai_runtime.storage.data_layout import final_root_layout
from app.features.accounts import AccountsService
from app.features.configuration import ProvidersService, SettingsService
from app.features.elfies import ElfiesService
from app.features.nest_management import NestManagementService
from infrastructure.models import ProviderModelsAdapter
from infrastructure.persistence import (
    SQLiteAccountsAdapter,
    SQLiteElfiesProjectionAdapter,
    SQLiteNestManagementAdapter,
)
from infrastructure.persistence.provider_references import (
    SQLiteProviderReferenceAdapter,
)
from infrastructure.platform import RuntimeSecurityPolicyAdapter, RuntimeSettingsAdapter


@dataclass(frozen=True)
class ApplicationContainer:
    accounts: AccountsService
    settings: SettingsService
    nest_management: NestManagementService
    elfies: ElfiesService
    providers: ProvidersService


def build_application_container(db_path: str) -> ApplicationContainer:
    config_path = get_config_path()
    if db_path != ":memory:":
        config_path = final_root_layout(data_home_from_db_path(db_path)).runtime_config
    accounts_adapter = SQLiteAccountsAdapter(db_path)
    settings_adapter = RuntimeSettingsAdapter(config_path)
    provider_models = ProviderModelsAdapter()
    return ApplicationContainer(
        accounts=AccountsService(
            sessions=accounts_adapter,
            security_policy=RuntimeSecurityPolicyAdapter(settings_adapter),
        ),
        settings=SettingsService(settings_adapter),
        nest_management=NestManagementService(SQLiteNestManagementAdapter(db_path)),
        elfies=ElfiesService(SQLiteElfiesProjectionAdapter(db_path)),
        providers=ProvidersService(
            catalog=provider_models,
            connections=provider_models,
            references=SQLiteProviderReferenceAdapter(db_path),
            technology=provider_models,
        ),
    )


__all__ = ("ApplicationContainer", "build_application_container")
