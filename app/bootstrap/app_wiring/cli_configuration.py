"""Narrow production composition for the local configuration CLI."""

from __future__ import annotations

from dataclasses import dataclass

from app.features.accounts import AccountPrincipal
from app.features.configuration import (
    CapabilitiesService,
    EnsureDefaultLocalProviderConnectionCommand,
    ProvidersService,
    SettingsService,
)
from app.features.configuration.food import FoodService
from infrastructure.models.cli_catalog import CliModelCatalogAdapter
from infrastructure.models.ollama.provider_ollama import PublicOllamaProviderAdapter
from infrastructure.models.provider_administration import ProviderModelsAdapter
from infrastructure.persistence.configuration.bundled_defaults import (
    load_system_defaults,
)
from infrastructure.persistence.configuration.settings import RuntimeSettingsAdapter
from infrastructure.persistence.food_evidence import SQLiteFoodEvidenceAdapter
from infrastructure.persistence.layout.data_home import (
    data_home_from_db_path,
    get_config_path,
    get_provider_catalog_path,
)
from infrastructure.persistence.layout.data_layout import final_root_layout
from infrastructure.persistence.model_catalog import (
    load_model_catalog,
    load_model_identities,
)
from infrastructure.persistence.provider_catalog import load_provider_catalog
from infrastructure.persistence.provider_connections import ProviderConnectionStore
from infrastructure.persistence.provider_references import (
    SQLiteProviderReferenceAdapter,
)
from infrastructure.persistence.provider_storage import ProviderStorageAdapter
from infrastructure.persistence.report_storage import ReportStorageAdapter

from .capabilities import build_capability_adapters
from .food import build_food_service, build_report_repository


@dataclass(frozen=True)
class CliConfigurationContainer:
    providers: ProvidersService
    food: FoodService
    capabilities: CapabilitiesService
    settings: SettingsService
    principal: AccountPrincipal
    models: CliModelCatalogAdapter


def build_cli_configuration(db_path: str) -> CliConfigurationContainer:
    layout = (
        None
        if db_path == ":memory:"
        else final_root_layout(data_home_from_db_path(db_path))
    )
    config_path = get_config_path() if layout is None else layout.runtime_config
    secret_path = None if layout is None else layout.auth_env
    provider_catalog_path = (
        get_provider_catalog_path()
        if layout is None
        else layout.provider_catalog_config
    )
    provider_catalog = load_provider_catalog(provider_catalog_path)
    identity_catalog = load_model_identities()
    model_catalog = load_model_catalog()
    system_defaults = load_system_defaults()
    report_repository = build_report_repository(db_path)
    provider_reports = ReportStorageAdapter(report_repository)
    provider_store = ProviderConnectionStore(
        None if layout is None else layout.providers_config
    )
    provider_storage = ProviderStorageAdapter(
        provider_store,
        secret_path=secret_path,
    )
    provider_evidence = SQLiteFoodEvidenceAdapter(
        provider_store,
        report_repository,
        provider_catalog,
        secret_resolver=provider_storage.resolve_secret,
    )
    provider_models = ProviderModelsAdapter(
        provider_storage,
        provider_reports,
        provider_evidence,
        catalog=provider_catalog,
        identity_catalog=identity_catalog,
        system_defaults=system_defaults,
    )
    providers = ProvidersService(
        catalog=provider_models,
        connections=provider_models,
        references=SQLiteProviderReferenceAdapter(db_path),
        technology=provider_models,
        local_state=provider_models,
        local_technology=PublicOllamaProviderAdapter(catalog=provider_catalog),
    )
    if db_path != ":memory:":
        providers.ensure_default_local_connection(
            EnsureDefaultLocalProviderConnectionCommand()
        )

    capability_config, capability_secrets, capability_validation = (
        build_capability_adapters(
            config_path,
            secret_path,
            data_home=None if layout is None else layout.data_home,
        )
    )
    return CliConfigurationContainer(
        providers=providers,
        food=build_food_service(
            db_path,
            provider_catalog=provider_catalog,
            evidence=provider_evidence,
        ),
        capabilities=CapabilitiesService(
            capability_config,
            capability_secrets,
            capability_validation,
        ),
        settings=SettingsService(RuntimeSettingsAdapter(config_path)),
        principal=AccountPrincipal(
            user_id=0,
            account_id="local-cli",
            role="owner",
            default_landing_page="manage",
        ),
        models=CliModelCatalogAdapter(model_catalog),
    )


__all__ = ("CliConfigurationContainer", "build_cli_configuration")
