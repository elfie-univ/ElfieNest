from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends

from runtime.models.catalog import BUILTIN_MODEL_CATALOG
from runtime.models.groups import DEFAULT_MODEL_GROUPS
from runtime.usage.observer import RuntimeEvent, get_runtime_observer
from runtime.usage.token_tracker import get_token_tracker

from .admin_routes import require_admin

router = APIRouter(prefix="/api/admin/runtime", tags=["runtime"])

_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
_RUNTIME_CONFIG_PATH: Path = _PROJECT_ROOT / "runtime" / "runtime_config.json"


def _read_runtime_config() -> Dict[str, Any]:
    if not _RUNTIME_CONFIG_PATH.exists():
        return {}
    try:
        with _RUNTIME_CONFIG_PATH.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


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
            "groups": _model_groups_payload(),
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
    admin: Dict[str, Any] = Depends(require_admin),  # noqa: B008
) -> Dict[str, Any]:
    _ = admin
    return build_runtime_status()


def _provider_is_active(provider_id: str, info: Any) -> bool:
    if provider_id == "ollama":
        return True
    if not isinstance(info, dict):
        return False
    return bool(info.get("api_key")) or info.get("status") == "active"


def _dict_field(data: Dict[str, Any], field_name: str) -> Dict[str, Any]:
    field_value = data.get(field_name, {})
    return field_value if isinstance(field_value, dict) else {}


def _model_groups_payload() -> list[Dict[str, Any]]:
    return [
        {
            "key": group.key,
            "display_name": group.display_name,
            "model_keys": list(group.model_keys),
        }
        for group in DEFAULT_MODEL_GROUPS.values()
    ]


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
