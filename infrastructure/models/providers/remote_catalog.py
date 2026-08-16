"""Optional read-only client for the centrally maintained Provider catalog."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

REMOTE_CATALOG_URL_ENV = "ELFIENEST_PROVIDER_CATALOG_URL"
REMOTE_CATALOG_SHA256_ENV = "ELFIENEST_PROVIDER_CATALOG_SHA256"
REMOTE_CATALOG_SCHEMA_VERSION = 1
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
    expected_digest = os.environ.get(REMOTE_CATALOG_SHA256_ENV, "").strip().lower()
    if not _is_sha256(expected_digest):
        raise RemoteCatalogUnavailable("远程模型目录缺少有效 SHA-256 固定值")
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise RemoteCatalogUnavailable("远程模型目录必须使用 HTTPS")
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
    actual_digest = hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(actual_digest, expected_digest):
        raise RemoteCatalogUnavailable("远程模型目录完整性校验失败")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RemoteCatalogUnavailable("远程模型目录格式无效") from exc
    if not isinstance(document, dict):
        raise RemoteCatalogUnavailable("远程模型目录格式无效")
    if document.get("version") != REMOTE_CATALOG_SCHEMA_VERSION:
        raise RemoteCatalogUnavailable("远程模型目录版本不受支持")
    products = document.get("products")
    product = products.get(catalog_id) if isinstance(products, dict) else None
    if not isinstance(product, dict):
        raise RemoteCatalogUnavailable("远程模型目录没有当前产品")
    raw_models = product.get("models")
    if not isinstance(raw_models, list):
        raise RemoteCatalogUnavailable("远程模型目录没有当前产品模型")
    models = tuple(
        dict.fromkeys(
            model.strip()
            for model in raw_models
            if isinstance(model, str) and model.strip()
        )
    )
    if not models:
        raise RemoteCatalogUnavailable("远程模型目录没有当前产品模型")
    return models


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )
