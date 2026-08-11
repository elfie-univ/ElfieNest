"""Versioned storage for stable food packages."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from ai_runtime.food.models import (
    FOOD_COMMON_ID,
    FOOD_EMERGENCY_ID,
    SYSTEM_FOOD_IDS,
    FoodPackage,
    system_food_packages,
)
from infrastructure.models.model_reference import (
    ModelReferenceError,
    parse_model_reference,
)
from infrastructure.persistence.provider_connections import ProviderConnectionStore

FOOD_CATALOG_VERSION = 1


class FoodCatalogRepository(Protocol):
    """Narrow food catalog contract shared by runtime and persistence roots."""

    def load(self) -> FoodCatalog:
        """Load the complete food catalog projection."""

    def list(self) -> tuple[FoodPackage, ...]:
        """List food packages in stable display order."""

    def get(self, food_key: str) -> FoodPackage | None:
        """Return one package by key, or ``None`` when absent."""

    def create(self, package: FoodPackage) -> FoodPackage:
        """Persist one complete package."""

    def update(self, package: FoodPackage) -> FoodPackage:
        """Replace one complete package atomically."""

    def delete(self, food_key: str) -> None:
        """Delete one package after repository guards pass."""


@dataclass(frozen=True)
class FoodCatalog:
    version: int = FOOD_CATALOG_VERSION
    global_default_food_id: str = FOOD_COMMON_ID
    global_emergency_food_id: str = FOOD_EMERGENCY_ID
    packages: Mapping[str, FoodPackage] = field(default_factory=system_food_packages)

    @property
    def recipes(self) -> Mapping[str, FoodPackage]:
        return self.packages

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
