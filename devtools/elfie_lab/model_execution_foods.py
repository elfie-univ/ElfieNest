"""Elfie Lab 的隔离模型连接与测试粮食支持。"""

from __future__ import annotations

import secrets
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, Literal, Mapping, Sequence

from app.features.configuration.food import (
    FoodPortConflict,
    FoodPortError,
    FoodPortNotFound,
    StoredFoodPackage,
    StoredModelEvidence,
)
from devtools.elfie_lab.model_subscriptions import subscription_by_id
from elfie.brain.reasoning.food_port import FoodCatalog, FoodPort
from infrastructure.models.model_execution_config import ModelExecutionConfig
from infrastructure.models.model_reference import parse_model_reference
from infrastructure.models.ollama.ollama_platform import (
    DEFAULT_OLLAMA_ENDPOINT,
    OllamaBinding,
    OllamaPlatformAdapter,
    is_safe_local_endpoint,
)
from infrastructure.models.provider_records import ProviderModelRecord
from infrastructure.models.providers.dispatch import (
    call_ollama_api,
    call_openai_compatible_api,
)
from infrastructure.models.providers.profiles import get_product
from infrastructure.persistence.configuration.bundled_defaults import (
    load_system_defaults,
)
from infrastructure.persistence.configuration.secrets import (
    connection_secret_name,
    provider_secret_name,
    read_secrets,
    resolve_secret,
)
from infrastructure.persistence.food import SQLiteFoodAdapter
from infrastructure.persistence.layout.data_home import get_elfie_developer_home
from infrastructure.persistence.layout.data_layout import final_root_layout
from infrastructure.persistence.model_catalog import load_model_identities
from infrastructure.persistence.nest_db.store import init_db
from infrastructure.persistence.provider_catalog import load_provider_catalog
from infrastructure.persistence.provider_connections import ProviderConnectionStore
from infrastructure.persistence.provider_storage import ProviderStorageAdapter


class _ElfieLabModelEnvironmentConfigSource:
    """Build the Runtime projection from one Elfie Lab data root."""

    def __init__(self, root: Path, catalog) -> None:
        self._layout = final_root_layout(root)
        self._catalog = catalog

    def load_env(self, config_home: Path | None) -> Mapping[str, str]:
        _ = config_home
        return read_secrets(self._layout.auth_env)

    def load_settings(self, config_home: Path | None) -> Mapping[str, Any]:
        _ = config_home
        document = ProviderConnectionStore(self._layout.providers_config).load()
        return {
            "providers": {
                connection_id: {"status": "active"}
                for connection_id, connection in document.connections.items()
                if connection.enabled
                and not connection.archived
                and get_product(connection.catalog_id, catalog=self._catalog)
                is not None
            }
        }

    def load_connections(self) -> Mapping[str, Mapping[str, Any]]:
        document = ProviderConnectionStore(self._layout.providers_config).load()
        providers: Dict[str, Mapping[str, Any]] = {}
        for connection_id, connection in document.connections.items():
            if not connection.enabled or connection.archived:
                continue
            profile = get_product(connection.catalog_id, catalog=self._catalog)
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


FoodConnectionType = Literal["ollama", "openai"]


def food_connection_type(*, catalog_id: str, api_mode: str) -> FoodConnectionType:
    """Project persisted provider fields to the two Lab setup choices."""
    return "ollama" if catalog_id == "ollama" or api_mode == "ollama" else "openai"


def validate_food_connection(
    *,
    api_mode: str,
    api_base: str,
    api_key: str,
    primary_model: str,
) -> None:
    """Run one bounded native-Ollama or OpenAI-compatible smoke request."""
    try:
        messages = [{"role": "user", "content": "Reply with OK."}]
        if api_mode == "ollama":
            response = call_ollama_api(
                api_base,
                primary_model,
                messages,
                0.0,
                8,
                timeout_seconds=20.0,
            )[0]
        else:
            response = call_openai_compatible_api(
                api_base,
                api_key,
                primary_model,
                messages,
                0.0,
                8,
                provider="Elfie Lab",
                timeout_seconds=20.0,
            )[0]
    except Exception as error:
        detail = str(error).strip() or type(error).__name__
        raise ValueError(f"模型连接验证失败：{detail}") from error
    if not response.strip():
        raise ValueError("模型连接验证失败：主模型返回空响应")


