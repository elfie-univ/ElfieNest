"""Local offline diagnostics implementing the lifecycle Doctor Port."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.orchestration.lifecycle import DoctorRepairResult, DoctorValidationResult
from app.orchestration.lifecycle.ports import LifecycleLocalDataPort


class LocalDoctorAdapter:
    def __init__(
        self,
        *,
        local_data: LifecycleLocalDataPort,
        offline_validator: Callable[[Path | None], bool] | None = None,
    ) -> None:
        self._local_data = local_data
        self._offline_validator = offline_validator

    def repair_local_state(self, elfie_home: Path | None = None) -> DoctorRepairResult:
        if elfie_home is None:
            home = self._local_data.home()
            logs_dir = self._local_data.logs_dir()
            model_validation_dir = self._local_data.model_validation_dir()
            runtime_validation_dir = self._local_data.runtime_validation_dir()
            runtime_locks_dir = self._local_data.runtime_locks_dir()
        else:
            paths = self._local_data.paths(elfie_home)
            home = paths.home
            logs_dir = paths.logs
            model_validation_dir = paths.model_validations
            runtime_validation_dir = paths.runtime_validations
            runtime_locks_dir = paths.runtime_locks
        expected_dirs = (
            home,
            home / "assets",
            home / "assets" / "users",
            home / "configs",
            home / "elfies",
            logs_dir,
            model_validation_dir,
            runtime_validation_dir,
            runtime_locks_dir,
        )
        missing = any(not path.exists() for path in expected_dirs)
        if elfie_home is None:
            self._local_data.ensure_home()
        else:
            for path in expected_dirs:
                path.mkdir(mode=0o700, parents=True, exist_ok=True)
        return DoctorRepairResult(
            ("Created missing ~/.elfienest data directories",) if missing else ()
        )

    def run_offline_validation(
        self, elfie_home: Path | None = None
    ) -> DoctorValidationResult:
        if self._offline_validator is None:
            return DoctorValidationResult(passed=False)
        return DoctorValidationResult(passed=self._offline_validator(elfie_home))


__all__ = ("LocalDoctorAdapter",)
