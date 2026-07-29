"""Owner APIs for stable Provider catalog products and connection instances."""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from fastapi import APIRouter, Depends, HTTPException

from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.food.store import FoodCatalogStore, foods_referencing_connection
from ai_runtime.models.catalog import _verify_custom_openai_provider, verify_provider
from ai_runtime.providers.model_identity import match_model_identity
from ai_runtime.providers.profiles import PROVIDER_CATALOG, get_product
from ai_runtime.storage.provider_connections import (
    ProviderConnection,
    ProviderConnectionStore,
    ProviderModelRecord,
)
from ai_runtime.storage.secrets import (
    connection_secret_name,
    resolve_secret,
    set_connection_secret,
)
from ai_runtime.storage.validation_reports import (
    read_latest_provider_validation,
    write_provider_validation_report,
)
from ai_runtime.validation.providers import discover_provider_models
from app.features.accounts.auth import require_owner

from .provider_schemas import (
    ProviderConnectionUpdateRequest,
    ProviderConnectionWriteRequest,
    ProviderModelInput,
    ProviderModelUpdateRequest,
)
from .provider_support import sanitize_error

router = APIRouter()
_CREATE_LOCK = threading.Lock()
_DISCOVERY_SLOTS = threading.BoundedSemaphore(3)
_DISCOVERY_TIMEOUT_SECONDS = 7.0
_VERIFY_SLOTS = threading.BoundedSemaphore(3)
_VERIFY_TIMEOUT_SECONDS = 15.0


def _store() -> ProviderConnectionStore:
    return ProviderConnectionStore()


def _ensure_local_connection(store: ProviderConnectionStore) -> None:
    document = store.load()
    if any(
        connection.catalog_id == "ollama"
        for connection in document.connections.values()
    ):
        return
    profile = get_product("ollama")
    assert profile is not None
    store.create(
        catalog_id="ollama",
        alias=profile.name,
        api_base=profile.api_base,
        api_mode=profile.api_mode,
        auth_type=profile.auth_type,
    )


