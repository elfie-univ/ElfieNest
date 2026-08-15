"""Production composition for the App Runtime lifecycle boundary."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

from app.interfaces.api.runtime_capability import RuntimeCapabilityDenied
from app.orchestration.lifecycle.capability_gate import CapabilityDeniedError

if TYPE_CHECKING:
    from app.orchestration.lifecycle import LifecycleFacade


@dataclass(frozen=True)
class LifecycleRuntimeCapabilityGate:
    """Adapt the authoritative lifecycle permit issuer to the API Port."""

    lifecycle: LifecycleFacade
    elfie_home: Path

    def require(self, operation: str) -> None:
        try:
            self.lifecycle.issue_capability_permit(self.elfie_home, operation)
        except CapabilityDeniedError as error:
            raise RuntimeCapabilityDenied(error.code, error.detail) from error


def create_runtime_capability_gate(
    lifecycle: LifecycleFacade, elfie_home: Path
) -> LifecycleRuntimeCapabilityGate:
    return LifecycleRuntimeCapabilityGate(lifecycle, elfie_home)


def _load_configured_ollama_binding(elfie_home: Path):
    """Read the current data root's persisted local Ollama binding only."""
    from app.features.configuration.providers import StoredLocalProviderBinding
    from infrastructure.persistence.layout.data_layout import final_root_layout
    from infrastructure.persistence.provider_connections import ProviderConnectionStore

    document = ProviderConnectionStore(
        final_root_layout(elfie_home).providers_config
    ).load()
    for connection in document.connections.values():
        if (
            connection.catalog_id != "ollama"
            or not connection.enabled
            or connection.archived
            or not connection.api_base
        ):
            continue
        installation = connection.installation
        platform = installation.get("platform", "")
        if platform not in {"darwin", "linux", "win32"}:
            return None
        return StoredLocalProviderBinding(
            api_base=connection.api_base,
            platform=platform,
            install_kind=installation.get("install_kind", "existing-public"),
            launch_target=installation.get("launch_target", ""),
            version=installation.get("version", ""),
            installer_source_url=installation.get("installer_source_url", ""),
            installer_sha256=installation.get("installer_sha256", ""),
        )
    return None


def _build_offline_validator(db_path: str) -> Callable[[], bool]:
    """Compose offline suites without making Doctor own model execution."""

    def validate() -> bool:
        from infrastructure.models.validation.food_validation import (
            FoodValidationRunner,
        )
        from infrastructure.models.validation.validation_models import ValidationReport
        from infrastructure.persistence.configuration.secrets import resolve_secret
        from infrastructure.persistence.food import SQLiteFoodAdapter
        from infrastructure.persistence.food_evidence import query_model_evidence
        from infrastructure.persistence.model_execution_config import (
            load_model_execution_config,
        )
        from infrastructure.persistence.validation_artifacts import (
            save_validation_report,
        )
        from infrastructure.tools.validation.direct_validation import (
            DirectToolValidationRunner,
        )
        from infrastructure.tools.web_search.search import WebSearchPlugin

        config = load_model_execution_config()
        tool_suite = DirectToolValidationRunner(
            config,
            search_plugin=WebSearchPlugin.from_model_execution_policy(
                config.runtime_policy,
                secret_resolver=resolve_secret,
            ),
        ).run(include_network=False)
        food_suite = FoodValidationRunner().validate(
            SQLiteFoodAdapter(db_path).load(),
            list(query_model_evidence().values()),
        )
        report = ValidationReport((tool_suite, food_suite))
        save_validation_report(report)
        return report.passed

    return validate


def create_lifecycle_facade() -> LifecycleFacade:
    """Create one process-scoped lifecycle facade with explicit Adapter injection."""
    from app.interfaces.web.build_discovery import discover_web_build
    from app.orchestration.lifecycle import LifecycleFacade
    from infrastructure.godot.artifacts.web_build import GodotWebBuildAdapter
    from infrastructure.godot.lifecycle.authority import GodotAuthorityHostAdapter
    from infrastructure.models.model_health_projection import (
        FoodModelHealthProjectionAdapter,
    )
    from infrastructure.models.ollama.lifecycle_ollama import OllamaLifecycleAdapter
    from infrastructure.models.ollama.provider_ollama import PublicOllamaProviderAdapter
    from infrastructure.persistence.layout.data_home import get_db_path
    from infrastructure.persistence.layout.lifecycle_data_home import (
        LifecycleDataHomeAdapter,
    )
    from infrastructure.persistence.provider_catalog import load_provider_catalog
    from infrastructure.platform.doctor import LocalDoctorAdapter
    from infrastructure.platform.frontend_build import FrontendBuildAdapter
    from infrastructure.platform.lifecycle.desktop import LocalDesktopHostAdapter
    from infrastructure.platform.lifecycle.http_probe import UrllibHttpProbeAdapter
    from infrastructure.platform.lifecycle.process import (
        DefaultProcessInspector,
        LocalServiceProcessAdapter,
    )
    from infrastructure.platform.lifecycle.recovery_lock import LocalRecoveryLockAdapter
    from infrastructure.platform.lifecycle.runtime_record import (
        FileRuntimeRecordAdapter,
    )
    from infrastructure.platform.uninstall import LocalUninstallAdapter

    inspector = DefaultProcessInspector()
    db_path = str(get_db_path())
    provider_catalog = load_provider_catalog()
    local_data = LifecycleDataHomeAdapter()
    project_root = Path(
        os.environ.get("ELFIENEST_PROJECT_ROOT", Path(__file__).resolve().parents[3])
    ).resolve()
    packaged_core = os.environ.get("ELFIENEST_CORE_BIN")
    service_launch_command = (
        (packaged_core,)
        if packaged_core
        else (sys.executable, str((project_root / "scripts" / "serve.py").resolve()))
    )
    return LifecycleFacade(
        service_launch_command=service_launch_command,
        process_port=LocalServiceProcessAdapter(),
        recovery_lock=LocalRecoveryLockAdapter(),
        desktop_host=LocalDesktopHostAdapter(),
        http_probe=UrllibHttpProbeAdapter(),
        runtime_record_factory=FileRuntimeRecordAdapter,
        authority_host_factory=partial(
            GodotAuthorityHostAdapter,
            inspector=inspector,
        ),
        optional_component=OllamaLifecycleAdapter(
            PublicOllamaProviderAdapter(catalog=provider_catalog),
            binding_loader=_load_configured_ollama_binding,
        ),
        model_projection_factory=FoodModelHealthProjectionAdapter,
        frontend_preparation=FrontendBuildAdapter(discover_web_build),
        godot_web_preparation=GodotWebBuildAdapter(),
        data_home=local_data,
        doctor=LocalDoctorAdapter(
            local_data=local_data,
            offline_validator=_build_offline_validator(db_path),
        ),
        uninstall=LocalUninstallAdapter(local_data=local_data),
    )
