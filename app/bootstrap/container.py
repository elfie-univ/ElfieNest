"""Typed application container assembled at the production composition root."""

from __future__ import annotations

from dataclasses import dataclass

from app.features.accounts import AccountsService
from app.features.adoption import AdoptionService
from app.features.bodies import BodiesService
from app.features.communication import CommunicationFacade
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
from infrastructure.models.ollama.provider_ollama import PublicOllamaProviderAdapter
from infrastructure.models.provider_administration import ProviderModelsAdapter
from infrastructure.persistence.elfie_workspace.bodies import SQLiteBodiesAdapter
from infrastructure.persistence.elfie_workspace.elfies import (
    SQLiteElfiesProjectionAdapter,
)
from infrastructure.persistence.elfie_workspace.embodiment import (
    SQLiteEmbodimentLeaseAdapter,
)
from infrastructure.persistence.layout.data_home import (
    data_home_from_db_path,
    get_config_path,
)
from infrastructure.persistence.layout.data_layout import final_root_layout
from infrastructure.persistence.nest_db.nest_management import (
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

from .app_wiring.accounts import build_accounts_service
from .app_wiring.adoption import build_adoption_services
from .app_wiring.communication import build_communication_services
from .app_wiring.food import build_food_service
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
    food: FoodService
    capabilities: CapabilitiesService
    operations: OperationsFacade
    communication: CommunicationFacade
    message_delivery: MessageDeliveryFacade
    communication_realtime: SameOriginMessagePublisher
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
    elfies = ElfiesService(SQLiteElfiesProjectionAdapter(db_path))
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
    )
    nest_adapter = SQLiteNestManagementAdapter(db_path)
    setup = build_setup_services(
        db_path,
        accounts=accounts,
        nest=nest_adapter,
        provider_state=provider_models,
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
        local_technology=PublicOllamaProviderAdapter(),
    )
    if db_path != ":memory:":
        providers.ensure_default_local_connection(
            EnsureDefaultLocalProviderConnectionCommand()
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
