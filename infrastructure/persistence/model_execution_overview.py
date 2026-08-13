"""Durable storage for generated Runtime overview reports."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from infrastructure.persistence.layout.data_home import get_model_validation_dir


class ModelExecutionOverviewStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or get_model_validation_dir()
        self.current_path = self.directory / "runtime-overview-current.json"

    def load_current(self) -> dict[str, Any] | None:
        return self._read(self.current_path)

    def save(self, report: Mapping[str, Any]) -> Path:
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name != "nt":
            os.chmod(self.directory, 0o700)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        history_path = self.directory / f"runtime-overview-{stamp}.json"
        payload = json.dumps(dict(report), ensure_ascii=False, indent=2)
        self._atomic_write(history_path, payload)
        self._atomic_write(self.current_path, payload)
        return history_path

    def history(self) -> list[Path]:
        if not self.directory.exists():
            return []
        return sorted(
            (
                path
                for path in self.directory.glob("runtime-overview-*.json")
                if path.name != self.current_path.name
            ),
            reverse=True,
        )

    def load_path(self, path: Path) -> dict[str, Any] | None:
        return self._read(path)

    @staticmethod
    def _read(path: Path) -> dict[str, Any] | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _atomic_write(path: Path, payload: str) -> None:
        temp_path = path.with_name(f".{path.name}.tmp")
        temp_path.write_text(payload, encoding="utf-8")
        if os.name != "nt":
            os.chmod(temp_path, 0o600)
        temp_path.replace(path)


__all__ = ("ModelExecutionOverviewStore",)
