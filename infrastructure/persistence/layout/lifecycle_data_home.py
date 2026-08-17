"""Data-root selection and durable receipt for the lifecycle workflow."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, Optional

from app.orchestration.lifecycle.ports import (
    DataHomeInspection,
    DataHomeRecoveryResult,
    DataHomeState,
)
from infrastructure.persistence.layout.data_home import (
    DataHomeSelectionError,
    ensure_elfie_home,
    get_elfie_home,
    get_logs_dir,
    get_model_validation_dir,
    get_runtime_locks_dir,
    get_runtime_validation_dir,
    resolve_elfie_home,
)
from infrastructure.persistence.layout.data_layout import ensure_final_root_layout
from infrastructure.persistence.nest_db.final_schema import create_final_nest_database
from infrastructure.persistence.nest_db.store import inspect_data_home, repair_data_home

_RECEIPT_NAME: Final = "selected-data-home"


class LifecycleDataHomeAdapter:
    def home(self) -> Path:
        return get_elfie_home()

    def ensure_home(self) -> None:
        ensure_elfie_home()

    def logs_dir(self) -> Path:
        return get_logs_dir()

    def model_validation_dir(self) -> Path:
        return get_model_validation_dir()

    def runtime_validation_dir(self) -> Path:
        return get_runtime_validation_dir()

    def runtime_locks_dir(self) -> Path:
        return get_runtime_locks_dir()

    def select(
        self,
        explicit_home: Optional[str],
        *,
        project_root: Path,
        runtime_mode: str,
        use_remembered: bool,
    ) -> Path:
        if explicit_home is not None:
            return self._resolve(explicit_home, project_root, runtime_mode)
        if os.environ.get("ELFIE_HOME"):
            return self._resolve(None, project_root, runtime_mode)
        if use_remembered:
            remembered = self._remembered(project_root, runtime_mode)
            if remembered is not None:
                return remembered
        return self._resolve(None, project_root, runtime_mode)

    def remember(
        self,
        selected_home: Path,
        *,
        project_root: Path,
        runtime_mode: str,
    ) -> None:
        receipt_path = self._receipt_path(project_root, runtime_mode)
        receipt_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name != "nt":
            os.chmod(receipt_path.parent.parent, 0o700)
            os.chmod(receipt_path.parent, 0o700)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{_RECEIPT_NAME}.",
            dir=str(receipt_path.parent),
        )
        temporary_path = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as receipt:
                receipt.write(str(selected_home.resolve(strict=False)))
                receipt.write("\n")
            temporary_path.replace(receipt_path)
        except OSError:
            temporary_path.unlink(missing_ok=True)
            raise

    def inspect(self, selected_home: Path) -> DataHomeInspection:
        return inspect_data_home(selected_home)

    def prepare(self, selected_home: Path) -> DataHomeInspection:
        return repair_data_home(selected_home)

    def recover(self, selected_home: Path) -> DataHomeRecoveryResult:
        inspection = self.inspect(selected_home)
        if inspection.state not in {DataHomeState.LEGACY, DataHomeState.CORRUPT}:
            raise OSError("只允许对旧版或损坏的数据目录执行备份后重建")
        home = inspection.home
        if not home.exists() or not home.is_dir() or home.is_symlink():
            raise OSError("数据目录不是可安全处理的真实目录")
        backup_parent = home.parent / f"{home.name}-backups"
        backup_parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name != "nt":
            os.chmod(backup_parent, 0o700)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        backup_home = backup_parent / f"{timestamp}-{inspection.state.value}"
        candidate = home.parent / f".{home.name}.recovery-{timestamp}"
        if backup_home.exists() or candidate.exists():
            raise OSError("恢复目录已存在，请稍后重试")
        try:
            ensure_final_root_layout(candidate)
            create_final_nest_database(candidate / "nest.db")
            home.rename(backup_home)
            try:
                candidate.rename(home)
            except OSError:
                backup_home.rename(home)
                raise
        except OSError:
            if candidate.exists():
                _remove_empty_candidate(candidate)
            raise
        return DataHomeRecoveryResult(home=home, backup_home=backup_home)

    def _remembered(self, project_root: Path, runtime_mode: str) -> Optional[Path]:
        try:
            selected = (
                self._receipt_path(project_root, runtime_mode)
                .read_text(encoding="utf-8")
                .strip()
            )
        except OSError:
            return None
        if not selected:
            return None
        try:
            return self._resolve(selected, project_root, runtime_mode)
        except DataHomeSelectionError:
            return None

    @staticmethod
    def _resolve(
        explicit_home: Optional[str], project_root: Path, runtime_mode: str
    ) -> Path:
        return resolve_elfie_home(
            explicit_home,
            invoking_cwd=project_root,
            runtime_mode=runtime_mode,
            source_root=project_root,
        )

    @staticmethod
    def _receipt_path(project_root: Path, runtime_mode: str) -> Path:
        receipt_home = resolve_elfie_home(
            None,
            invoking_cwd=project_root,
            runtime_mode=runtime_mode,
            source_root=project_root,
            env={},
        )
        return receipt_home / "runtime" / _RECEIPT_NAME


__all__ = ("LifecycleDataHomeAdapter",)


def _remove_empty_candidate(candidate: Path) -> None:
    """Remove only the private candidate created by a failed recovery."""
    for path in sorted(candidate.rglob("*"), reverse=True):
        if path.is_file() or path.is_symlink():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            path.rmdir()
    candidate.rmdir()
