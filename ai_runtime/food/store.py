"""Versioned storage for stable food packages."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from ai_runtime.food.models import (
    FOOD_COMMON_ID,
    FOOD_EMERGENCY_ID,
    SYSTEM_FOOD_IDS,
    FoodPackage,
    system_food_packages,
)
from ai_runtime.models.model_reference import ModelReferenceError, parse_model_reference
from ai_runtime.storage.config_store import read_yaml_mapping, write_yaml_mapping
from ai_runtime.storage.data_home import get_food_catalog_path, get_food_history_dir
from ai_runtime.storage.provider_connections import ProviderConnectionStore

FOOD_CATALOG_VERSION = 1


@dataclass(frozen=True)
class FoodCatalog:
    version: int = FOOD_CATALOG_VERSION
    global_default_food_id: str = FOOD_COMMON_ID
    global_emergency_food_id: str = FOOD_EMERGENCY_ID
    packages: Mapping[str, FoodPackage] = field(default_factory=system_food_packages)

    @property
    def recipes(self) -> Mapping[str, FoodPackage]:
        return self.packages

    @property
    def default_food(self) -> str:
        return self.global_default_food_id

    @property
    def fallback_food(self) -> str:
        return self.global_emergency_food_id

    def ordered_packages(self) -> tuple[FoodPackage, ...]:
        ordered = [
            self.packages[food_id]
            for food_id in (FOOD_EMERGENCY_ID, FOOD_COMMON_ID)
            if food_id in self.packages
        ]
        ordered.extend(
            package
            for key, package in self.packages.items()
            if key not in SYSTEM_FOOD_IDS
        )
        return tuple(ordered)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "global_default_food_id": self.global_default_food_id,
            "global_emergency_food_id": self.global_emergency_food_id,
            "packages": {
                key: package.to_dict() for key, package in self.packages.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> FoodCatalog:
        raw_packages = data.get("packages")
        if not isinstance(raw_packages, Mapping):
            return cls()
        packages = {
            str(key): FoodPackage.from_dict(str(key), value)
            for key, value in raw_packages.items()
            if isinstance(value, Mapping)
        }
        for key, package in system_food_packages().items():
            packages.setdefault(key, package)
        return cls(
            version=FOOD_CATALOG_VERSION,
            global_default_food_id=FOOD_COMMON_ID,
            global_emergency_food_id=FOOD_EMERGENCY_ID,
            packages=packages,
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
        if not self.path.exists():
            catalog = FoodCatalog()
            self.save(catalog, keep_history=False)
            return catalog
        return FoodCatalog.from_dict(read_yaml_mapping(self.path))

    def save(self, catalog: FoodCatalog, *, keep_history: bool = True) -> None:
        validate_food_catalog_model_references(catalog)
        if keep_history and self.path.exists():
            self._snapshot_current()
        write_yaml_mapping(self.path, catalog.to_dict())

    def history_versions(self) -> list[Path]:
        if not self.history_dir.exists():
            return []
        return sorted(self.history_dir.glob("foods-*.yaml"), reverse=True)

    def rollback_latest(self) -> FoodCatalog:
        versions = self.history_versions()
        if not versions:
            raise FileNotFoundError("没有可回滚的粮食历史版本")
        catalog = FoodCatalog.from_dict(read_yaml_mapping(versions[0]))
        self.save(catalog)
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
    return hashlib.sha256(serialized.encode()).hexdigest()


def validate_food_catalog_model_references(catalog: FoodCatalog) -> None:
    connections = ProviderConnectionStore().load().connections
    for package in catalog.packages.values():
        for reference_value in package.model_references:
            try:
                reference = parse_model_reference(reference_value)
            except ModelReferenceError as exc:
                raise ModelReferenceError(
                    f"粮食 '{package.key}' 的模型无效: {exc}"
                ) from exc
            connection = connections.get(reference.connection_id)
            if connection is None or not connection.enabled or connection.archived:
                raise ModelReferenceError(f"粮食 '{package.key}' 引用了不可用连接")
            model = next(
                (
                    item
                    for item in connection.models
                    if item.endpoint_model_id == reference.model_id
                ),
                None,
            )
            if model is None or model.hidden or model.retired or not model.available:
                raise ModelReferenceError(f"粮食 '{package.key}' 引用了不可用模型")


def foods_referencing_connection(
    catalog: FoodCatalog,
    connection_id: str,
) -> tuple[str, ...]:
    return tuple(
        package.key
        for package in catalog.packages.values()
        if any(
            _connection_id(reference) == connection_id
            for reference in package.model_references
        )
    )


def foods_referencing_model(
    catalog: FoodCatalog,
    connection_id: str,
    model_id: str,
) -> tuple[str, ...]:
    target = f"{connection_id}/{model_id}"
    return tuple(
        package.key
        for package in catalog.packages.values()
        if target in package.model_references
    )


def _connection_id(reference: str) -> str:
    try:
        return parse_model_reference(reference).connection_id
    except ModelReferenceError:
        return ""
