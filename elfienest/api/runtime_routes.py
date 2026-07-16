from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from elfienest.config.runtime_store import read_runtime_config, write_runtime_config
from runtime.food.models import FIXED_FOOD_KINDS
from runtime.models.catalog import BUILTIN_MODEL_CATALOG
from runtime.policy.food_policy import RuntimeTaskType
from runtime.safety.permissions import DEFAULT_TOOL_PERMISSIONS
from runtime.storage.data_home import get_config_path
from runtime.usage.observer import RuntimeEvent, get_runtime_observer
from runtime.usage.token_tracker import get_token_tracker

from .owner_routes import require_owner

router = APIRouter(prefix="/api/owner/runtime", tags=["runtime"])

def _read_runtime_config() -> Dict[str, Any]:
    return read_runtime_config(get_config_path())


def _write_runtime_config(config: Dict[str, Any]) -> None:
    write_runtime_config(get_config_path(), config)


def build_runtime_status() -> Dict[str, Any]:
    config = _read_runtime_config()
    providers = _dict_field(config, "providers")
    model_overrides = _dict_field(config, "models")
    observer_events = get_runtime_observer().snapshot()

    provider_total = len(providers)
    provider_active = sum(
        1 for provider_id, info in providers.items() if _provider_is_active(provider_id, info)
    )
    model_total = len(BUILTIN_MODEL_CATALOG)
    hidden_models = {
        model_id
        for model_id, override in model_overrides.items()
        if isinstance(override, dict) and override.get("visible") is False
    }
    fallback_raw = providers.get("ollama", {})
    fallback_info = fallback_raw if isinstance(fallback_raw, dict) else {}
    fallback_configured = bool(fallback_info.get("api_base")) or "ollama" in providers

    notes = _build_notes(
        provider_active=provider_active,
        provider_total=provider_total,
        fallback_configured=fallback_configured,
        observer_events=observer_events,
    )

    return {
        "status": "ok",
        "providers": {
            "total": provider_total,
            "active": provider_active,
            "inactive": max(provider_total - provider_active, 0),
        },
        "models": {
            "total": model_total,
            "visible": max(model_total - len(hidden_models), 0),
            "hidden": len(hidden_models),
            "groups": [],
        },
        "fallback": {
            "provider": "ollama",
            "configured": fallback_configured,
            "api_base": str(fallback_info.get("api_base", "")),
        },
        "tools": {
            "web_search": {"available": True},
            "code_sandbox": {"available": True},
            "skills_evolution": {"available": True},
        },
        "usage": get_token_tracker().get_tick_summary(),
        "observer": {
            "event_count": len(observer_events),
            "last_event": _event_payload(observer_events[-1]) if observer_events else None,
        },
        "notes": notes,
    }


