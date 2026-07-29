"""粮食目录的本地版本化存储。"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from ai_runtime.food.models import FoodRecipe
from ai_runtime.models.model_reference import ModelReferenceError, parse_model_reference
from ai_runtime.storage.config_store import read_yaml_mapping, write_yaml_mapping
from ai_runtime.storage.data_home import get_food_catalog_path, get_food_history_dir
from ai_runtime.storage.provider_connections import ProviderConnectionStore

FOOD_CATALOG_VERSION = 2


@dataclass(frozen=True)
class FoodCatalog:
    version: int = FOOD_CATALOG_VERSION
    default_food: str = ""
    fallback_food: str = ""
    source_fingerprint: str = ""
    generated_at: str = ""
    generation_sources: tuple[str, ...] = ()
    generation_note: str = ""
    recipes: Mapping[str, FoodRecipe] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "default_food": self.default_food,
            "fallback_food": self.fallback_food,
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
            default_food=str(data.get("default_food", "")),
            fallback_food=str(data.get("fallback_food", "")),
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
        raw = read_yaml_mapping(self.path)
        catalog = FoodCatalog.from_dict(raw)
        if raw and catalog.version < FOOD_CATALOG_VERSION:
            migrated = _migrate_legacy_model_references(catalog)
            if migrated is not None:
                backup = self.path.with_suffix(f"{self.path.suffix}.v1.bak")
                if not backup.exists():
                    shutil.copy2(self.path, backup)
                write_yaml_mapping(self.path, migrated.to_dict())
                return migrated
        return catalog

    def save(self, catalog: FoodCatalog, *, keep_history: bool = True) -> None:
        validate_food_catalog_model_references(catalog)
        validate_food_catalog_selections(catalog)
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


def validate_food_catalog_model_references(catalog: FoodCatalog) -> None:
    """Reject new food writes that leave provider selection implicit."""
    for recipe in catalog.recipes.values():
        profiles = [recipe.primary, recipe.deep, recipe.vision, recipe.verifier]
        profiles.extend(recipe.technical_fallbacks)
        for profile in profiles:
            if profile is None or not profile.model:
                continue
            try:
                parse_model_reference(profile.model)
            except ModelReferenceError as exc:
                raise ModelReferenceError(
                    f"粮食 '{recipe.key}' 的模型无效: {exc}"
                ) from exc


def validate_food_catalog_selections(catalog: FoodCatalog) -> None:
    for field_name, food_key in (
        ("default_food", catalog.default_food),
        ("fallback_food", catalog.fallback_food),
    ):
        if food_key and food_key not in catalog.recipes:
            raise ValueError(f"{field_name} 指向不存在的粮食套餐: {food_key}")


def foods_referencing_connection(
    catalog: FoodCatalog,
    connection_id: str,
) -> tuple[str, ...]:
    """Return food keys that still depend on a connection instance."""
    referenced: list[str] = []
    for recipe in catalog.recipes.values():
        profiles = [recipe.primary, recipe.deep, recipe.vision, recipe.verifier]
        profiles.extend(recipe.technical_fallbacks)
        for profile in profiles:
            if profile is None or not profile.model:
                continue
            try:
                reference = parse_model_reference(profile.model)
            except ModelReferenceError:
                continue
            if reference.connection_id == connection_id:
                referenced.append(recipe.key)
                break
    return tuple(sorted(set(referenced)))


def _migrate_legacy_model_references(
    catalog: FoodCatalog,
) -> FoodCatalog | None:
    document = ProviderConnectionStore().load()
    legacy_map = {
        connection.legacy_provider_id: connection.connection_id
        for connection in document.connections.values()
        if connection.legacy_provider_id
    }
    connection_ids = set(document.connections)
    changed = False
    recipes: dict[str, FoodRecipe] = {}
    for key, recipe in catalog.recipes.items():
        profiles = [
            recipe.primary,
            recipe.deep,
            recipe.vision,
            recipe.verifier,
            *recipe.technical_fallbacks,
        ]
        migrated_profiles = []
        for profile in profiles:
            if profile is None or not profile.model:
                migrated_profiles.append(profile)
                continue
            reference = parse_model_reference(profile.model)
            if reference.connection_id in connection_ids:
                migrated_profiles.append(profile)
                continue
            connection_id = legacy_map.get(reference.connection_id)
            if not connection_id:
                return None
            changed = True
            migrated_profiles.append(
                replace(
                    profile,
                    model=f"{connection_id}/{reference.model_id}",
                )
            )
        primary, deep, vision, verifier, *fallbacks = migrated_profiles
        assert primary is not None
        recipes[key] = replace(
            recipe,
            primary=primary,
            deep=deep,
            vision=vision,
            verifier=verifier,
            technical_fallbacks=tuple(
                profile for profile in fallbacks if profile is not None
            ),
        )
    if not changed and catalog.version == FOOD_CATALOG_VERSION:
        return catalog
    return replace(catalog, version=FOOD_CATALOG_VERSION, recipes=recipes)
