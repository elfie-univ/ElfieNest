"""File adapter for model token usage batches."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from pydantic import JsonValue


class FileTokenUsageWriter:
    def __init__(self, path: Path) -> None:
        self.path = path

    def write(self, record: Mapping[str, JsonValue]) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(record), ensure_ascii=False) + "\n")


__all__ = ("FileTokenUsageWriter",)
