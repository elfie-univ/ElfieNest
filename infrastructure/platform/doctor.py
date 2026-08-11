"""Local offline diagnostics implementing the lifecycle Doctor Port."""

from __future__ import annotations

from collections.abc import Callable

from app.orchestration.lifecycle import DoctorRepairResult, DoctorValidationResult
from infrastructure.persistence.layout.data_home import (
    ensure_elfie_home,
    get_elfie_home,
    get_logs_dir,
    get_model_validation_dir,
    get_runtime_locks_dir,
    get_runtime_validation_dir,
)


class LocalDoctorAdapter:
    def __init__(
        self,
        *,
        offline_validator: Callable[[], bool] | None = None,
    ) -> None:
        self._offline_validator = offline_validator

    def repair_local_state(self) -> DoctorRepairResult:
        home = get_elfie_home()
        expected_dirs = (
            home,
            home / "assets",
            home / "assets" / "users",
            home / "configs",
            home / "elfies",
            get_logs_dir(),
            get_model_validation_dir(),
            get_runtime_validation_dir(),
            get_runtime_locks_dir(),
        )
        missing = any(not path.exists() for path in expected_dirs)
        ensure_elfie_home()
        return DoctorRepairResult(
            ("Created missing ~/.elfienest data directories",) if missing else ()
        )

    def run_offline_validation(self) -> DoctorValidationResult:
        if self._offline_validator is None:
            return DoctorValidationResult(passed=False)
        return DoctorValidationResult(passed=self._offline_validator())


__all__ = ("LocalDoctorAdapter",)
