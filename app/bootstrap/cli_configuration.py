"""Narrow production composition for the local configuration CLI."""

from __future__ import annotations

from dataclasses import dataclass

from app.features.accounts import AccountPrincipal
from app.features.configuration import ProvidersService, SettingsService
from infrastructure.models.cli_catalog import CliModelCatalogAdapter
from infrastructure.models.provider_administration import ProviderModelsAdapter
from infrastructure.models.provider_ollama import PublicOllamaProviderAdapter
from infrastructure.persistence.data_home import data_home_from_db_path, get_config_path
from infrastructure.persistence.data_layout import final_root_layout
from infrastructure.persistence.provider_references import (
    SQLiteProviderReferenceAdapter,
)
from infrastructure.platform import RuntimeSettingsAdapter
from infrastructure.platform.runtime_lab_menus import RuntimeLabMenusAdapter


@dataclass(frozen=True)
class CliConfigurationContainer:
    providers: ProvidersService
    settings: SettingsService
    principal: AccountPrincipal
    models: CliModelCatalogAdapter
    runtime_menus: RuntimeLabMenusAdapter


def build_cli_configuration(db_path: str) -> CliConfigurationContainer:
    config_path = get_config_path()
    provider_models = ProviderModelsAdapter()
    if db_path != ":memory:":
        layout = final_root_layout(data_home_from_db_path(db_path))
        config_path = layout.runtime_config
        provider_models = ProviderModelsAdapter(
            layout.providers_config,
            layout.auth_env,
        )
        local_provider = provider_models.get_product("ollama")
        if local_provider is not None:
            provider_models.ensure_local_connection(local_provider)

    return CliConfigurationContainer(
        providers=ProvidersService(
            catalog=provider_models,
            connections=provider_models,
            references=SQLiteProviderReferenceAdapter(db_path),
            technology=provider_models,
            local_state=provider_models,
            local_technology=PublicOllamaProviderAdapter(),
        ),
        settings=SettingsService(RuntimeSettingsAdapter(config_path)),
        principal=AccountPrincipal(
            user_id=0,
            account_id="local-cli",
            role="owner",
            default_landing_page="manage",
        ),
        models=CliModelCatalogAdapter(),
        runtime_menus=RuntimeLabMenusAdapter(),
    )


__all__ = ("CliConfigurationContainer", "build_cli_configuration")
