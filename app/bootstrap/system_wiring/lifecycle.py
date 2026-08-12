"""Production composition for the App Runtime lifecycle boundary."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from functools import partial
from pathlib import Path

from app.orchestration.lifecycle import LifecycleFacade
from infrastructure.godot.lifecycle.authority import GodotAuthorityHostAdapter
from infrastructure.models.ollama.lifecycle_ollama import OllamaLifecycleAdapter
from infrastructure.models.ollama.provider_ollama import PublicOllamaProviderAdapter
from infrastructure.models.validation.food_validation import FoodValidationRunner
from infrastructure.models.validation.validation_models import ValidationReport
from infrastructure.persistence.configuration.secrets import resolve_secret
from infrastructure.persistence.food import SQLiteFoodAdapter
from infrastructure.persistence.food_evidence import query_model_evidence
from infrastructure.persistence.layout.data_home import get_db_path
from infrastructure.persistence.layout.lifecycle_data_home import (
    LifecycleDataHomeAdapter,
)
from infrastructure.persistence.runtime_config import load_runtime_config
from infrastructure.persistence.validation_artifacts import save_validation_report
from infrastructure.platform.doctor import LocalDoctorAdapter
from infrastructure.platform.lifecycle.desktop import LocalDesktopHostAdapter
from infrastructure.platform.lifecycle.http_probe import UrllibHttpProbeAdapter
from infrastructure.platform.lifecycle.process import (
    DefaultProcessInspector,
    LocalServiceProcessAdapter,
)
from infrastructure.platform.lifecycle.recovery_lock import LocalRecoveryLockAdapter
from infrastructure.platform.lifecycle.runtime_record import FileRuntimeRecordAdapter
from infrastructure.platform.uninstall import LocalUninstallAdapter
from infrastructure.tools.validation.direct_validation import DirectToolValidationRunner
from infrastructure.tools.web_search.search import WebSearchPlugin


def _build_offline_validator(db_path: str) -> Callable[[], bool]:
    """Compose the existing offline suites without making Doctor own Runtime Lab."""

    def validate() -> bool:
        config = load_runtime_config()
        tool_suite = DirectToolValidationRunner(
            config,
            search_plugin=WebSearchPlugin.from_runtime_policy(
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
    inspector = DefaultProcessInspector()
    db_path = str(get_db_path())
    local_data = LifecycleDataHomeAdapter()
    project_root = Path(__file__).resolve().parents[3]
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
        optional_component=OllamaLifecycleAdapter(PublicOllamaProviderAdapter()),
        data_home=local_data,
        doctor=LocalDoctorAdapter(
            local_data=local_data,
            offline_validator=_build_offline_validator(db_path),
        ),
        uninstall=LocalUninstallAdapter(local_data=local_data),
    )
