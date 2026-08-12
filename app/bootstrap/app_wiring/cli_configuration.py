"""Narrow production composition for the local configuration CLI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.features.accounts import AccountPrincipal
from app.features.configuration import (
    EnsureDefaultLocalProviderConnectionCommand,
    ProvidersService,
    SettingsService,
)
from infrastructure.models.cli_catalog import CliModelCatalogAdapter
from infrastructure.models.ollama.provider_ollama import PublicOllamaProviderAdapter
from infrastructure.models.provider_administration import ProviderModelsAdapter
from infrastructure.persistence.configuration.settings import RuntimeSettingsAdapter
from infrastructure.persistence.food_evidence import SQLiteFoodEvidenceAdapter
from infrastructure.persistence.layout.data_home import (
    data_home_from_db_path,
    get_config_path,
)
from infrastructure.persistence.layout.data_layout import final_root_layout
from infrastructure.persistence.provider_connections import ProviderConnectionStore
from infrastructure.persistence.provider_references import (
    SQLiteProviderReferenceAdapter,
)
from infrastructure.persistence.provider_storage import ProviderStorageAdapter
from infrastructure.persistence.report_storage import ReportStorageAdapter
from infrastructure.persistence.reports.report_repository import ReportRepository


class RuntimeConfigMenus(Protocol):
    """Developer CLI menus supplied by the Runtime Lab entrypoint."""

    def tool_menu(self) -> None: ...

    def food_menu(self) -> None: ...


@dataclass(frozen=True)
class CliConfigurationContainer:
    providers: ProvidersService
    settings: SettingsService
    principal: AccountPrincipal
    models: CliModelCatalogAdapter
    runtime_menus: RuntimeConfigMenus


def build_cli_configuration(
    db_path: str,
    *,
    runtime_menus: RuntimeConfigMenus,
) -> CliConfigurationContainer:
    config_path = get_config_path()
    provider_reports = ReportStorageAdapter(ReportRepository())
    provider_store = ProviderConnectionStore()
    provider_models = ProviderModelsAdapter(
        ProviderStorageAdapter(provider_store),
        provider_reports,
        SQLiteFoodEvidenceAdapter(provider_store, ReportRepository()),
    )
    if db_path != ":memory:":
        layout = final_root_layout(data_home_from_db_path(db_path))
        config_path = layout.runtime_config
        provider_store = ProviderConnectionStore(layout.providers_config)
        provider_models = ProviderModelsAdapter(
            ProviderStorageAdapter(
                provider_store,
                secret_path=layout.auth_env,
            ),
            provider_reports,
            SQLiteFoodEvidenceAdapter(provider_store, ReportRepository()),
        )
    providers = ProvidersService(
        catalog=provider_models,
        connections=provider_models,
        references=SQLiteProviderReferenceAdapter(db_path),
        technology=provider_models,
        local_state=provider_models,
        local_technology=PublicOllamaProviderAdapter(),
    )
    if db_path != ":memory:":
        providers.ensure_default_local_connection(
            EnsureDefaultLocalProviderConnectionCommand()
        )

    return CliConfigurationContainer(
        providers=providers,
        settings=SettingsService(RuntimeSettingsAdapter(config_path)),
        principal=AccountPrincipal(
            user_id=0,
            account_id="local-cli",
            role="owner",
            default_landing_page="manage",
        ),
        models=CliModelCatalogAdapter(),
        runtime_menus=runtime_menus,
    )


__all__ = ("CliConfigurationContainer", "build_cli_configuration")
