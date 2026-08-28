"""独立的远程评审订阅存储与调用适配。

评审订阅不是粮食：它只负责给评测器提供一个 OpenAI-compatible 远程模型，
不会创建 Food，也不会被候选精灵对话使用。
"""

from __future__ import annotations

import ipaddress
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from infrastructure.models.provider_records import (
    ProviderConnection,
    ProviderModelRecord,
)
from infrastructure.models.providers.dispatch import call_openai_compatible_api
from infrastructure.persistence.provider_connections import ProviderConnectionStore
from infrastructure.persistence.provider_storage import ProviderStorageAdapter

# New subscriptions use the shared OpenAI connection catalog so the same
# provider record can be selected by Food and by the reviewer model picker.
# Legacy ``reviewer_openai`` records remain readable for existing Lab data.
REVIEWER_CATALOG_ID = "reviewer_openai"
SHARED_REMOTE_CATALOG_ID = "custom_openai"


def _normalize_api_base(value: str) -> str:
    base = value.strip().rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("评审模型只支持远程 HTTPS OpenAI-compatible 地址")
    if parsed.username or parsed.password:
        raise ValueError("API URL 不能内嵌用户名或密码")
    host = parsed.hostname.strip().lower().rstrip(".")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ValueError("评审模型不能使用本机或局域网地址")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and (
        address.is_loopback or address.is_private or address.is_link_local
    ):
        raise ValueError("评审模型不能使用本机或私有网络地址")
    return base


def _normalize_models(models: Sequence[str]) -> tuple[str, ...]:
    result = tuple(
        dict.fromkeys(
            item.strip() for item in models if isinstance(item, str) and item.strip()
        )
    )
    if not result:
        raise ValueError("评审订阅至少要包含一个模型")
    return result


def validate_reviewer_connection(*, api_base: str, api_key: str, model: str) -> None:
    """用一个极小请求验证订阅和所选模型，错误不写入持久化配置。"""
    try:
        response = call_openai_compatible_api(
            api_base,
            api_key,
            model,
            [{"role": "user", "content": "Reply with OK."}],
            0.0,
            8,
            provider="Elfie Lab 评审模型",
            timeout_seconds=20.0,
        )[0]
    except Exception as error:
        detail = str(error).strip() or type(error).__name__
        raise ValueError(f"评审模型连接验证失败：{detail}") from error
    if not response.strip():
        raise ValueError("评审模型连接验证失败：模型返回空响应")


