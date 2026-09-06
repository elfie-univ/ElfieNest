"""Production composition for first-run Setup and its installation workflow."""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from app.features.accounts import AccountPrincipal, AccountsService
from app.features.configuration import ProviderLocalStatePort
from app.features.configuration.food import (
    FoodError,
    FoodRolesInput,
    FoodService,
    ListFoodPackagesQuery,
    PreviewFoodGenerationCommand,
    UpdateFoodPackageCommand,
)
from app.features.configuration.providers import (
    ListProviderConnectionsQuery,
    ProvidersError,
    ProvidersService,
    StoredLocalProviderBinding,
    VerifyProviderConnectionCommand,
)
from app.features.nest_management import NestManagementCommandPort
from app.features.setup import SetupService
from app.orchestration.lifecycle.ports import ProcessIdentityReaderPort
from app.orchestration.nest_session import NestSession
from app.orchestration.setup_installation import (
    CreatedSetupOwner,
    SetupInstallationPortError,
    SetupInstallationService,
    SetupModelValidationResult,
    SetupOllamaBinding,
    SetupOllamaTaskLease,
    SetupRemotePreparationPort,
    SetupRuntimeReadinessPort,
)
from infrastructure.models.food_technology import FoodEvidencePort
from infrastructure.models.ollama.lifecycle_ollama import OllamaLifecycleAdapter
from infrastructure.models.ollama.provider_ollama import PublicOllamaProviderAdapter
from infrastructure.models.providers.catalog import ProviderCatalog
from infrastructure.models.setup_catalog import ProviderSetupCatalogAdapter
from infrastructure.models.setup_ollama import SetupOllamaAdapter
from infrastructure.models.setup_ollama_technology import (
    PublicOllamaSetupTechnologyAdapter,
)
from infrastructure.models.setup_provider import SetupProviderAdapter
from infrastructure.persistence.setup import SQLiteSetupAdapter
from infrastructure.persistence.setup_accounts import SetupAccountsAdapter
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
    nest: NestManagementCommandPort,
    nest_session: NestSession | None,
    providers_service: ProvidersService,
    food_service: FoodService,
    provider_state: ProviderLocalStatePort,
    food_evidence: FoodEvidencePort | None = None,
    catalog: ProviderCatalog | None = None,
    data_home: Path | None = None,
    process_identity_reader: ProcessIdentityReaderPort,
) -> SetupServices:
    state = SQLiteSetupAdapter(db_path)
    setup_accounts = SetupAccountsAdapter(accounts)
    providers = SetupProviderAdapter(provider_state)
    ollama_task_lease_factory = _build_ollama_task_lease_factory(
        providers,
        data_home,
        catalog,
        process_identity_reader,
    )
    ollama = SetupOllamaAdapter(
        technology=PublicOllamaSetupTechnologyAdapter(
            process_identity_reader=process_identity_reader
        ),
        load_binding=providers.load_ollama_binding,
        save_binding=providers.save_ollama_binding,
        save_model=providers.save_ollama_model,
        acquire_task_lease=ollama_task_lease_factory,
    )

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
            preparation=_SetupRemotePreparationAdapter(
                providers_service,
                food_service,
            ),
            nest=nest,
            runtime=_SetupRuntimeReadinessAdapter(nest_session),
            runner=ThreadSetupInstallationRunner(),
        ),
    )


