"""Data-root selection and durable receipt for the lifecycle workflow."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Final, Optional

from infrastructure.persistence.layout.data_home import (
    DataHomeSelectionError,
    resolve_elfie_home,
)

_RECEIPT_NAME: Final = "selected-data-home"


class LifecycleDataHomeAdapter:
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