@router.get("/status")
async def get_runtime_status(
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> Dict[str, Any]:
    _ = owner
    return build_runtime_status()


@router.get("/policy")
async def get_runtime_policy(
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> Dict[str, Any]:
    _ = owner
    config = _read_runtime_config()
    runtime_policy = _dict_field(config, "runtime_policy")
    return _runtime_policy_payload(runtime_policy)


@router.put("/policy")
async def update_runtime_policy(
    body: Dict[str, Any],
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> Dict[str, Any]:
    _ = owner
    current_config = _read_runtime_config()
    existing_policy = _dict_field(current_config, "runtime_policy")
    merged_policy = _merge_runtime_policy(existing_policy, body)
    _validate_runtime_policy(merged_policy)
    current_config["runtime_policy"] = merged_policy
    _write_runtime_config(current_config)
    return _runtime_policy_payload(merged_policy)


@router.get("/audit")
async def get_runtime_audit(
    limit: int = 100,
    owner: Dict[str, Any] = Depends(require_owner),  # noqa: B008
) -> Dict[str, Any]:
    _ = owner
    bounded_limit = min(max(limit, 1), 500)
    events = get_runtime_observer().snapshot()
    recent_events = events[-bounded_limit:]
    return {
        "event_count": len(events),
        "events": [_event_payload(event) for event in recent_events],
    }


def _provider_is_active(provider_id: str, info: Any) -> bool:
    if provider_id == "ollama":
        return True
    if not isinstance(info, dict):
        return False
    return bool(info.get("api_key")) or info.get("status") == "active"


def _dict_field(data: Dict[str, Any], field_name: str) -> Dict[str, Any]:
    field_value = data.get(field_name, {})
    return field_value if isinstance(field_value, dict) else {}


def _runtime_policy_payload(runtime_policy: Dict[str, Any]) -> Dict[str, Any]:
    defaults = {
        RuntimeTaskType.CHAT.value: "standard",
        RuntimeTaskType.REASONING.value: "focus",
        RuntimeTaskType.VISION.value: "vision",
        RuntimeTaskType.CODE.value: "tool",
        RuntimeTaskType.ORGANIZE.value: "focus",
    }
    raw_routes = runtime_policy.get("task_routes", {})
    if isinstance(raw_routes, dict):
        defaults.update(
            {
                task_type: food_key
                for task_type, food_key in raw_routes.items()
                if task_type in {item.value for item in RuntimeTaskType}
                and food_key in FIXED_FOOD_KINDS
            }
        )
    return {
        "task_routes": defaults,
        "food_keys": list(FIXED_FOOD_KINDS),
        "tool_permissions": _tool_permissions_payload(runtime_policy),
    }


def _tool_permissions_payload(runtime_policy: Dict[str, Any]) -> Dict[str, Any]:
    permissions = {
        action: {
            "mode": rule.mode.value,
            "reason": rule.reason,
        }
        for action, rule in DEFAULT_TOOL_PERMISSIONS.items()
    }
    raw_permissions = runtime_policy.get("tool_permissions", {})
    if not isinstance(raw_permissions, dict):
        return permissions
    for action, rule in raw_permissions.items():
        if isinstance(action, str) and isinstance(rule, dict):
            permissions[action] = {
                "mode": str(rule.get("mode", "")),
                "reason": str(rule.get("reason", "")),
            }
    return permissions


def _merge_runtime_policy(
    existing_policy: Dict[str, Any],
    updates: Dict[str, Any],
) -> Dict[str, Any]:
    if not isinstance(updates, dict):
        raise HTTPException(status_code=422, detail="runtime policy body 必须是对象")

    merged = dict(existing_policy)
    if "model_groups" in updates:
        raise HTTPException(
            status_code=410,
            detail="model_groups 已停用；任务只能路由到粮食 key，模型由粮食配方管理",
        )
    for field_name in ("task_routes", "tool_permissions"):
        if field_name in updates:
            value = updates[field_name]
            if not isinstance(value, dict):
                raise HTTPException(status_code=422, detail=f"{field_name} 必须是对象")
            current_value = merged.get(field_name, {})
            current_mapping = current_value if isinstance(current_value, dict) else {}
            merged[field_name] = {**current_mapping, **value}
    return merged


def _validate_runtime_policy(runtime_policy: Dict[str, Any]) -> None:
    valid_modes = {"allow", "ask", "deny", "owner"}
    valid_task_types = {task_type.value for task_type in RuntimeTaskType}
    routes = runtime_policy.get("task_routes", {})
    if isinstance(routes, dict):
        for task_type, group_key in routes.items():
            if task_type not in valid_task_types or not isinstance(group_key, str):
                raise HTTPException(status_code=422, detail="task_routes 格式错误")

    permissions = runtime_policy.get("tool_permissions", {})
    if isinstance(permissions, dict):
        for action, rule in permissions.items():
            if not isinstance(action, str) or not isinstance(rule, dict):
                raise HTTPException(status_code=422, detail="tool_permissions 格式错误")
            mode = rule.get("mode")
            if mode not in valid_modes:
                raise HTTPException(
                    status_code=422,
                    detail=f"权限模式必须是 {sorted(valid_modes)} 之一",
                )

    if isinstance(routes, dict):
        invalid_foods = [
            food_key for food_key in routes.values() if food_key not in FIXED_FOOD_KINDS
        ]
        if invalid_foods:
            raise HTTPException(
                status_code=422,
                detail=f"task_routes 只能使用粮食 key: {list(FIXED_FOOD_KINDS)}",
            )


def _event_payload(event: RuntimeEvent) -> Dict[str, Any]:
    return event.to_dict()


def _build_notes(
    provider_active: int,
    provider_total: int,
    fallback_configured: bool,
    observer_events: tuple[RuntimeEvent, ...],
) -> list[str]:
    notes: list[str] = []
    if not fallback_configured:
        notes.append("[模型] Ollama 兜底未配置，请先运行 runtime/setup_runtime.py。")
    if provider_total == 0 or provider_active == 0:
        notes.append("[Provider] 尚未检测到可用模型供应商。")
    if observer_events:
        notes.append(f"[运行时] 已记录 {len(observer_events)} 条模型/工具调用观测事件。")
    else:
        notes.append("[运行时] 暂无模型或工具调用观测事件。")
    return notes