class _SetupRemotePreparationAdapter(SetupRemotePreparationPort):
    """Bridge Setup to the existing Provider and Food feature facades."""

    def __init__(self, providers: ProvidersService, food: FoodService) -> None:
        self._providers = providers
        self._food = food

    @staticmethod
    def _principal(owner: CreatedSetupOwner) -> AccountPrincipal:
        return AccountPrincipal(
            user_id=owner.user_id,
            account_id=owner.account_id,
            role="owner",
        )

    def validate_models(
        self,
        owner: CreatedSetupOwner,
        connection_id: str,
    ) -> SetupModelValidationResult:
        principal = self._principal(owner)
        try:
            # Step 2 performs one lightweight model smoke check in the web
            # setup flow. This adapter is the locked Step 3 boundary that
            # records evidence for every selected model.
            asyncio.run(
                self._providers.verify_connection(
                    principal,
                    VerifyProviderConnectionCommand(
                        connection_id=connection_id,
                        force_full=True,
                    ),
                )
            )
            connection = next(
                (
                    item
                    for item in self._providers.list_connections(
                        principal, ListProviderConnectionsQuery()
                    )
                    if item.connection_id == connection_id
                ),
                None,
            )
        except ProvidersError as error:
            raise SetupInstallationPortError(
                "远程模型验证失败，请检查订阅配置"
            ) from error
        if connection is None:
            raise SetupInstallationPortError("远程订阅连接记录不存在")
        active_models = tuple(
            model
            for model in connection.models
            if model.discovery_state == "present"
            and not model.hidden
            and not model.retired
        )
        passed = tuple(
            model
            for model in active_models
            if model.available and model.verification.status == "passed"
        )
        return SetupModelValidationResult(
            total=len(active_models),
            passed=len(passed),
        )

    def prepare_common_food(self, owner: CreatedSetupOwner, connection_id: str) -> None:
        principal = self._principal(owner)
        try:
            catalog = self._food.list_packages(principal, ListFoodPackagesQuery())
            common = next(
                (
                    package
                    for package in catalog.packages
                    if package.food_id == catalog.global_default_food_id
                ),
                None,
            )
            if common is None:
                raise SetupInstallationPortError("常用粮配置不存在")
            preview = self._food.preview_generation(
                principal,
                PreviewFoodGenerationCommand(
                    connection_ids=(connection_id,),
                    local_first=False,
                    allow_remote=True,
                    visibility_mode="global",
                    visible_user_ids=(),
                    food_id=common.food_id,
                ),
            )
            candidate = preview.candidate
            if not candidate.enabled or candidate.roles.primary is None:
                raise SetupInstallationPortError("没有可用于常用粮的远程模型")
            self._food.update_package(
                principal,
                UpdateFoodPackageCommand(
                    food_id=common.food_id,
                    display_name=candidate.display_name,
                    enabled=True,
                    roles=FoodRolesInput(
                        primary=None
                        if candidate.roles.primary is None
                        else candidate.roles.primary.model,
                        reasoning=None
                        if candidate.roles.reasoning is None
                        else candidate.roles.reasoning.model,
                        vision=None
                        if candidate.roles.vision is None
                        else candidate.roles.vision.model,
                        tool=None
                        if candidate.roles.tool is None
                        else candidate.roles.tool.model,
                        fallback=None
                        if candidate.roles.fallback is None
                        else candidate.roles.fallback.model,
                    ),
                    visibility_mode=candidate.visibility_mode,
                    visible_user_ids=candidate.visible_user_ids,
                    required_roles=common.required_roles,
                ),
            )
        except SetupInstallationPortError:
            raise
        except FoodError as error:
            raise SetupInstallationPortError(
                "常用粮生成失败，请到管理页检查模型配置"
            ) from error


class _SetupRuntimeReadinessAdapter(SetupRuntimeReadinessPort):
    """Wait on the existing lifecycle-owned Runtime; never start a process."""

    def __init__(
        self,
        session: NestSession | None,
        *,
        timeout_seconds: float = 120.0,
    ) -> None:
        self._session = session
        self._timeout_seconds = timeout_seconds

    def ensure_ready(self, cancelled: Callable[[], bool]) -> None:
        if self._session is None:
            raise SetupInstallationPortError("精灵巢运行时不可用，请到管理页检查服务")
        deadline = time.monotonic() + self._timeout_seconds
        while not self._session.runtime_world_ready:
            if cancelled():
                return
            if time.monotonic() >= deadline:
                raise SetupInstallationPortError(
                    "精灵巢运行时未就绪，请到管理页检查服务后重试"
                )
            time.sleep(0.1)


def _build_ollama_task_lease_factory(
    providers: SetupProviderAdapter,
    data_home: Path | None,
    catalog: ProviderCatalog | None,
    process_identity_reader: ProcessIdentityReaderPort,
) -> Callable[[SetupOllamaBinding], Optional[SetupOllamaTaskLease]] | None:
    """Share the user-scoped Ollama lease with Setup model downloads."""
    if data_home is None:
        return None
    if catalog is None:
        raise ValueError(
            "Ollama lease composition requires an injected Provider catalog"
        )

    def load_binding(_home: Path) -> StoredLocalProviderBinding | None:
        binding = providers.load_ollama_binding()
        if binding is None:
            return None
        return StoredLocalProviderBinding(
            api_base=binding.api_base,
            platform=binding.platform,
            install_kind=binding.install_kind,
            launch_target=binding.launch_target,
            version=binding.version,
            installer_source_url=binding.installer_source_url,
            installer_sha256=binding.installer_sha256,
        )

    lifecycle = OllamaLifecycleAdapter(
        PublicOllamaProviderAdapter(
            catalog=catalog,
            process_identity_reader=process_identity_reader,
        ),
        process_identity_reader=process_identity_reader,
        binding_loader=load_binding,
    )
    owner_id = f"setup:{os.getpid()}"
    instance_id = (
        "setup-"
        + hashlib.sha256(str(data_home.resolve()).encode("utf-8")).hexdigest()[:16]
    )

    def acquire(_binding: SetupOllamaBinding) -> Optional[SetupOllamaTaskLease]:
        return lifecycle.acquire(
            owner_id=owner_id,
            instance_id=instance_id,
            generation=1,
            elfie_home=data_home,
        )

    return acquire


__all__ = ("SetupServices", "build_setup_services")
