"""Atomic evaluation artifacts confined to the repository build tree."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping

from pydantic import BaseModel


class BrainEvalArtifactStore:
    """Write one run under ``build/brain-eval/<run_id>`` only."""

    def __init__(
        self,
        project_root: Path,
        run_id: str,
        *,
        output_root: Path | None = None,
    ) -> None:
        if not 1 <= len(run_id) <= 160 or not all(
            character.isalnum() or character in {"-", "_"} for character in run_id
        ):
            raise ValueError("run_id must contain 1-160 letters, digits, '-' or '_'")
        project = project_root.resolve()
        allowed = (project / "build" / "brain-eval").resolve()
        selected = (output_root or allowed).resolve()
        if selected != allowed and allowed not in selected.parents:
            raise ValueError(
                "Brain evaluation artifacts must stay under build/brain-eval"
            )
        self.run_dir = selected / run_id
        try:
            self.run_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError as error:
            raise ValueError(
                f"evaluation run already exists: {self.run_dir}"
            ) from error

    def write_json(self, name: str, payload: Any) -> Path:
        destination = self._destination(name)
        self._atomic_write(
            destination,
            json.dumps(
                _json_value(payload),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
        return destination

    def write_jsonl(self, name: str, payloads: Iterable[Any]) -> Path:
        destination = self._destination(name)
        content = "".join(
            json.dumps(_json_value(payload), ensure_ascii=False, sort_keys=True) + "\n"
            for payload in payloads
        )
        self._atomic_write(destination, content)
        return destination

    def _destination(self, name: str) -> Path:
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("artifact name must be a safe relative path")
        destination = (self.run_dir / relative).resolve()
        if destination != self.run_dir and self.run_dir not in destination.parents:
            raise ValueError("artifact path escaped the run directory")
        destination.parent.mkdir(parents=True, exist_ok=True)
        return destination

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=str(path.parent),
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError as error:
                raise ValueError(
                    f"evaluation artifact already exists: {path}"
                ) from error
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def load_jsonl(path: Path, model: type[BaseModel]) -> tuple[BaseModel, ...]:
    """Load strict versioned contracts from a JSONL artifact."""

    result = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                result.append(model.model_validate_json(line))
            except ValueError as error:
                raise ValueError(
                    f"invalid JSONL at {path}:{line_number}: {error}"
                ) from error
    return tuple(result)


def _json_value(payload: Any) -> Any:
    if isinstance(payload, BaseModel):
        return payload.model_dump(mode="json")
    if isinstance(payload, Mapping):
        return dict(payload)
    return payload


__all__ = ("BrainEvalArtifactStore", "load_jsonl")
