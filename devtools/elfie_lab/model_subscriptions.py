"""统一的 Elfie Lab 模型订阅投影。

Food 和评审模型使用同一份 Provider connection 记录，但在产品层保留各自的
用途引用。这个模块只负责安全的公开投影；凭据仍由 ProviderStorageAdapter
管理，绝不返回 API Key。
"""

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from infrastructure.models.ollama.ollama_platform import DEFAULT_OLLAMA_ENDPOINT
from infrastructure.models.provider_records import ProviderConnection
from infrastructure.persistence.provider_connections import ProviderConnectionStore
from infrastructure.persistence.provider_storage import ProviderStorageAdapter


def _connection_type(connection: ProviderConnection) -> str:
    return (
        "ollama"
        if connection.catalog_id == "ollama" or connection.api_mode == "ollama"
        else "openai"
    )


def _supports_reviewer(connection: ProviderConnection) -> bool:
    if _connection_type(connection) != "openai":
        return False
    parsed = urlsplit((connection.api_base or "").strip())
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower().rstrip(".")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    return address is None or not (
        address.is_loopback or address.is_private or address.is_link_local
    )


def list_model_subscriptions(root: str | Path) -> list[dict[str, Any]]:
    """Return all active Lab subscriptions usable by at least one consumer."""
    root_path = Path(root).expanduser().resolve()
    providers_path = root_path / "configs" / "providers.yaml"
    secret_path = root_path / "configs" / "auth.env"
    store = ProviderConnectionStore(providers_path)
    storage = ProviderStorageAdapter(store, secret_path=secret_path)
    result: list[dict[str, Any]] = []
    for connection_id, connection in sorted(store.load().connections.items()):
        if not connection.enabled or connection.archived:
            continue
        models = [
            model.endpoint_model_id
            for model in connection.models
            if not model.hidden and not model.retired and model.available
        ]
        if not models:
            continue
        kind = _connection_type(connection)
        supports_reviewer = _supports_reviewer(connection)
        result.append(
            {
                "id": connection_id,
                "display_name": connection.alias,
                "connection_type": kind,
                "api_base": connection.api_base
                or (DEFAULT_OLLAMA_ENDPOINT if kind == "ollama" else ""),
                "models": models,
                "model_count": len(models),
                "has_api_key": bool(
                    connection.credential_ref
                    and storage.has_secret(connection.credential_ref)
                ),
                "supports_food": True,
                "supports_reviewer": supports_reviewer,
            }
        )
    return result


def subscription_by_id(
    root: str | Path, subscription_id: str
) -> ProviderConnection | None:
    """Resolve one active shared subscription without exposing its secret."""
    normalized = subscription_id.strip()
    if not normalized:
        return None
    root_path = Path(root).expanduser().resolve()
    connection = (
        ProviderConnectionStore(root_path / "configs" / "providers.yaml")
        .load()
        .connections.get(normalized)
    )
    if connection is None or not connection.enabled or connection.archived:
        return None
    return connection


__all__ = ("list_model_subscriptions", "subscription_by_id")