@router.get("/catalog")
async def list_connection_products(
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> list[dict[str, Any]]:
    _ = owner
    return [
        {
            "catalog_id": catalog_id,
            "name": profile.name,
            "brand": {
                "brand_id": profile.brand_id,
                "name": PROVIDER_CATALOG.brands[profile.brand_id].name,
                "logo_asset": PROVIDER_CATALOG.brands[profile.brand_id].logo_asset,
            },
            "connection_method": profile.connection_method,
            "oauth_available": profile.oauth_available,
            "usage_scope": profile.usage_scope,
            "discovery_strategy": profile.discovery_strategy,
            "api_mode": profile.api_mode,
        }
        for catalog_id, profile in PROVIDER_CATALOG.products.items()
    ]


@router.get("/connections")
async def list_connections(
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> list[dict[str, Any]]:
    _ = owner
    store = _store()
    _ensure_local_connection(store)
    return [
        _connection_view(connection)
        for connection in store.load().connections.values()
    ]


@router.post("/connections", status_code=201)
async def create_connection(
    body: ProviderConnectionWriteRequest,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    profile = get_product(body.catalog_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="未知连接产品")
    if profile.connection_method == "local" and body.api_key:
        raise HTTPException(status_code=422, detail="本地连接不接受 API Key")
    api_base = body.api_base if body.api_base is not None else profile.api_base
    if body.catalog_id == "custom_openai" and not api_base:
        raise HTTPException(status_code=422, detail="自定义连接必须提供 API Base URL")
    with _CREATE_LOCK:
        store = _store()
        _ensure_local_connection(store)
        existing = [
            connection
            for connection in store.load().connections.values()
            if connection.catalog_id == body.catalog_id
        ]
        alias = body.alias or (
            profile.name if not existing else f"{profile.name} {len(existing) + 1}"
        )
        models = _manual_models(body.models or ())
        connection = store.create(
            catalog_id=body.catalog_id,
            alias=alias,
            api_base=api_base,
            api_mode=body.api_mode or profile.api_mode,
            auth_type=body.auth_type or profile.auth_type,
            models=models,
        )
        try:
            if body.api_key is not None:
                credential_ref = set_connection_secret(
                    connection.connection_id,
                    body.api_key,
                )
                connection = replace(connection, credential_ref=credential_ref)
                store.replace(connection)
        except Exception:
            store.delete(connection.connection_id)
            raise
    refresh_result = None
    if body.refresh_models:
        refresh_result = await _refresh_connection_models(connection.connection_id)
        connection = _require_connection(store, connection.connection_id)
    verification = None
    if body.verify:
        verification = await _verify_connection(connection)
    return _connection_view(
        connection,
        verification=verification,
        refresh_result=refresh_result,
    )


@router.put("/connections/{connection_id}")
async def update_connection(
    connection_id: str,
    body: ProviderConnectionUpdateRequest,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    store = _store()
    connection = _require_connection(store, connection_id)
    profile = get_product(connection.catalog_id)
    if profile is None:
        raise HTTPException(status_code=409, detail="连接产品目录已经缺失")
    fields = body.model_fields_set
    updated = replace(
        connection,
        alias=body.alias if "alias" in fields and body.alias else connection.alias,
        api_base=body.api_base if "api_base" in fields else connection.api_base,
        api_mode=body.api_mode if "api_mode" in fields else connection.api_mode,
        auth_type=body.auth_type if "auth_type" in fields else connection.auth_type,
        models=(
            _manual_models(body.models or ())
            if "models" in fields
            else connection.models
        ),
    )
    if body.api_key is not None:
        credential_ref = set_connection_secret(connection_id, body.api_key)
        updated = replace(updated, credential_ref=credential_ref)
    store.replace(updated)
    refresh_result = None
    if body.refresh_models:
        refresh_result = await _refresh_connection_models(connection_id)
        updated = _require_connection(store, connection_id)
    verification = await _verify_connection(updated) if body.verify else None
    return _connection_view(
        updated,
        verification=verification,
        refresh_result=refresh_result,
    )


@router.delete("/connections/{connection_id}")
async def delete_connection(
    connection_id: str,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, str]:
    _ = owner
    store = _store()
    connection = _require_connection(store, connection_id)
    if connection.catalog_id == "ollama":
        raise HTTPException(status_code=400, detail="不能删除默认 Ollama 连接")
    food_keys = foods_referencing_connection(FoodCatalogStore().load(), connection_id)
    if food_keys:
        raise HTTPException(
            status_code=409,
            detail=(
                f"连接 '{connection_id}' 仍被粮食套餐引用："
                + "、".join(food_keys)
            ),
        )
    store.delete(connection_id)
    set_connection_secret(connection_id, "")
    return {"detail": f"连接 '{connection_id}' 已删除"}


@router.post("/connections/{connection_id}/verify")
async def verify_connection_route(
    connection_id: str,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    connection = _require_connection(_store(), connection_id)
    return {
        "connection_id": connection_id,
        "verification": await _verify_connection(connection),
    }


@router.post("/connections/{connection_id}/models/refresh")
async def refresh_connection_models(
    connection_id: str,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    return await _refresh_connection_models(connection_id)


@router.post("/connections/{connection_id}/models", status_code=201)
async def add_connection_model(
    connection_id: str,
    body: ProviderModelInput,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    store = _store()
    connection = _require_connection(store, connection_id)
    if any(model.endpoint_model_id == body.id for model in connection.models):
        raise HTTPException(status_code=409, detail="该连接已存在同名模型")
    model = _model_record(body, source="manual")
    store.replace(replace(connection, models=(*connection.models, model)))
    return _model_view(model)


@router.put("/connections/{connection_id}/models/{model_id:path}")
async def update_connection_model(
    connection_id: str,
    model_id: str,
    body: ProviderModelUpdateRequest,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, Any]:
    _ = owner
    store = _store()
    connection = _require_connection(store, connection_id)
    current = next(
        (model for model in connection.models if model.endpoint_model_id == model_id),
        None,
    )
    if current is None:
        raise HTTPException(status_code=404, detail="模型不存在")
    fields = body.model_fields_set
    updated = replace(
        current,
        display_name=(
            body.display_name
            if "display_name" in fields and body.display_name
            else current.display_name
        ),
        canonical_model_id=(
            body.canonical_model_id
            if "canonical_model_id" in fields
            else current.canonical_model_id
        ),
        context_window_tokens=(
            body.context_window_tokens
            if "context_window_tokens" in fields
            else current.context_window_tokens
        ),
        max_output_tokens=(
            body.max_output_tokens
            if "max_output_tokens" in fields
            else current.max_output_tokens
        ),
        supports_tools=(
            body.supports_tools
            if "supports_tools" in fields
            else current.supports_tools
        ),
        supports_vision=(
            body.supports_vision
            if "supports_vision" in fields
            else current.supports_vision
        ),
        supports_reasoning=(
            body.supports_reasoning
            if "supports_reasoning" in fields
            else current.supports_reasoning
        ),
        hidden=body.hidden if "hidden" in fields else current.hidden,
    )
    models = tuple(
        updated if model.endpoint_model_id == model_id else model
        for model in connection.models
    )
    store.replace(replace(connection, models=models))
    return _model_view(updated)


@router.delete("/connections/{connection_id}/models/{model_id:path}")
async def delete_connection_model(
    connection_id: str,
    model_id: str,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> dict[str, str]:
    _ = owner
    store = _store()
    connection = _require_connection(store, connection_id)
    current = next(
        (model for model in connection.models if model.endpoint_model_id == model_id),
        None,
    )
    if current is None:
        raise HTTPException(status_code=404, detail="模型不存在")
    if current.source != "manual":
        raise HTTPException(
            status_code=409,
            detail="自动发现或目录模型不能删除，请改为隐藏",
        )
    store.replace(
        replace(
            connection,
            models=tuple(
                model
                for model in connection.models
                if model.endpoint_model_id != model_id
            ),
        )
    )
    return {"detail": f"模型 '{model_id}' 已删除"}


def _require_connection(
    store: ProviderConnectionStore,
    connection_id: str,
) -> ProviderConnection:
    connection = store.load().connections.get(connection_id)
    if connection is None:
        raise HTTPException(status_code=404, detail=f"连接 '{connection_id}' 不存在")
    return connection


def _manual_models(
    inputs: Iterable[ProviderModelInput],
) -> tuple[ProviderModelRecord, ...]:
    return tuple(_model_record(item, source="manual") for item in inputs)


def _model_record(
    item: ProviderModelInput,
    *,
    source: str,
) -> ProviderModelRecord:
    match = match_model_identity(item.id, item.display_name)
    canonical_model_id = item.canonical_model_id or (
        match.canonical_model_id if match else None
    )
    return ProviderModelRecord(
        endpoint_model_id=item.id,
        display_name=item.display_name or item.id,
        canonical_model_id=canonical_model_id,
        source=source,  # type: ignore[arg-type]
        context_window_tokens=item.context_window_tokens
        or (match.context_window_tokens if match else None),
        max_output_tokens=item.max_output_tokens
        or (match.max_output_tokens if match else None),
        supports_tools=(
            item.supports_tools
            if item.supports_tools is not None
            else match.supports_tools if match else None
        ),
        supports_vision=(
            item.supports_vision
            if item.supports_vision is not None
            else match.supports_vision if match else None
        ),
        supports_reasoning=(
            item.supports_reasoning
            if item.supports_reasoning is not None
            else match.supports_reasoning if match else None
        ),
    )


async def _refresh_connection_models(connection_id: str) -> dict[str, Any]:
    store = _store()
    connection = _require_connection(store, connection_id)
    profile = get_product(connection.catalog_id)
    if profile is None:
        raise HTTPException(status_code=409, detail="连接产品目录已经缺失")
    checked_at = datetime.now(timezone.utc).isoformat()
    try:
        discovered = await asyncio.wait_for(
            asyncio.to_thread(_discover_with_slot, connection),
            timeout=_DISCOVERY_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        catalog_models = (
            _catalog_models(profile.default_models)
            if connection.catalog_id != "custom_openai"
            else ()
        )
        if catalog_models:
            store.replace(replace(connection, models=catalog_models))
            return {
                "status": "catalog",
                "checked_at": checked_at,
                "message": "模型接口不可用，已使用内置产品清单",
                "models": [_model_view(model) for model in catalog_models],
            }
        message = sanitize_error(
            str(exc),
            secrets=(_connection_api_key(connection),),
        )
        return {
            "status": "failed",
            "checked_at": checked_at,
            "message": f"模型获取失败，请手工添加模型：{message}",
            "models": [_model_view(model) for model in connection.models],
        }
    models = tuple(
        _model_record(
            ProviderModelInput(id=item.name, display_name=item.display_name or item.name),
            source="discovered",
        )
        for item in discovered
    )
    if not models:
        return {
            "status": "failed",
            "checked_at": checked_at,
            "message": "模型接口未返回结果，请手工添加模型",
            "models": [_model_view(model) for model in connection.models],
        }
    store.replace(replace(connection, models=models))
    return {
        "status": "updated",
        "checked_at": checked_at,
        "message": None,
        "models": [_model_view(model) for model in models],
    }


def _discover_with_slot(connection: ProviderConnection):
    if not _DISCOVERY_SLOTS.acquire(blocking=False):
        raise RuntimeError("模型发现任务过多，请稍后重试")
    try:
        runtime_id, config = _runtime_projection(connection)
        return discover_provider_models(
            runtime_id,
            config,
            timeout=5.0,
            allow_configured_fallback=False,
        )
    finally:
        _DISCOVERY_SLOTS.release()


def _catalog_models(
    roles: Dict[str, list[str]],
) -> tuple[ProviderModelRecord, ...]:
    model_ids = dict.fromkeys(
        model_id
        for role in ("cheap", "deep", "multimodal")
        for model_id in roles.get(role, [])
    )
    return tuple(
        _model_record(
            ProviderModelInput(id=model_id, display_name=model_id),
            source="provider_catalog",
        )
        for model_id in model_ids
    )


async def _verify_connection(connection: ProviderConnection) -> dict[str, Any]:
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_verify_with_slot, connection),
            timeout=_VERIFY_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        result = {
            "status": "failed",
            "latency_ms": None,
            "error": "连接验证超时",
        }
    status = "passed" if result.get("status") in {"active", "passed"} else "failed"
    checked_at = datetime.now(timezone.utc).isoformat()
    latency = result.get("latency_ms")
    error = sanitize_error(
        str(result["error"]) if result.get("error") else "",
        secrets=(_connection_api_key(connection),),
    ) or None
    verification = {
        "status": status,
        "checked_at": checked_at,
        "latency_ms": float(latency) if isinstance(latency, (int, float)) else None,
        "error": error,
    }
    write_provider_validation_report(
        connection.connection_id,
        status=status,
        checked_at=checked_at,
        latency_ms=verification["latency_ms"],
        error=error,
        trigger="single",
    )
    return verification


def _verify_with_slot(connection: ProviderConnection) -> dict[str, Any]:
    if not _VERIFY_SLOTS.acquire(blocking=False):
        return {
            "status": "failed",
            "latency_ms": None,
            "error": "连接验证任务过多，请稍后重试",
        }
    started = time.perf_counter()
    try:
        runtime_id, config = _runtime_projection(connection)
        provider = config.providers[runtime_id]
        if connection.catalog_id == "custom_openai":
            return _verify_custom_openai_provider(
                provider,
                connection.api_base,
                _connection_api_key(connection),
            )
        return verify_provider(runtime_id, config)
    except Exception as exc:
        return {
            "status": "failed",
            "latency_ms": (time.perf_counter() - started) * 1000,
            "error": str(exc),
        }
    finally:
        _VERIFY_SLOTS.release()


def _runtime_projection(
    connection: ProviderConnection,
) -> tuple[str, LLMRuntimeConfig]:
    profile = get_product(connection.catalog_id)
    if profile is None:
        raise ValueError("连接产品目录已经缺失")
    runtime_id = (
        connection.connection_id
        if connection.catalog_id == "custom_openai"
        else profile.legacy_provider_id
    )
    config = LLMRuntimeConfig()
    config.providers[runtime_id] = {
        "api_base": connection.api_base or profile.api_base,
        "api_mode": connection.api_mode or profile.api_mode,
        "auth_type": connection.auth_type or profile.auth_type,
        "api_key": _connection_api_key(connection),
        "models": [
            {"id": model.endpoint_model_id, "display_name": model.display_name}
            for model in connection.models
        ],
        "test_model": (
            connection.models[0].endpoint_model_id
            if connection.models
            else profile.test_model
        ),
    }
    return runtime_id, config


def _connection_api_key(connection: ProviderConnection) -> str:
    secret_name = connection.credential_ref or connection_secret_name(
        connection.connection_id
    )
    return resolve_secret(secret_name)


def _connection_view(
    connection: ProviderConnection,
    *,
    verification: Optional[dict[str, Any]] = None,
    refresh_result: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    profile = get_product(connection.catalog_id)
    latest = verification or read_latest_provider_validation(
        connection.connection_id
    )
    if not latest:
        latest = {
            "status": "never",
            "checked_at": None,
            "latency_ms": None,
            "error": None,
        }
    return {
        "connection_id": connection.connection_id,
        "catalog_id": connection.catalog_id,
        "alias": connection.alias,
        "api_base": connection.api_base,
        "api_mode": connection.api_mode,
        "auth_type": connection.auth_type,
        "has_api_key": bool(_connection_api_key(connection)),
        "enabled": connection.enabled,
        "usage_scope": profile.usage_scope if profile else "general",
        "verification": {
            "status": latest.get("status", "never"),
            "checked_at": latest.get("checked_at"),
            "latency_ms": latest.get("latency_ms"),
            "error": latest.get("error"),
        },
        "models": [_model_view(model) for model in connection.models],
        "model_refresh": refresh_result,
    }


def _model_view(model: ProviderModelRecord) -> dict[str, Any]:
    return {
        "id": model.endpoint_model_id,
        "display_name": model.display_name,
        "canonical_model_id": model.canonical_model_id,
        "source": model.source,
        "context_window_tokens": model.context_window_tokens,
        "max_output_tokens": model.max_output_tokens,
        "supports_tools": model.supports_tools,
        "supports_vision": model.supports_vision,
        "supports_reasoning": model.supports_reasoning,
        "hidden": model.hidden,
    }
