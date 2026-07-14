"""粮食目录的本地版本化存储。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from runtime.food.models import FoodRecipe
from runtime.storage.config_store import read_yaml_mapping, write_yaml_mapping
from runtime.storage.data_home import get_food_catalog_path, get_food_history_dir


@dataclass(frozen=True)
class FoodCatalog:
    version: int = 1
    source_fingerprint: str = ""
    generated_at: str = ""
    generation_sources: tuple[str, ...] = ()
    generation_note: str = ""
    recipes: Mapping[str, FoodRecipe] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "source_fingerprint": self.source_fingerprint,
            "generated_at": self.generated_at,
            "generation_sources": list(self.generation_sources),
            "generation_note": self.generation_note,
            "foods": {key: recipe.to_dict() for key, recipe in self.recipes.items()},
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> FoodCatalog:
        raw_foods = data.get("foods", {})
        foods = raw_foods if isinstance(raw_foods, Mapping) else {}
        return cls(
            version=int(data.get("version", 1)),
            source_fingerprint=str(data.get("source_fingerprint", "")),
            generated_at=str(data.get("generated_at", "")),
            generation_sources=tuple(
                str(item) for item in data.get("generation_sources", ()) if str(item)
            ),
            generation_note=str(data.get("generation_note", "")),
            recipes={
                str(key): FoodRecipe.from_dict(str(key), value)
                for key, value in foods.items()
                if isinstance(value, Mapping)
            },
        )


class FoodCatalogStore:
    def __init__(
        self,
        path: Path | None = None,
        history_dir: Path | None = None,
    ) -> None:
        self.path = path or get_food_catalog_path()
        self.history_dir = history_dir or get_food_history_dir()

    def load(self) -> FoodCatalog:
        return FoodCatalog.from_dict(read_yaml_mapping(self.path))

    def save(self, catalog: FoodCatalog, *, keep_history: bool = True) -> None:
        if keep_history and self.path.exists():
            self._snapshot_current()
        payload = catalog.to_dict()
        if not payload["generated_at"]:
            payload["generated_at"] = datetime.now(timezone.utc).isoformat()
        write_yaml_mapping(self.path, payload)

    def has_update(self, source_fingerprint: str) -> bool:
        return self.load().source_fingerprint != source_fingerprint

    def history_versions(self) -> list[Path]:
        if not self.history_dir.exists():
            return []
        return sorted(self.history_dir.glob("foods-*.yaml"), reverse=True)

    def rollback_latest(self) -> FoodCatalog:
        versions = self.history_versions()
        if not versions:
            raise FileNotFoundError("没有可回滚的粮食历史版本")
        return self.restore_version(versions[0])

    def restore_version(self, path: Path) -> FoodCatalog:
        resolved = path.resolve()
        history_root = self.history_dir.resolve()
        if resolved.parent != history_root or resolved not in {
            item.resolve() for item in self.history_versions()
        }:
            raise ValueError("粮食历史版本路径无效")
        catalog = FoodCatalog.from_dict(read_yaml_mapping(resolved))
        self.save(catalog, keep_history=True)
        return catalog

    def _snapshot_current(self) -> Path:
        current = self.path.read_bytes()
        digest = hashlib.sha256(current).hexdigest()[:12]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        history_path = self.history_dir / f"foods-{stamp}-{digest}.yaml"
        self.history_dir.mkdir(parents=True, exist_ok=True)
        history_path.write_bytes(current)
        return history_path


def fingerprint_source(data: Mapping[str, Any]) -> str:
    serialized = json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
