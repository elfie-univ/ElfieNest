"""Typed application container assembled at the production composition root."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import cast

from app.features.accounts import AccountsService
from app.features.adoption import (
    AdoptionService,
    CandidatePortraitPort,
    SpeciesRuntimeReadinessPort,
)
from app.features.bodies import BodiesService
from app.features.communication import CommunicationFacade
from app.features.communication.discord_service import DiscordAccountsService
from app.features.communication.telegram_service import TelegramAccountsService
from app.features.configuration import (
    CapabilitiesService,
    EnsureDefaultLocalProviderConnectionCommand,
    ProvidersService,
    SettingsService,
)
from app.features.configuration.food import FoodService
from app.features.elfies import ElfiesService
from app.features.nest_management import NestManagementService
from app.features.operations import OperationsFacade
from app.features.setup import SetupService
from app.orchestration.embodiment import BodyDeviceChannel, EmbodimentSessionService
from app.orchestration.lifecycle import ApplicationRuntimeLifecycle
from app.orchestration.message_delivery import (
    MessageDeliveryFacade,
    MessageDeliveryOwnerBroadcaster,
)
from app.orchestration.nest_session import NestSession
from app.orchestration.observer import ObserverFacade, SessionLogoutWorkflow
from app.orchestration.resident_admission import ResidentAdmissionService
from app.orchestration.setup_installation import SetupInstallationService
from infrastructure.communication import OwnerMessageSession, SameOriginMessagePublisher
from infrastructure.devices import DeviceGateway
from infrastructure.models.adoption_narrative import AdoptionStructuredModelExecution
from infrastructure.models.model_execution_adapter import StructuredModelExecution
from infrastructure.models.ollama.provider_ollama import PublicOllamaProviderAdapter
from infrastructure.models.provider_administration import ProviderModelsAdapter
from infrastructure.models.providers.openai_chatgpt import OpenAIChatGptOAuthAdapter
from infrastructure.models.validation.core_validation_scheduler import (
    CoreValidationScheduler,
)
from infrastructure.models.validation.core_validation_worker import (
    CoreValidationWorker,
)
from infrastructure.models.validation.provider_scheduler import (
    ProviderValidationScheduler,
)
from infrastructure.models.validation.serving_food import build_serving_food_index
from infrastructure.persistence.configuration.bundled_defaults import (
    load_nest_config,
    load_system_defaults,
)
from infrastructure.persistence.configuration.oauth_credentials import (
    OAuthCredentialAdapter,
    OAuthCredentialStore,
)
from infrastructure.persistence.configuration.settings import RuntimeSettingsAdapter
from infrastructure.persistence.configuration.species import (
    load_and_configure_species_catalog,
)
from infrastructure.persistence.elfie_workspace.bodies import SQLiteBodiesAdapter
from infrastructure.persistence.elfie_workspace.elfies import (
    SQLiteElfiesProjectionAdapter,
)
from infrastructure.persistence.elfie_workspace.embodiment import (
    SQLiteEmbodimentLeaseAdapter,
)
from infrastructure.persistence.food import SQLiteFoodAdapter
from infrastructure.persistence.food_evidence import SQLiteFoodEvidenceAdapter
from infrastructure.persistence.layout.data_home import (
    data_home_from_db_path,
    get_config_path,
    get_provider_catalog_path,
)
from infrastructure.persistence.layout.data_layout import final_root_layout
from infrastructure.persistence.model_catalog import load_model_identities
from infrastructure.persistence.nest_db.nest_management import (
    SQLiteNestManagementAdapter,
)
from infrastructure.persistence.provider_availability import ProviderAvailabilityQuery
from infrastructure.persistence.provider_catalog import load_provider_catalog
from infrastructure.persistence.provider_connections import ProviderConnectionStore
from infrastructure.persistence.provider_references import (
    SQLiteProviderReferenceAdapter,
)
from infrastructure.persistence.provider_storage import ProviderStorageAdapter
from infrastructure.persistence.report_storage import ReportStorageAdapter

from .app_wiring.accounts import build_accounts_service
from .app_wiring.adoption import build_adoption_services
from .app_wiring.capabilities import build_capability_adapters
from .app_wiring.communication import build_communication_services
from .app_wiring.food import build_food_service, build_report_repository
from .app_wiring.observer import build_observer_facade
from .app_wiring.operations import build_operations_facade
from .app_wiring.setup import build_setup_services


@dataclass(frozen=True)
class ApplicationContainer:
    accounts: AccountsService
    settings: SettingsService
    nest_management: NestManagementService
    elfies: ElfiesService
    providers: ProvidersService
    availability: ProviderAvailabilityQuery
    provider_scheduler: ProviderValidationScheduler
    core_validation_worker: CoreValidationWorker | None
    food: FoodService
    capabilities: CapabilitiesService
    operations: OperationsFacade
    communication: CommunicationFacade
    message_delivery: MessageDeliveryFacade
    communication_realtime: SameOriginMessagePublisher
    telegram_accounts: TelegramAccountsService
    discord_accounts: DiscordAccountsService
    runtime_lifecycle: ApplicationRuntimeLifecycle
    observer: ObserverFacade
    session_logout: SessionLogoutWorkflow
    adoption: AdoptionService
    resident_admission: ResidentAdmissionService
    setup: SetupService
    setup_installation: SetupInstallationService
    bodies: BodiesService
    embodiment: EmbodimentSessionService
    body_device_channel: BodyDeviceChannel


def build_application_container(
    db_path: str,
    *,
    message_session: OwnerMessageSession | None = None,
    nest_session: NestSession | None = None,
    model_execution: StructuredModelExecution | None = None,
    portraits: CandidatePortraitPort | None = None,
    species_runtime: SpeciesRuntimeReadinessPort | None = None,
) -> ApplicationContainer:
    config_path = get_config_path()
    provider_catalog_path = get_provider_catalog_path()
    provider_store = ProviderConnectionStore()
    data_home = None
    if db_path != ":memory:":
        data_home = data_home_from_db_path(db_path)
        provider_catalog_path = final_root_layout(data_home).provider_catalog_config
    provider_catalog = load_provider_catalog(provider_catalog_path)
    identity_catalog = load_model_identities()
    system_defaults = load_system_defaults()
    species_catalog = load_and_configure_species_catalog()
    nest_config = load_nest_config()
    report_repository = build_report_repository(db_path)
    provider_storage = ProviderStorageAdapter(provider_store)
    provider_reports = ReportStorageAdapter(report_repository)
    provider_evidence = SQLiteFoodEvidenceAdapter(
        provider_store,
        report_repository,
        provider_catalog,
        secret_resolver=provider_storage.resolve_secret,
    )
    oauth_credentials = OAuthCredentialAdapter()
    provider_models = ProviderModelsAdapter(
        provider_storage,
        provider_reports,
        provider_evidence,
        oauth_credentials,
        catalog=provider_catalog,
        identity_catalog=identity_catalog,
        system_defaults=system_defaults,
    )
    if db_path != ":memory:":
        assert data_home is not None
        layout = final_root_layout(data_home)
        config_path = layout.runtime_config
        provider_store = ProviderConnectionStore(layout.providers_config)
        provider_storage = ProviderStorageAdapter(
            provider_store,
            secret_path=layout.auth_env,
        )
        provider_evidence = SQLiteFoodEvidenceAdapter(
            provider_store,
            report_repository,
            provider_catalog,
            secret_resolver=provider_storage.resolve_secret,
        )
        oauth_credentials = OAuthCredentialAdapter(
            OAuthCredentialStore(layout.oauth_credentials)
        )
        provider_models = ProviderModelsAdapter(
            provider_storage,
            provider_reports,
            provider_evidence,
            oauth_credentials,
            catalog=provider_catalog,
            identity_catalog=identity_catalog,
            system_defaults=system_defaults,
        )
    settings_adapter = RuntimeSettingsAdapter(config_path)
    food_persistence = SQLiteFoodAdapter(db_path)

    def serving_index():
        connections = provider_storage.load_connections()
        resolvable = tuple(
            f"{connection.connection_id}/{model.endpoint_model_id}"
            for connection in connections.values()
            if connection.enabled and not connection.archived
            for model in connection.models
        )
        food_packages = food_persistence.list_packages()
        default_food_id = next(
            (
                package.food_id
                for package in food_packages
                if package.system_role == "common"
            ),
            "",
        )
        emergency_food_id = next(
            (
                package.food_id
                for package in food_packages
                if package.system_role == "emergency"
            ),
            "",
        )
        return build_serving_food_index(
            food_packages,
            food_persistence.list_assignments(),
            default_food_id=default_food_id,
            emergency_food_id=emergency_food_id,
            observations=report_repository.current(subject_kind="model"),
            resolvable_references=resolvable,
        )

    def _validate_core_channel(reference: str, channel: str) -> object:
        if channel == "text":
            return asyncio.run(provider_models.probe_model(reference))
        capability_by_channel = {
            "reasoning": "reasoning",
            "vision": "vision",
            "tool": "tools",
        }
        capability = capability_by_channel.get(channel)
        if capability is None:
            raise ValueError(f"unsupported core validation channel: {channel}")
        return asyncio.run(
            provider_models.probe_model_capability(reference, capability)  # type: ignore[arg-type]
        )

    provider_models.set_serving_index(serving_index)
    availability = ProviderAvailabilityQuery(
        provider_storage,
        provider_reports,
        serving_index=serving_index,
        active_probe=lambda reference: asyncio.run(
            provider_models.probe_model(reference)
        ),
        active_capability_probe=lambda reference, capability: asyncio.run(
            provider_models.probe_model_capability(reference, capability)
        ),
        active_reachability_probe=lambda connection_id: asyncio.run(
            provider_models.probe_reachability(connection_id)
        ),
        config_fingerprint=lambda connection: provider_models.validation_fingerprint(
            connection.connection_id
        ),
        reachability_fingerprint=lambda connection: (
            provider_models.reachability_fingerprint(connection.connection_id)
        ),
    )
    core_validation_worker: CoreValidationWorker | None = None
    if data_home is not None:
        validation_scheduler = CoreValidationScheduler(
            final_root_layout(data_home).runtime_locks / "core-validation.lock",
            _validate_core_channel,
            current_index=serving_index,
        )
        core_validation_worker = CoreValidationWorker(
            lambda: availability.run_core_validation(validation_scheduler),
        )
    elfies = ElfiesService(
        SQLiteElfiesProjectionAdapter(db_path),
        catalog=species_catalog,
    )
    provider_scheduler = ProviderValidationScheduler(
        availability,
        serving_index,
        report_repository,
        connection_ids=lambda: tuple(
            connection.connection_id
            for connection in provider_storage.load_connections().values()
            if connection.enabled and not connection.archived
        ),
        # With a live Nest session the CoreValidationWorker is started by the
        # application lifecycle and owns model/channel probes.  The in-memory
        # and headless composition paths have no worker, so keep the legacy
        # scheduler's core checks there.
        check_core_models=nest_session is None,
        maintenance=lambda cutoff: report_repository.compact_observations(
            cutoff.isoformat()
        ),
    )
    accounts = build_accounts_service(db_path, settings=settings_adapter)
    communication = build_communication_services(
        db_path,
        accounts=accounts,
        elfies=elfies,
        session=nest_session if message_session is None else message_session,
    )
    if nest_session is not None:
        nest_session.owner_broadcaster = MessageDeliveryOwnerBroadcaster(
            communication.message_delivery
        )
    adoption = build_adoption_services(
        db_path,
        settings=settings_adapter,
        nest_session=nest_session,
        model_execution=(
            None
            if model_execution is None
            else cast(AdoptionStructuredModelExecution, model_execution)
        ),
        portraits=portraits,
        nest_config=nest_config,
        catalog=species_catalog,
        species_runtime=species_runtime,
    )
    nest_adapter = SQLiteNestManagementAdapter(db_path, nest_config=nest_config)
    setup = build_setup_services(
        db_path,
        accounts=accounts,
        nest=nest_adapter,
        provider_state=provider_models,
        food_evidence=provider_evidence,
        catalog=provider_catalog,
        data_home=data_home,
    )
    bodies = BodiesService(SQLiteBodiesAdapter(db_path))
    embodiment = EmbodimentSessionService(SQLiteEmbodimentLeaseAdapter(db_path))
    body_gateway = DeviceGateway()
    observer = build_observer_facade(
        accounts=accounts,
        elfies=elfies,
        nest_session=nest_session,
    )
    providers = ProvidersService(
        catalog=provider_models,
        connections=provider_models,
        references=SQLiteProviderReferenceAdapter(db_path),
        technology=provider_models,
        local_state=provider_models,
        local_technology=PublicOllamaProviderAdapter(catalog=provider_catalog),
        oauth=OpenAIChatGptOAuthAdapter(oauth_credentials),
    )
    if db_path != ":memory:":
        providers.ensure_default_local_connection(
            EnsureDefaultLocalProviderConnectionCommand()
        )
    capability_config, capability_secrets, capability_validation = (
        build_capability_adapters(
            config_path,
            None if data_home is None else final_root_layout(data_home).auth_env,
        )
    )
    return ApplicationContainer(
        accounts=accounts,
        settings=SettingsService(
            settings_adapter,
            security_settings_changed=accounts,
        ),
        nest_management=NestManagementService(nest_adapter),
        elfies=elfies,
        providers=providers,
        availability=availability,
        core_validation_worker=core_validation_worker,
        food=build_food_service(
            db_path,
            provider_catalog=provider_catalog,
            evidence=provider_evidence,
        ),
        provider_scheduler=provider_scheduler,
        capabilities=CapabilitiesService(
            capability_config,
            capability_secrets,
            capability_validation,
        ),
        operations=build_operations_facade(db_path),
        communication=communication.communication,
        message_delivery=communication.message_delivery,
        communication_realtime=communication.realtime,
        telegram_accounts=communication.telegram_accounts,
        discord_accounts=communication.discord_accounts,
        runtime_lifecycle=ApplicationRuntimeLifecycle(
            (communication.telegram_runtime, communication.discord_runtime)
        ),
        observer=observer,
        session_logout=SessionLogoutWorkflow(accounts, observer),
        adoption=adoption.adoption,
        resident_admission=adoption.resident_admission,
        setup=setup.setup,
        setup_installation=setup.installation,
        bodies=bodies,
        embodiment=embodiment,
        body_device_channel=BodyDeviceChannel(
            bodies=bodies,
            gateway=body_gateway,
        ),
    )


__all__ = ("ApplicationContainer", "build_application_container")
