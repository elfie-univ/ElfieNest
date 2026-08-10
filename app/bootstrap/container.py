"""Typed application container assembled at the production composition root."""

from __future__ import annotations

from dataclasses import dataclass

from ai_runtime.storage.data_home import data_home_from_db_path, get_config_path
from ai_runtime.storage.data_layout import final_root_layout
from app.features.accounts import AccountsService
from app.features.communication import CommunicationFacade
from app.features.configuration import (
    CapabilitiesService,
    ProvidersService,
    SettingsService,
)
from app.features.configuration.food import FoodService
from app.features.elfies import ElfiesService
from app.features.nest_management import NestManagementService
from app.features.operations import OperationsFacade
from app.orchestration.message_delivery import MessageDeliveryFacade
from app.orchestration.nest_session import NestSession
from app.orchestration.observer import ObserverFacade
from infrastructure.communication import OwnerMessageSession, SameOriginMessagePublisher
from infrastructure.models import ProviderModelsAdapter
from infrastructure.persistence import (
    SQLiteElfiesProjectionAdapter,
    SQLiteNestManagementAdapter,
)
from infrastructure.persistence.provider_references import (
    SQLiteProviderReferenceAdapter,
)
from infrastructure.platform import RuntimeSettingsAdapter
from infrastructure.tools import (
    DirectCapabilityValidationAdapter,
    RuntimeCapabilitiesAdapter,
    ToolCapabilitySecretAdapter,
)

from .accounts import build_accounts_service
from .communication import build_communication_services
from .food import build_food_service
from .observer import build_observer_facade
from .operations import build_operations_facade


@dataclass(frozen=True)
class ApplicationContainer:
    accounts: AccountsService
    settings: SettingsService
    nest_management: NestManagementService
    elfies: ElfiesService
    providers: ProvidersService
    food: FoodService
    capabilities: CapabilitiesService
    operations: OperationsFacade
    communication: CommunicationFacade
    message_delivery: MessageDeliveryFacade
    communication_realtime: SameOriginMessagePublisher
    observer: ObserverFacade


def build_application_container(
    db_path: str,
    *,
    message_session: OwnerMessageSession | None = None,
    observer_session: NestSession | None = None,
) -> ApplicationContainer:
    config_path = get_config_path()
    provider_models = ProviderModelsAdapter()
    data_home = None
    if db_path != ":memory:":
        data_home = data_home_from_db_path(db_path)
        layout = final_root_layout(data_home)
        config_path = layout.runtime_config
        provider_models = ProviderModelsAdapter(
            layout.providers_config,
            layout.auth_env,
        )
    settings_adapter = RuntimeSettingsAdapter(config_path)
    if db_path != ":memory:":
        local_provider = provider_models.get_product("ollama")
        if local_provider is not None:
            provider_models.ensure_local_connection(local_provider)
    elfies = ElfiesService(SQLiteElfiesProjectionAdapter(db_path))
    accounts = build_accounts_service(db_path, settings=settings_adapter)
    communication = build_communication_services(
        db_path,
        elfies=elfies,
        session=message_session,
    )
    return ApplicationContainer(
        accounts=accounts,
        settings=SettingsService(settings_adapter),
        nest_management=NestManagementService(SQLiteNestManagementAdapter(db_path)),
        elfies=elfies,
        providers=ProvidersService(
            catalog=provider_models,
            connections=provider_models,
            references=SQLiteProviderReferenceAdapter(db_path),
            technology=provider_models,
        ),
        food=build_food_service(db_path),
        capabilities=CapabilitiesService(
            RuntimeCapabilitiesAdapter(config_path),
            ToolCapabilitySecretAdapter(
                None if data_home is None else final_root_layout(data_home).auth_env
            ),
            DirectCapabilityValidationAdapter(),
        ),
        operations=build_operations_facade(db_path),
        communication=communication.communication,
        message_delivery=communication.message_delivery,
        communication_realtime=communication.realtime,
        observer=build_observer_facade(
            accounts=accounts,
            elfies=elfies,
            nest_session=observer_session,
        ),
    )


__all__ = ("ApplicationContainer", "build_application_container")
