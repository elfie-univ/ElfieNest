"""Local offline diagnostics implementing the lifecycle Doctor Port."""

from __future__ import annotations

from collections.abc import Callable

from app.orchestration.lifecycle import DoctorRepairResult, DoctorValidationResult
from app.orchestration.lifecycle.ports import LifecycleLocalDataPort


class LocalDoctorAdapter:
    def __init__(
        self,
        *,
        local_data: LifecycleLocalDataPort,
        offline_validator: Callable[[], bool] | None = None,
    ) -> None:
        self._local_data = local_data
        self._offline_validator = offline_validator

    def repair_local_state(self) -> DoctorRepairResult:
        home = self._local_data.home()
        expected_dirs = (
            home,
            home / "assets",
            home / "assets" / "users",
            home / "configs",
            home / "elfies",
            self._local_data.logs_dir(),
            self._local_data.model_validation_dir(),
            self._local_data.runtime_validation_dir(),
            self._local_data.runtime_locks_dir(),
        )
        missing = any(not path.exists() for path in expected_dirs)
        self._local_data.ensure_home()
        return DoctorRepairResult(
            ("Created missing ~/.elfienest data directories",) if missing else ()
        )

    def run_offline_validation(self) -> DoctorValidationResult:
        if self._offline_validator is None:
            return DoctorValidationResult(passed=False)
        return DoctorValidationResult(passed=self._offline_validator())


__all__ = ("LocalDoctorAdapter",)