class ReviewerSubscriptionStore:
    """在同一 Lab 配置根下管理独立的远程评审订阅记录。"""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.providers_path = self.root / "configs" / "providers.yaml"
        self.secret_path = self.root / "configs" / "auth.env"

    def _store_and_storage(
        self,
    ) -> tuple[ProviderConnectionStore, ProviderStorageAdapter]:
        store = ProviderConnectionStore(self.providers_path)
        return store, ProviderStorageAdapter(store, secret_path=self.secret_path)

    def _connections(self) -> Mapping[str, ProviderConnection]:
        connections: dict[str, ProviderConnection] = {}
        for key, value in (
            ProviderConnectionStore(self.providers_path).load().connections.items()
        ):
            if value.catalog_id not in {REVIEWER_CATALOG_ID, SHARED_REMOTE_CATALOG_ID}:
                continue
            if not value.enabled or value.archived:
                continue
            # A shared connection can also be a local Food.  Keeping it in the
            # Food catalog is correct, but it must never become a reviewer by
            # calling the evaluation API directly.  Apply the same remote-only
            # rule here as the reviewer save flow and the public subscription
            # projection.
            try:
                _normalize_api_base(value.api_base or "")
            except ValueError:
                continue
            connections[key] = value
        return connections

    def list_public(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        store = ProviderConnectionStore(self.providers_path)
        storage = ProviderStorageAdapter(store, secret_path=self.secret_path)
        for connection_id, connection in sorted(self._connections().items()):
            models = [
                model.endpoint_model_id
                for model in connection.models
                if not model.hidden and not model.retired and model.available
            ]
            result.append(
                {
                    "id": connection_id,
                    "display_name": connection.alias,
                    "api_base": connection.api_base,
                    "models": models,
                    "model_count": len(models),
                    "has_api_key": bool(
                        connection.credential_ref
                        and storage.has_secret(connection.credential_ref)
                    ),
                }
            )
        return result

    def get(self, subscription_id: str) -> ProviderConnection:
        connection = self._connections().get(subscription_id.strip())
        if connection is None:
            raise ValueError("评审订阅不存在或已删除")
        return connection

    def descriptor(self, subscription_id: str, model: str = "") -> dict[str, Any]:
        connection = self.get(subscription_id)
        available = tuple(
            item.endpoint_model_id
            for item in connection.models
            if not item.hidden and not item.retired and item.available
        )
        selected = model.strip() or (available[0] if available else "")
        if selected not in available:
            raise ValueError("评审模型必须来自该评审订阅的模型列表")
        return {
            "id": connection.connection_id,
            "display_name": connection.alias,
            "api_base": connection.api_base,
            "api_key": ProviderStorageAdapter(
                ProviderConnectionStore(self.providers_path),
                secret_path=self.secret_path,
            ).resolve_secret(connection.credential_ref)
            if connection.credential_ref
            else "",
            "model": selected,
            "models": list(available),
        }

    def save(
        self,
        *,
        subscription_id: str | None,
        display_name: str,
        api_base: str,
        api_key: str | None,
        models: Sequence[str],
    ) -> dict[str, Any]:
        alias = display_name.strip()
        if not alias:
            raise ValueError("评审订阅名称不能为空")
        normalized_base = _normalize_api_base(api_base)
        normalized_models = _normalize_models(models)
        store, storage = self._store_and_storage()
        existing = self.get(subscription_id) if subscription_id else None
        effective_key = (api_key or "").strip()
        if not effective_key and existing is not None and existing.credential_ref:
            effective_key = storage.resolve_secret(existing.credential_ref)
        validate_reviewer_connection(
            api_base=normalized_base,
            api_key=effective_key,
            model=normalized_models[0],
        )
        records = tuple(
            ProviderModelRecord(
                endpoint_model_id=model, display_name=model, source="manual"
            )
            for model in normalized_models
        )
        if existing is None:
            connection = store.create(
                catalog_id=SHARED_REMOTE_CATALOG_ID,
                alias=alias,
                api_base=normalized_base,
                api_mode="chat_completions",
                auth_type="bearer" if effective_key else "none",
                models=records,
            )
            try:
                storage.create_with_secret(connection, effective_key or None)
            except Exception:
                storage.delete_with_secret(connection.connection_id)
                raise
            selected_id = connection.connection_id
        else:
            connection = replace(
                existing,
                alias=alias,
                api_base=normalized_base,
                api_mode="chat_completions",
                auth_type="bearer" if effective_key else "none",
                models=records,
            )
            storage.replace_with_secret(connection, effective_key or None)
            selected_id = existing.connection_id
        return next(item for item in self.list_public() if item["id"] == selected_id)

    def delete(self, subscription_id: str) -> bool:
        self.get(subscription_id)
        _store, storage = self._store_and_storage()
        return storage.delete_with_secret(subscription_id.strip())


class ReviewerModelExecutionAgent:
    """Tiny ``ask`` adapter used only by the automatic evaluator."""

    def __init__(self, descriptor: Mapping[str, Any]) -> None:
        self._api_base = str(descriptor.get("api_base") or "")
        self._api_key = str(descriptor.get("api_key") or "")
        self._model = str(descriptor.get("model") or "")
        self.subscription_id = str(descriptor.get("id") or "")

    def ask(self, prompt: str, energy: float, task_complexity: int) -> str:
        del energy, task_complexity
        response = call_openai_compatible_api(
            self._api_base,
            self._api_key,
            self._model,
            [{"role": "user", "content": prompt}],
            0.0,
            1024,
            provider=self.subscription_id,
            timeout_seconds=60.0,
        )[0]
        return response


__all__ = (
    "REVIEWER_CATALOG_ID",
    "ReviewerModelExecutionAgent",
    "ReviewerSubscriptionStore",
    "validate_reviewer_connection",
)
