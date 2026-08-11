"""Technical catalog and local-model inventory used by the legacy CLI surface."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from infrastructure.models.catalog import BUILTIN_MODEL_CATALOG

_COST_LABELS = {0: "免费", 1: "极低", 2: "低", 3: "中", 4: "高"}


@dataclass(frozen=True)
class _CatalogModel:
    model_id: str
    capabilities_text: str
    cost_text: str
    provider_id: str


@dataclass(frozen=True)
class _LocalModel:
    name: str
    size_bytes: int
    modified_at: str


@dataclass(frozen=True)
class _LocalModelScan:
    status: str
    error: str | None
    models: tuple[_LocalModel, ...]


class CliModelCatalogAdapter:
    def list_models(self) -> tuple[_CatalogModel, ...]:
        return tuple(
            _CatalogModel(
                model_id=model.model_id,
                capabilities_text=", ".join(model.capabilities[:3])
                + ("..." if len(model.capabilities) > 3 else ""),
                cost_text=_COST_LABELS.get(model.cost_tier, "未知"),
                provider_id=model.provider,
            )
            for model in BUILTIN_MODEL_CATALOG.values()
            if model.visible
        )

    def scan_local_models(self) -> _LocalModelScan:
        try:
            response = urllib.request.urlopen(
                "http://localhost:11434/api/tags",
                timeout=5.0,
            )
            payload = json.loads(response.read().decode())
        except urllib.error.URLError:
            return _LocalModelScan("not_running", None, ())
        except (OSError, TimeoutError, json.JSONDecodeError) as error:
            return _LocalModelScan("failed", str(error), ())

        raw_models = payload.get("models", [])
        if not isinstance(raw_models, list):
            return _LocalModelScan("failed", "invalid Ollama model response", ())
        models = tuple(
            _LocalModel(
                name=str(item.get("name", "")),
                size_bytes=int(item.get("size", 0)),
                modified_at=str(item.get("modified_at", "")),
            )
            for item in raw_models
            if isinstance(item, dict)
        )
        return _LocalModelScan("available", None, models)


__all__ = ("CliModelCatalogAdapter",)
