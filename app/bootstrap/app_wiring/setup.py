"""Production composition for first-run Setup and its installation workflow."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from app.features.accounts import AccountsService
from app.features.configuration import ProviderLocalStatePort
from app.features.configuration.providers import StoredLocalProviderBinding
from app.features.setup import SetupService
from app.orchestration.setup_installation import (
    SetupInstallationService,
    SetupOllamaBinding,
    SetupOllamaTaskLease,
)
from infrastructure.models.food_technology import (
    FoodEvidencePort,
    ModelFoodTechnologyAdapter,
)
from infrastructure.models.ollama.lifecycle_ollama import OllamaLifecycleAdapter
from infrastructure.models.ollama.provider_ollama import PublicOllamaProviderAdapter
from infrastructure.models.providers.catalog import ProviderCatalog
from infrastructure.models.setup_catalog import ProviderSetupCatalogAdapter
from infrastructure.models.setup_food import SetupFoodAdapter
from infrastructure.models.setup_ollama import SetupOllamaAdapter
from infrastructure.models.setup_ollama_technology import (
    PublicOllamaSetupTechnologyAdapter,
)
from infrastructure.models.setup_provider import SetupProviderAdapter
from infrastructure.persistence.food import SQLiteFoodAdapter
from infrastructure.persistence.nest_db.nest_management import (
    SQLiteNestManagementAdapter,
)
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
    food_evidence: FoodEvidencePort | None = None,
    catalog: ProviderCatalog | None = None,
    data_home: Path | None = None,
) -> SetupServices:
    state = SQLiteSetupAdapter(db_path)
    setup_accounts = SetupAccountsAdapter(accounts)
    providers = SetupProviderAdapter(provider_state)
    ollama_task_lease_factory = _build_ollama_task_lease_factory(providers, data_home)
    ollama = SetupOllamaAdapter(
        technology=PublicOllamaSetupTechnologyAdapter(),
        load_binding=providers.load_ollama_binding,
        save_binding=providers.save_ollama_binding,
        save_model=providers.save_ollama_model,
        acquire_task_lease=ollama_task_lease_factory,
    )

    def acquire_setup_task_lease() -> Optional[SetupOllamaTaskLease]:
        if ollama_task_lease_factory is None:
            return None
        binding = providers.load_ollama_binding()
        if binding is None:
            return None
        return ollama_task_lease_factory(binding)

    setup_task_lease_factory = (
        acquire_setup_task_lease if ollama_task_lease_factory is not None else None
    )

    food_persistence = SQLiteFoodAdapter(db_path)
    evidence_port = food_evidence
    if evidence_port is None:
        from app.bootstrap.app_wiring.food import build_food_evidence

        evidence_port = build_food_evidence(db_path)
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
            ollama=ollama,
            providers=providers,
            food=SetupFoodAdapter(
                catalog=food_persistence,
                technology=ModelFoodTechnologyAdapter(evidence_port),
                evidence=evidence_port,
            ),
            nest=SetupNestAdapter(nest),
            runner=ThreadSetupInstallationRunner(),
            ollama_task_lease_factory=setup_task_lease_factory,
        ),
    )


def _build_ollama_task_lease_factory(
    providers: SetupProviderAdapter,
    data_home: Path | None,
) -> Callable[[SetupOllamaBinding], Optional[SetupOllamaTaskLease]] | None:
    """Share the user-scoped Ollama lease with Setup model downloads."""
    if data_home is None:
        return None

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
        PublicOllamaProviderAdapter(),
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
