"""Restore Setup model artifacts when their database milestone rejects."""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from ai_runtime.food.evidence import ModelEvidenceStore
from ai_runtime.food.store import FoodCatalogStore


@dataclass(frozen=True)
class _FileState:
    path: Path
    contents: bytes | None
    mode: int

    @classmethod
    def capture(cls, path: Path) -> _FileState:
        if not path.exists():
            return cls(path=path, contents=None, mode=0o600)
        return cls(
            path=path,
            contents=path.read_bytes(),
            mode=path.stat().st_mode & 0o777,
        )

    def restore(self) -> None:
        if self.contents is None:
            self.path.unlink(missing_ok=True)
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.rollback")
        try:
            temporary.write_bytes(self.contents)
            os.chmod(temporary, self.mode)
            temporary.replace(self.path)
        except OSError:
            temporary.unlink(missing_ok=True)
            raise


@contextmanager
def rollback_artifacts(
    evidence_store: ModelEvidenceStore,
    catalog_store: FoodCatalogStore,
) -> Iterator[None]:
    """Compensate catalog, evidence, and new history files on any failure."""
    states = (
        _FileState.capture(evidence_store.path),
        _FileState.capture(catalog_store.path),
    )
    history_existed = catalog_store.history_dir.exists()
    history_before = set(catalog_store.history_versions())
    try:
        yield
    except Exception:
        for state in states:
            state.restore()
        for path in set(catalog_store.history_versions()) - history_before:
            path.unlink(missing_ok=True)
        if not history_existed and catalog_store.history_dir.exists():
            catalog_store.history_dir.rmdir()
        raise
