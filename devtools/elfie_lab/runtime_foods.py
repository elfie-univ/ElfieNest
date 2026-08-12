"""Elfie Lab 的隔离模型连接与测试粮食支持。"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, Mapping

from app.features.configuration.food import StoredFoodPackage, StoredModelEvidence
from elfie.brain.reasoning.food_port import FoodCatalog, FoodPort
from infrastructure.models.provider_records import ProviderModelRecord
from infrastructure.models.providers.ollama import OllamaManager
from infrastructure.models.providers.profiles import get_product
from infrastructure.models.runtime_config import LLMRuntimeConfig
from infrastructure.persistence.configuration.secrets import (
    connection_secret_name,
    provider_secret_name,
    read_secrets,
    resolve_secret,
)
from infrastructure.persistence.food import SQLiteFoodAdapter
from infrastructure.persistence.layout.data_home import get_elfie_developer_home
from infrastructure.persistence.layout.data_layout import final_root_layout
from infrastructure.persistence.nest_db.store import init_db
from infrastructure.persistence.provider_connections import ProviderConnectionStore
from infrastructure.persistence.provider_storage import ProviderStorageAdapter


class _ElfieLabRuntimeConfigSource:
    """Build the Runtime projection from one Elfie Lab data root."""

    def __init__(self, root: Path) -> None:
        self._layout = final_root_layout(root)

    def load_env(self, config_home: Path | None) -> Mapping[str, str]:
        _ = config_home
        return read_secrets(self._layout.auth_env)

    def load_settings(self, config_home: Path | None) -> Mapping[str, Any]:
        _ = config_home
        return {}

    def load_connections(self) -> Mapping[str, Mapping[str, Any]]:
        document = ProviderConnectionStore(self._layout.providers_config).load()
        providers: Dict[str, Mapping[str, Any]] = {}
        for connection_id, connection in document.connections.items():
            if not connection.enabled or connection.archived:
                continue
            profile = get_product(connection.catalog_id)
            if profile is None:
                continue
            secret_name = connection.credential_ref or connection_secret_name(
                connection_id
            )
            providers[connection_id] = {
                "catalog_id": connection.catalog_id,
                "display_name": connection.alias,
                "api_base": connection.api_base or profile.api_base,
                "api_mode": connection.api_mode or profile.api_mode,
                "auth_type": connection.auth_type or profile.auth_type,
                "api_key_env": secret_name,
                "api_key": resolve_secret(secret_name, self._layout.auth_env),
                "models": [
                    {
                        "id": model.endpoint_model_id,
                        "display_name": model.display_name,
                    }
                    for model in connection.models
                    if not model.hidden and not model.retired and model.available
                ],
            }
        return providers

    def resolve_secret(self, name: str, config_home: Path | None) -> str:
        _ = config_home
        return resolve_secret(name, self._layout.auth_env)

    def provider_secret_name(self, provider_id: str) -> str:
        return provider_secret_name(provider_id)


class ElfieLabRuntime:
    """Own the small, isolated configuration surface used by Elfie Lab."""

    test_food_id = "elfie_lab_test"
    test_food_name = "Elfie Lab 测试粮"

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.layout = final_root_layout(self.root)
        self.ensure()

    def ensure(self) -> None:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        init_db(str(self.layout.nest_database))

    @property
    def config_path(self) -> Path:
        return self.layout.runtime_config

    @property
    def env_path(self) -> Path:
        return self.layout.auth_env

    @property
    def providers_path(self) -> Path:
        return self.layout.providers_config

    @property
    def database_path(self) -> Path:
        return self.layout.nest_database

    def config_paths(self) -> tuple[Path, ...]:
        return (self.config_path, self.providers_path, self.env_path)

    def food_store(self) -> SQLiteFoodAdapter:
        return SQLiteFoodAdapter(self.database_path)

    def load_runtime_config(self) -> LLMRuntimeConfig:
        return LLMRuntimeConfig(
            config_home=str(self.root),
            source=_ElfieLabRuntimeConfigSource(self.root),
        )

    def resolve_secret(self, name: str) -> str:
        return resolve_secret(name, self.env_path)

    def load_food_catalog(self, food_store: FoodPort | None = None) -> FoodCatalog:
        return (food_store or self.food_store()).load()

    def local_models(self) -> tuple[str, ...]:
        try:
            return tuple(
                OllamaManager(self.load_runtime_config()).list_installed_models()
            )
        except Exception:
            return ()

    def configure(
        self,
        *,
        mode: str,
        model: str,
        api_base: str = "",
        api_key: str = "",
        alias: str = "",
    ) -> str:
        normalized_model = model.strip()
        if not normalized_model:
            raise ValueError("模型名称不能为空")
        if mode == "local":
            if api_key.strip():
                raise ValueError("本地模型不需要 Token")
            connection_id = self._save_connection(
                catalog_id="ollama",
                api_base=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
                api_mode="ollama",
                auth_type="none",
                model=normalized_model,
                api_key=None,
                alias=alias,
            )
        elif mode == "openai":
            if not api_base.strip():
                raise ValueError("OpenAI 兼容服务必须填写 URL")
            if not api_key.strip():
                raise ValueError("OpenAI 兼容服务必须填写 Token")
            connection_id = self._save_connection(
                catalog_id="custom_openai",
                api_base=api_base.strip().rstrip("/"),
                api_mode="chat_completions",
                auth_type="bearer",
                model=normalized_model,
                api_key=api_key.strip(),
                alias=alias,
            )
        else:
            raise ValueError("不支持的模型连接类型")

        reference = f"{connection_id}/{normalized_model}"
        food_store = self.food_store()
        package = StoredFoodPackage(
            food_id=self.test_food_id,
            display_name=self.test_food_name,
            primary_model=reference,
            enabled=True,
        )
        existing = food_store.get_package(self.test_food_id)
        if existing is None:
            food_store.create_package(package)
        else:
            food_store.update_package(package)
        return self.test_food_id

    def model_evidence(self) -> dict[str, StoredModelEvidence]:
        """Expose configured models as attemptable, not validated, evidence."""
        document = ProviderConnectionStore(self.providers_path).load()
        result: dict[str, StoredModelEvidence] = {}
        for connection in document.connections.values():
            if not connection.enabled or connection.archived:
                continue
            profile = get_product(connection.catalog_id)
            local = bool(profile and profile.connection_method == "local")
            for model in connection.models:
                reference = f"{connection.connection_id}/{model.endpoint_model_id}"
                result[reference] = StoredModelEvidence(
                    reference=reference,
                    display_name=model.display_name,
                    capabilities=frozenset(),
                    verified=False,
                    local=local,
                    status="never_verified",
                    fresh=True,
                )
        return result

    def status(self) -> dict[str, Any]:
        catalog = self.load_food_catalog()
        configured = any(
            package.system_role is None
            and package.enabled
            and not package.archived
            and package.primary is not None
            for package in catalog.packages.values()
        )
        return {
            "scope": "developer",
            "root": str(self.root),
            "configured": configured,
        }

    def _save_connection(
        self,
        *,
        catalog_id: str,
        api_base: str,
        api_mode: str,
        auth_type: str,
        model: str,
        api_key: str | None,
        alias: str,
    ) -> str:
        store = ProviderConnectionStore(self.providers_path)
        storage = ProviderStorageAdapter(store, secret_path=self.env_path)
        existing = next(
            (
                item
                for item in store.load().connections.values()
                if item.catalog_id == catalog_id
            ),
            None,
        )
        model_record = ProviderModelRecord(
            endpoint_model_id=model,
            display_name=model,
            source="manual",
        )
        display_alias = alias.strip() or "Elfie Lab"
        if existing is None:
            connection = store.create(
                catalog_id=catalog_id,
                alias=display_alias,
                api_base=api_base,
                api_mode=api_mode,
                auth_type=auth_type,
                models=(model_record,),
            )
            saved = storage.create_with_secret(connection, api_key)
            return saved.connection_id
        updated = replace(
            existing,
            alias=display_alias,
            api_base=api_base,
            api_mode=api_mode,
            auth_type=auth_type,
            models=(model_record,),
            enabled=True,
            archived=False,
        )
        saved = storage.replace_with_secret(updated, api_key)
        return saved.connection_id


def runtime_food_catalog_store(runtime: ElfieLabRuntime) -> FoodPort:
    """Return the Food Port for the Lab-isolated database."""
    runtime.ensure()
    return runtime.food_store()


def load_runtime_food_catalog(
    runtime: ElfieLabRuntime,
    food_store: FoodPort | None = None,
) -> FoodCatalog:
    """Load the Food projection consumed by the Lab Runtime."""
    return runtime.load_food_catalog(food_store)


def default_runtime_config_dir() -> str:
    """Return the isolated Elfie Lab data root."""
    return str(get_elfie_developer_home() / "elfie_lab")


__all__ = (
    "ElfieLabRuntime",
    "default_runtime_config_dir",
    "load_runtime_food_catalog",
    "runtime_food_catalog_store",
)