class ElfieLabModelEnvironment:
    """Own the small, isolated configuration surface used by Elfie Lab."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.layout = final_root_layout(self.root)
        self.provider_catalog = load_provider_catalog()
        self.identity_catalog = load_model_identities()
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

    def load_model_execution_config(self) -> ModelExecutionConfig:
        return ModelExecutionConfig(
            config_home=str(self.root),
            source=_ElfieLabModelEnvironmentConfigSource(
                self.root, self.provider_catalog
            ),
            provider_catalog=self.provider_catalog,
            system_defaults=load_system_defaults(),
        )

    def resolve_secret(self, name: str) -> str:
        return resolve_secret(name, self.env_path)

    def load_food_catalog(self, food_store: FoodPort | None = None) -> FoodCatalog:
        return (food_store or self.food_store()).load()

    def _connection_store(self) -> ProviderConnectionStore:
        return ProviderConnectionStore(self.providers_path)

    def _connection_and_adapter(
        self,
    ) -> tuple[ProviderConnectionStore, ProviderStorageAdapter]:
        store = self._connection_store()
        return store, ProviderStorageAdapter(store, secret_path=self.env_path)

    def _normalize_models(self, models: Sequence[str]) -> tuple[str, ...]:
        normalized = tuple(
            dict.fromkeys(
                model.strip()
                for model in models
                if isinstance(model, str) and model.strip()
            )
        )
        if not normalized:
            raise ValueError("粮食配置至少要包含一个模型")
        return normalized

    def probe_ollama(self, *, api_base: str | None = None) -> dict[str, str]:
        """Probe one explicit loopback Ollama endpoint without scanning ports."""
        endpoint = (api_base or DEFAULT_OLLAMA_ENDPOINT).strip().rstrip("/")
        if not is_safe_local_endpoint(endpoint):
            raise ValueError("Ollama endpoint 必须是本机回环地址并包含端口")

        adapter = OllamaPlatformAdapter()
        probe = adapter.probe(
            OllamaBinding(
                api_base=endpoint,
                platform=adapter.platform,
                install_kind="external",
                launch_target="",
                version="",
            )
        )
        healthy = probe.state == "healthy"
        return {
            "state": "healthy" if healthy else "unavailable",
            "endpoint": endpoint,
            "version": probe.version or "",
            "message": (
                "已连接本机 Ollama"
                if healthy
                else "未检测到本机 Ollama，请确认服务已启动"
            ),
        }

    def configure_food(
        self,
        *,
        display_name: str,
        food_id: str | None,
        subscription_id: str | None = None,
        subscription_name: str | None = None,
        connection_type: FoodConnectionType,
        api_base: str | None,
        api_key: str | None,
        models: Sequence[str],
        primary_model: str,
        reasoning_model: str,
        vision_model: str,
        tool_model: str,
        fallback_model: str,
    ) -> str:
        """Create/update a Food package, optionally reusing a shared subscription."""
        normalized_name = display_name.strip()
        if not normalized_name:
            raise ValueError("粮食名称不能为空")

        normalized_models = self._normalize_models(models)
        store, storage = self._connection_and_adapter()
        food_store = self.food_store()

        requested_food_id = food_id.strip() if food_id and food_id.strip() else ""
        existing_package = (
            food_store.get_package(requested_food_id) if requested_food_id else None
        )
        if requested_food_id and existing_package is None:
            raise ValueError("系统不存在该粮食")

        if existing_package is not None:
            if existing_package.system_role is not None:
                raise ValueError("系统粮食不能在 Elfie Lab 中编辑")
            if existing_package.archived:
                raise ValueError("归档粮食不能编辑")

            if api_base not in (None, ""):
                raise ValueError("编辑粮食不能修改 API URL")
            if api_key not in (None, ""):
                raise ValueError("编辑粮食不能修改 API Key")

            if existing_package.primary_model is None:
                raise ValueError("系统数据异常：该粮食主模型缺失")
            try:
                connection_id = parse_model_reference(
                    existing_package.primary_model
                ).connection_id
            except ValueError as error:
                raise ValueError("系统数据异常：粮食绑定的模型引用格式错误") from error

            requested_subscription_id = (
                subscription_id.strip() if subscription_id else ""
            )
            if requested_subscription_id and requested_subscription_id != connection_id:
                raise ValueError("编辑粮食不能更换模型订阅")

            document = store.load()
            connection = document.connections.get(connection_id)
            if connection is None:
                raise ValueError("系统数据异常：粮食绑定的连接已丢失")
            saved_connection_type = food_connection_type(
                catalog_id=connection.catalog_id,
                api_mode=connection.api_mode,
            )
            if connection_type != saved_connection_type:
                raise ValueError("编辑粮食不能修改连接方式")

            effective_primary = primary_model.strip()
            effective_reasoning = reasoning_model.strip()
            effective_vision = vision_model.strip()
            effective_tool = tool_model.strip()
            effective_fallback = fallback_model.strip()

            if not effective_primary:
                raise ValueError("主模型不能为空")
            if effective_primary not in normalized_models:
                raise ValueError("主模型必须来自“模型列表”")

            for role_name, model_name in (
                ("reasoning_model", effective_reasoning),
                ("vision_model", effective_vision),
                ("tool_model", effective_tool),
                ("fallback_model", effective_fallback),
            ):
                if model_name and model_name not in normalized_models:
                    raise ValueError(f"{role_name}必须来自“模型列表”")

            secret_name = connection.credential_ref or connection_secret_name(
                connection_id
            )
            saved_api_key = storage.resolve_secret(secret_name)
            saved_api_base = (connection.api_base or "").strip().rstrip("/")
            if not saved_api_base and saved_connection_type == "ollama":
                saved_api_base = DEFAULT_OLLAMA_ENDPOINT
            if not saved_api_base:
                raise ValueError("系统数据异常：粮食绑定的 API URL 缺失")
            validate_food_connection(
                api_mode=(
                    "ollama"
                    if saved_connection_type == "ollama"
                    else "chat_completions"
                ),
                api_base=saved_api_base,
                api_key=saved_api_key,
                primary_model=effective_primary,
            )

            storage.replace_with_secret(
                replace(
                    connection,
                    models=tuple(
                        ProviderModelRecord(
                            endpoint_model_id=model,
                            display_name=model,
                            source="manual",
                        )
                        for model in normalized_models
                    ),
                ),
                api_key=None,
            )

            food_store.update_package(
                StoredFoodPackage(
                    food_id=existing_package.food_id,
                    display_name=normalized_name,
                    system_role=existing_package.system_role,
                    enabled=True,
                    archived=False,
                    primary_model=f"{connection_id}/{effective_primary}",
                    reasoning_model=(
                        f"{connection_id}/{effective_reasoning}"
                        if effective_reasoning
                        else None
                    ),
                    vision_model=(
                        f"{connection_id}/{effective_vision}"
                        if effective_vision
                        else None
                    ),
                    tool_model=(
                        f"{connection_id}/{effective_tool}" if effective_tool else None
                    ),
                    fallback_model=(
                        f"{connection_id}/{effective_fallback}"
                        if effective_fallback
                        else None
                    ),
                    visibility_mode=existing_package.visibility_mode,
                    visible_user_ids=existing_package.visible_user_ids,
                    required_roles=existing_package.required_roles,
                )
            )
            return existing_package.food_id

        requested_subscription_id = subscription_id.strip() if subscription_id else ""

        # 自定义接口需要明确 URL；已选共享订阅直接复用其地址。
        if (
            not requested_subscription_id
            and connection_type == "openai"
            and (api_base is None or not api_base.strip())
        ):
            raise ValueError("新建粮食必须填写 API URL")

        normalized_primary = primary_model.strip()
        if not normalized_primary:
            raise ValueError("主模型不能为空")
        if normalized_primary not in normalized_models:
            raise ValueError("主模型必须来自“模型列表”")

        for role_name, model_name in (
            ("reasoning_model", reasoning_model.strip()),
            ("vision_model", vision_model.strip()),
            ("tool_model", tool_model.strip()),
            ("fallback_model", fallback_model.strip()),
        ):
            if model_name and model_name not in normalized_models:
                raise ValueError(f"{role_name}必须来自“模型列表”")

        connection_id = requested_subscription_id
        created_connection_id: str | None = None

        if requested_subscription_id:
            connection = subscription_by_id(self.root, requested_subscription_id)
            if connection is None:
                raise ValueError("选择的模型订阅不存在或已删除")
            saved_connection_type = food_connection_type(
                catalog_id=connection.catalog_id,
                api_mode=connection.api_mode,
            )
            if saved_connection_type != connection_type:
                raise ValueError("模型订阅连接方式与当前选择不一致")
            normalized_models = tuple(
                model.endpoint_model_id
                for model in connection.models
                if not model.hidden and not model.retired and model.available
            )
            if not normalized_models:
                raise ValueError("选择的模型订阅没有可用模型")
            normalized_api_base = (connection.api_base or "").strip().rstrip("/")
            if not normalized_api_base and connection_type == "ollama":
                normalized_api_base = DEFAULT_OLLAMA_ENDPOINT
            secret_name = connection.credential_ref or connection_secret_name(
                connection_id
            )
            normalized_api_key = storage.resolve_secret(secret_name)
            validate_food_connection(
                api_mode="ollama"
                if connection_type == "ollama"
                else "chat_completions",
                api_base=normalized_api_base,
                api_key=normalized_api_key,
                primary_model=normalized_primary,
            )
        else:
            normalized_api_base = (
                (api_base or DEFAULT_OLLAMA_ENDPOINT).strip().rstrip("/")
            )
            normalized_api_key = (api_key or "").strip()
        if connection_type == "ollama":
            if normalized_api_key:
                raise ValueError("本机 Ollama 不需要 API Key")
            if not is_safe_local_endpoint(normalized_api_base):
                raise ValueError("Ollama endpoint 必须是本机回环地址并包含端口")

        api_mode = "ollama" if connection_type == "ollama" else "chat_completions"
        if not requested_subscription_id:
            validate_food_connection(
                api_mode=api_mode,
                api_base=normalized_api_base,
                api_key=normalized_api_key,
                primary_model=normalized_primary,
            )
            connection_id = self._save_connection(
                catalog_id="ollama" if connection_type == "ollama" else "custom_openai",
                api_base=normalized_api_base,
                api_mode=api_mode,
                auth_type=(
                    "none"
                    if connection_type == "ollama" or not normalized_api_key
                    else "bearer"
                ),
                models=normalized_models,
                api_key=normalized_api_key or None,
                alias=subscription_name or normalized_name,
            )
            created_connection_id = connection_id

        selected_food_id = f"elfie_lab_food_{secrets.token_hex(4)}"
        try:
            food_store.create_package(
                StoredFoodPackage(
                    food_id=selected_food_id,
                    display_name=normalized_name,
                    primary_model=f"{connection_id}/{normalized_primary}",
                    reasoning_model=(
                        f"{connection_id}/{reasoning_model.strip()}"
                        if reasoning_model.strip()
                        else None
                    ),
                    vision_model=(
                        f"{connection_id}/{vision_model.strip()}"
                        if vision_model.strip()
                        else None
                    ),
                    tool_model=(
                        f"{connection_id}/{tool_model.strip()}"
                        if tool_model.strip()
                        else None
                    ),
                    fallback_model=(
                        f"{connection_id}/{fallback_model.strip()}"
                        if fallback_model.strip()
                        else None
                    ),
                    enabled=True,
                    archived=False,
                )
            )
        except Exception:
            if created_connection_id:
                try:
                    storage.delete_with_secret(created_connection_id)
                except Exception:
                    pass
            raise
        return selected_food_id

    def delete_food(self, *, food_id: str) -> str:
        requested_food_id = food_id.strip()
        if not requested_food_id:
            raise ValueError("粮食 ID 不能为空")

        food_store = self.food_store()
        package = food_store.get_package(requested_food_id)
        if package is None:
            raise ValueError("系统不存在该粮食")
        if package.system_role is not None:
            raise ValueError("系统粮食不能在 Elfie Lab 中删除")

        if package.primary_model is None:
            raise ValueError("该粮食主模型缺失，无法删除")
        try:
            parse_model_reference(package.primary_model)
        except ValueError as error:
            raise ValueError("系统数据异常：粮食绑定的模型引用格式错误") from error

        try:
            food_store.update_package(replace(package, archived=True, enabled=False))
            food_store.delete_package(requested_food_id)
        except (FoodPortConflict, FoodPortError, FoodPortNotFound) as error:
            raise ValueError(str(error)) from error

        return requested_food_id

    def model_evidence(self) -> dict[str, StoredModelEvidence]:
        """Expose configured models as attemptable, not validated, evidence."""
        document = ProviderConnectionStore(self.providers_path).load()
        food_catalog = self.load_food_catalog()
        food_connection_ids: set[str] = set()
        for package in food_catalog.packages.values():
            if (
                package.system_role is not None
                or package.archived
                or not package.enabled
            ):
                continue
            for reference in package.model_references:
                if not reference:
                    continue
                try:
                    food_connection_ids.add(
                        parse_model_reference(reference).connection_id
                    )
                except ValueError:
                    continue
        result: dict[str, StoredModelEvidence] = {}
        for connection in document.connections.values():
            if not connection.enabled or connection.archived:
                continue
            if connection.connection_id not in food_connection_ids:
                # A shared subscription may exist only for the evaluator. It is
                # selectable by the reviewer but must not leak into candidate
                # Food model evidence until a Food references it.
                continue
            profile = get_product(connection.catalog_id, catalog=self.provider_catalog)
            if profile is None:
                continue
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
        models: Sequence[str],
        api_key: str | None,
        alias: str,
    ) -> str:
        store = ProviderConnectionStore(self.providers_path)
        storage = ProviderStorageAdapter(store, secret_path=self.env_path)
        model_records = tuple(
            ProviderModelRecord(
                endpoint_model_id=model,
                display_name=model,
                source="manual",
            )
            for model in models
        )
        display_alias = alias.strip() or "Elfie Lab"
        connection = store.create(
            catalog_id=catalog_id,
            alias=display_alias,
            api_base=api_base,
            api_mode=api_mode,
            auth_type=auth_type,
            models=model_records,
        )
        saved = storage.create_with_secret(connection, api_key)
        return saved.connection_id


def model_execution_food_catalog_store(
    model_environment: ElfieLabModelEnvironment,
) -> FoodPort:
    """Return the Food Port for the Lab-isolated database."""
    model_environment.ensure()
    return model_environment.food_store()


def load_model_execution_food_catalog(
    model_environment: ElfieLabModelEnvironment,
    food_store: FoodPort | None = None,
) -> FoodCatalog:
    """Load the Food projection consumed by the Lab model execution layer."""
    return model_environment.load_food_catalog(food_store)


def default_model_execution_config_dir() -> str:
    """Return the model configuration subroot owned by the isolated Elfie Lab."""
    return str(get_elfie_developer_home() / "elfie_lab" / "runtime")


__all__ = (
    "ElfieLabModelEnvironment",
    "default_model_execution_config_dir",
    "food_connection_type",
    "load_model_execution_food_catalog",
    "model_execution_food_catalog_store",
)
