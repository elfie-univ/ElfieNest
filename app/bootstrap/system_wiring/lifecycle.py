"""Production composition for the App Runtime lifecycle boundary."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

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


def runtime_projection_payload(
    lifecycle: LifecycleFacade, elfie_home: Path
) -> dict[str, object]:
    """Serialize the lifecycle-owned read-only projection for HTTP clients."""
    projection = lifecycle.runtime_projection(elfie_home)
    return {
        "schema_version": projection.schema_version,
        "instance_id": projection.instance_id,
        "generation": projection.generation,
        "revision": projection.revision,
        "tier": projection.tier.value,
        "phase": projection.phase.value,
        "subphase": projection.subphase,
        "desired_target": projection.desired_target.value,
        "reached_target": (
            projection.reached_target.value
            if projection.reached_target is not None
            else None
        ),
        "components": [
            {
                "component": item.component.value,
                "state": item.state.value,
                "detail": item.detail,
                "pid": item.pid,
                "executable": item.executable,
                "birth_identity": item.birth_identity,
            }
            for item in projection.components
        ],
        "endpoints": [
            {
                "name": item.name,
                "scheme": item.scheme,
                "host": item.host,
                "port": item.port,
                "protocol_version": item.protocol_version,
            }
            for item in projection.endpoints
        ],
        "model_state": projection.model_state.value,
        "model_common_state": projection.model_common_state.value,
        "model_emergency_state": projection.model_emergency_state.value,
        "model_revision": projection.model_revision,
        "failures": [
            {"code": item.code, "detail": item.detail, "phase": item.phase}
            for item in projection.failures
        ],
        "timings": [
            {
                "phase": item.phase,
                "duration_ms": item.duration_ms,
                "elapsed_ms": item.elapsed_ms,
            }
            for item in projection.timings
        ],
        "protocol_versions": list(projection.protocol_versions),
    }


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
        platform_value = installation.get("platform", "")
        if platform_value not in {"darwin", "linux", "win32"}:
            return None
        platform = cast(Literal["darwin", "linux", "win32"], platform_value)
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


def _build_offline_validator(
    db_path: str,
    data_home: Path | None = None,
) -> Callable[[], bool]:
    """Compose offline suites without making Doctor own model execution."""

    def validate() -> bool:
        from infrastructure.models.validation.food_validation import (
            FoodValidationRunner,
        )
        from infrastructure.models.validation.validation_models import ValidationReport
        from infrastructure.persistence.configuration.bundled_defaults import (
            load_tool_defaults,
        )
        from infrastructure.persistence.configuration.secrets import resolve_secret
        from infrastructure.persistence.food import SQLiteFoodAdapter
        from infrastructure.persistence.food_evidence import query_model_evidence
        from infrastructure.persistence.layout.data_layout import final_root_layout
        from infrastructure.persistence.model_execution_config import (
            load_model_execution_config,
        )
        from infrastructure.persistence.provider_catalog import load_provider_catalog
        from infrastructure.persistence.validation_artifacts import (
            save_validation_report,
        )
        from infrastructure.tools.validation.direct_validation import (
            DirectToolValidationRunner,
        )
        from infrastructure.tools.web_search.search import WebSearchPlugin

        layout = final_root_layout(data_home) if data_home is not None else None
        config = load_model_execution_config(
            str(data_home) if data_home is not None else None
        )
        provider_catalog = load_provider_catalog(
            layout.provider_catalog_config if layout is not None else None
        )
        tool_defaults = load_tool_defaults()
        tool_suite = DirectToolValidationRunner(
            config,
            search_plugin=WebSearchPlugin.from_model_execution_policy(
                config.runtime_policy,
                defaults=tool_defaults,
                secret_resolver=(
                    lambda name: resolve_secret(
                        name,
                        layout.auth_env if layout is not None else None,
                    )
                ),
            ),
        ).run(include_network=False)
        food_suite = FoodValidationRunner().validate(
            SQLiteFoodAdapter(db_path).load(),
            list(query_model_evidence(provider_catalog=provider_catalog).values()),
        )
        report = ValidationReport((tool_suite, food_suite))
        save_validation_report(
            report,
            layout.runtime_validations if layout is not None else None,
        )
        return report.passed

    return validate


def create_lifecycle_facade() -> LifecycleFacade:
    """Create one process-scoped lifecycle facade with explicit Adapter injection."""
    from app.interfaces.web.build_discovery import discover_web_build
    from app.orchestration.lifecycle import LifecycleFacade
    from infrastructure.godot.artifacts.web_build import GodotWebBuildAdapter
    from infrastructure.godot.lifecycle.authority import GodotAuthorityHostAdapter
    from infrastructure.models.ollama.lifecycle_ollama import OllamaLifecycleAdapter
    from infrastructure.models.ollama.provider_ollama import PublicOllamaProviderAdapter
    from infrastructure.persistence.layout.data_home import SOURCE_DATA_HOME_NAME
    from infrastructure.persistence.layout.lifecycle_data_home import (
        LifecycleDataHomeAdapter,
    )
    from infrastructure.persistence.model_health_projection import (
        FoodModelHealthProjectionAdapter,
    )
    from infrastructure.persistence.provider_catalog import load_provider_catalog
    from infrastructure.platform.doctor import LocalDoctorAdapter
    from infrastructure.platform.frontend_build import FrontendBuildAdapter
    from infrastructure.platform.lifecycle.controller_ipc import (
        LocalControllerIpcAdapter,
    )
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
    from infrastructure.platform.source_cli_state import SourceCliState
    from infrastructure.platform.uninstall import LocalUninstallAdapter
    from scripts.godot_species_validation import run_godot_species_validation

    inspector = DefaultProcessInspector()
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

    def runtime_record_factory(home: Path):
        return FileRuntimeRecordAdapter(
            local_data.paths(home),
            writer_token=os.environ.get("ELFIENEST_RUNTIME_WRITER_TOKEN"),
        )

    def source_cli_state_factory(source_root: Path):
        selected_home = (
            source_root.expanduser().resolve(strict=False) / SOURCE_DATA_HOME_NAME
        )
        return SourceCliState(local_data.paths(selected_home))

    def validate_current_root(data_home: Path | None = None) -> bool:
        """Read the target only when Doctor is actually invoked.

        Facade construction is deliberately root-neutral.  The CLI resolves a
        target first and publishes it to the short-lived command scope before
        any Doctor/configuration operation calls this closure.
        """

        from infrastructure.persistence.layout.data_home import (
            get_db_path,
            get_db_path_for_home,
        )

        if data_home is None:
            return _build_offline_validator(str(get_db_path()))()
        selected = data_home.expanduser().resolve(strict=False)
        return _build_offline_validator(
            str(get_db_path_for_home(selected)),
            selected,
        )()

    return LifecycleFacade(
        service_launch_command=service_launch_command,
        process_port=LocalServiceProcessAdapter(),
        recovery_lock=LocalRecoveryLockAdapter(),
        desktop_host=LocalDesktopHostAdapter(),
        http_probe=UrllibHttpProbeAdapter(),
        runtime_record_factory=runtime_record_factory,
        authority_host_factory=partial(
            GodotAuthorityHostAdapter,
            inspector=inspector,
        ),
        controller_ipc=LocalControllerIpcAdapter(),
        optional_component=OllamaLifecycleAdapter(
            PublicOllamaProviderAdapter(catalog_loader=load_provider_catalog),
            binding_loader=_load_configured_ollama_binding,
        ),
        model_projection_factory=FoodModelHealthProjectionAdapter,
        frontend_preparation=FrontendBuildAdapter(discover_web_build),
        godot_web_preparation=GodotWebBuildAdapter(
            godot_runner=run_godot_species_validation,
        ),
        data_home=local_data,
        doctor=LocalDoctorAdapter(
            local_data=local_data,
            offline_validator=validate_current_root,
        ),
        uninstall=LocalUninstallAdapter(local_data=local_data),
        source_cli_state_factory=source_cli_state_factory,
    )
