"""Shared state projection helpers for Owner Provider routes."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable

from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.providers.model_hints import configured_model_specs
from ai_runtime.providers.profiles import get_profile
from ai_runtime.storage.data_home import get_config_path
from app.features.configuration.runtime_store import (
    hydrate_runtime_secrets,
    read_runtime_config,
    write_runtime_config,
)

_URL_CREDENTIALS = re.compile(r"(https?://)[^/@\s]+@", re.IGNORECASE)


def read_provider_config() -> Dict[str, Any]:
    path = get_config_path()
    config = read_runtime_config(path)
    if path.suffix in {".yaml", ".yml"}:
        return hydrate_runtime_secrets(config)
    return config


def write_provider_config(config: Dict[str, Any]) -> None:
    write_runtime_config(get_config_path(), config)


def runtime_config(config: Dict[str, Any]) -> LLMRuntimeConfig:
    result = LLMRuntimeConfig()
    result.providers.update(
        {
            key: value
            for key, value in config.get("providers", {}).items()
            if isinstance(value, dict)
        }
    )
    return result


def is_configured(provider_id: str, info: Dict[str, Any]) -> bool:
    profile = get_profile(provider_id)
    method = (
        profile.connection_method
        if profile
        else ("local" if info.get("auth_type") == "none" else "api_key")
    )
    api_base = str(
        info.get("api_base") or (profile.api_base if profile else "")
    ).strip()
    if method == "local":
        return bool(api_base)
    if method == "oauth":
        return bool(
            profile and profile.oauth_available and info.get("oauth_credentials")
        )
    return bool(api_base and info.get("api_key"))


def model_source(info: Dict[str, Any]) -> str:
    refresh = info.get("model_refresh")
    if isinstance(refresh, dict) and refresh.get("status") == "updated":
        return "discovered"
    if info.get("models"):
        return "manual"
    return "configured"


def provider_models(info: Dict[str, Any]) -> list[dict[str, str]]:
    source = model_source(info)
    return [
        {
            "id": item.model_id,
            "display_name": item.display_name,
            "source": source,
        }
        for item in configured_model_specs(info)
    ]


def verification_view(info: Dict[str, Any]) -> dict[str, Any]:
    raw = info.get("verification")
    if not isinstance(raw, dict):
        raw = {}
    status = str(raw.get("status") or "never")
    if status not in {"never", "passed", "failed"}:
        status = "never"
    latency = raw.get("latency_ms")
    return {
        "status": status,
        "checked_at": str(raw["checked_at"]) if raw.get("checked_at") else None,
        "latency_ms": float(latency) if isinstance(latency, (int, float)) else None,
        "error": str(raw["error"]) if raw.get("error") else None,
    }


def provider_view(provider_id: str, info: Dict[str, Any]) -> dict[str, Any]:
    profile = get_profile(provider_id)
    display_name = str(info.get("display_name") or info.get("name") or "")
    api_mode = str(
        info.get("api_mode") or (profile.api_mode if profile else "chat_completions")
    )
    auth_type = str(
        info.get("auth_type") or (profile.auth_type if profile else "bearer")
    )
    connection_method = (
        profile.connection_method
        if profile
        else ("local" if auth_type == "none" else "api_key")
    )
    verification = verification_view(info)
    configured = is_configured(provider_id, info)
    return {
        "provider_id": provider_id,
        "name": display_name or (profile.name if profile else provider_id),
        "display_name": display_name,
        "api_base": str(info.get("api_base") or (profile.api_base if profile else "")),
        "api_mode": api_mode,
        "auth_type": auth_type,
        "test_model": str(info.get("test_model") or ""),
        "configured": configured,
        "configuration_status": "configured" if configured else "unconfigured",
        "verification": verification,
        "has_api_key": bool(info.get("api_key")),
        "models": provider_models(info),
        "model_refresh": info.get("model_refresh", {}),
        "capabilities": {
            "connection_method": connection_method,
            "oauth_available": bool(profile and profile.oauth_available),
            "oauth_unavailable": connection_method == "oauth"
            and not bool(profile and profile.oauth_available),
            "model_discovery": bool(
                str(info.get("api_base") or (profile.api_base if profile else ""))
            ),
        },
    }


def reset_verification(info: Dict[str, Any]) -> None:
    info["verification"] = {
        "status": "never",
        "checked_at": None,
        "latency_ms": None,
        "error": None,
    }


def stored_verification(
    *, status: str, latency_ms: float | None, error: str | None, secrets: Iterable[str]
) -> dict[str, Any]:
    return {
        "status": "passed" if status in {"active", "passed"} else "failed",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "latency_ms": latency_ms,
        "error": sanitize_error(error, secrets=secrets),
    }


def sanitize_error(error: str | None, *, secrets: Iterable[str]) -> str | None:
    if not error:
        return None
    result = _URL_CREDENTIALS.sub(r"\1[redacted]@", str(error))
    for secret in secrets:
        if secret:
            result = result.replace(secret, "[redacted]")
    result = " ".join(result.split())
    return result[:240]
