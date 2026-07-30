"""Optional read-only client for the centrally maintained Provider catalog."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any
from urllib.request import Request, urlopen

REMOTE_CATALOG_URL_ENV = "ELFIENEST_PROVIDER_CATALOG_URL"
_MAX_CATALOG_BYTES = 2 * 1024 * 1024


class RemoteCatalogUnavailable(RuntimeError):
    """The optional remote catalog could not provide a usable model list."""


def fetch_remote_models(
    catalog_id: str,
    *,
    timeout: float = 3.0,
    opener: Callable[..., Any] = urlopen,
) -> tuple[str, ...]:
    """Return model IDs for one product without persisting remote content."""
    base_url = os.environ.get(REMOTE_CATALOG_URL_ENV, "").strip()
    if not base_url:
        raise RemoteCatalogUnavailable("远程模型目录未配置")
    request = Request(
        f"{base_url.rstrip('/')}/v1/provider-catalog",
        headers={"Accept": "application/json"},
    )
    try:
        with opener(request, timeout=timeout) as response:
            raw = response.read(_MAX_CATALOG_BYTES + 1)
    except Exception as exc:
        raise RemoteCatalogUnavailable("远程模型目录不可用") from exc
    if len(raw) > _MAX_CATALOG_BYTES:
        raise RemoteCatalogUnavailable("远程模型目录响应过大")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RemoteCatalogUnavailable("远程模型目录格式无效") from exc
    if not isinstance(document, dict):
        raise RemoteCatalogUnavailable("远程模型目录格式无效")
    products = document.get("products")
    product = products.get(catalog_id) if isinstance(products, dict) else None
    if not isinstance(product, dict):
        raise RemoteCatalogUnavailable("远程模型目录没有当前产品")
    raw_models = product.get("models")
    if not isinstance(raw_models, list):
        raw_models = [
            model
            for role in ("cheap", "deep", "multimodal")
            for model in (
                product.get("default_models", {}).get(role, [])
                if isinstance(product.get("default_models"), dict)
                else []
            )
        ]
    models = tuple(
        dict.fromkeys(
            str(model).strip() for model in raw_models if str(model).strip()
        )
    )
    if not models:
        raise RemoteCatalogUnavailable("远程模型目录没有当前产品模型")
    return models
