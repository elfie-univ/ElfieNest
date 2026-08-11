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
from infrastructure.persistence.layout.data_home import (
    data_home_from_db_path,
    get_config_path,
)
from infrastructure.persistence.layout.data_layout import final_root_layout
from infrastructure.persistence.provider_references import (
    SQLiteProviderReferenceAdapter,
)
from infrastructure.platform import RuntimeSettingsAdapter


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
    provider_models = ProviderModelsAdapter()
    if db_path != ":memory:":
        layout = final_root_layout(data_home_from_db_path(db_path))
        config_path = layout.runtime_config
        provider_models = ProviderModelsAdapter(
            layout.providers_config,
            layout.auth_env,
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
