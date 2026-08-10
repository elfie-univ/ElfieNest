"""The five real side-effect phases executed after Setup confirmation."""

from __future__ import annotations

from typing import Callable

from ai_runtime.food.store import FoodCatalogRepository
from ai_runtime.storage.provider_connections import ProviderConnectionStore
from ai_runtime.storage.report_repository import ReportRepository
from app.features.setup.ollama import OllamaSetupService
from app.infrastructure.ollama_platform import OllamaPlatformAdapter
from app.infrastructure.persistence.food_packages import SQLiteFoodPackageRepository
from app.infrastructure.persistence.nest_repository import SQLiteNestRepository
from app.infrastructure.persistence.setup_install_repository import (
    SetupInstallRepository,
)
from app.infrastructure.persistence.store import get_db


def run_setup_installation(
    db_path: str,
    *,
    adapter: OllamaPlatformAdapter | None = None,
    food_catalog_repository: FoodCatalogRepository | None = None,
    report_repository: ReportRepository | None = None,
) -> None:
    """Run or resume the locked Setup draft from its persisted phase."""
    draft = SetupInstallRepository(db_path).get_draft()
    if not draft.complete or draft.locked_at is None:
        raise RuntimeError("Setup 安装草稿未锁定或不完整")
    installs = SetupInstallRepository(db_path)
    record = installs.get()
    if record.status == "completed":
        return
    service = OllamaSetupService(
        adapter=adapter or OllamaPlatformAdapter(),
        food_catalog_repository=food_catalog_repository
        or SQLiteFoodPackageRepository(db_path),
        report_repository=report_repository,
    )
    model_reference: str | None = None
    phase = record.install_step or 2
    if phase <= 2:
        if draft.use_local_ollama:
            binding = service.ensure_for_install(
                report_action=_phase_report(installs, 2),
            )
            _ = binding
        else:
            _phase_report(installs, 2)("ollama.skipped")
        installs.complete_phase(phase=2)
        phase = 3
    if draft.use_local_ollama and phase <= 3:
        if draft.model_id is None:
            raise RuntimeError("Setup 模型草稿缺失")
        model_reference = service.ensure_model_for_install(
            model_id=draft.model_id,
            report_action=_phase_report(installs, 3),
        )
        installs.complete_phase(phase=3)
        phase = 4
    elif not draft.use_local_ollama and phase <= 3:
        _phase_report(installs, 3)("model.skipped")
        installs.complete_phase(phase=3)
        phase = 4
    if draft.use_local_ollama and phase <= 4:
        model_reference = model_reference or _configured_model_reference(draft.model_id)
        if model_reference is None:
            raise RuntimeError("Setup 模型连接记录缺失")
        _phase_report(installs, 4)("food.emergency")
        service.generate_emergency_food(model_reference)
        installs.complete_phase(phase=4)
        phase = 5
    elif not draft.use_local_ollama and phase <= 4:
        _phase_report(installs, 4)("food.skipped")
        installs.complete_phase(phase=4)
        phase = 5
    if phase <= 5:
        if draft.bed_count is None:
            raise RuntimeError("Setup 床位草稿缺失")
        _phase_report(installs, 5)("nest.apply")
        with get_db(db_path) as connection:
            SQLiteNestRepository(connection).set_desired_bed_count(draft.bed_count)
            connection.commit()
        installs.complete_phase(phase=5)


def _phase_report(
    repository: SetupInstallRepository, phase: int
) -> Callable[[str], None]:
    starts = {2: 20, 3: 40, 4: 60, 5: 80}
    offsets = {2: 10, 3: 10, 4: 10, 5: 10}

    def report(action_key: str) -> None:
        repository.update(
            phase=phase,
            action_key=action_key,
            progress=starts[phase] + offsets[phase],
        )

    return report


def _configured_model_reference(model_id: str | None) -> str | None:
    if model_id is None:
        return None
    connection_store = ProviderConnectionStore()
    connection = next(
        (
            item
            for item in connection_store.load().connections.values()
            if item.catalog_id == "ollama"
        ),
        None,
    )
    if connection is None:
        return None
    if not any(model.endpoint_model_id == model_id for model in connection.models):
        return None
    return f"{connection.connection_id}/{model_id}"


__all__ = ("run_setup_installation",)
