"""Typed runtime.yaml reader for the Accounts security-policy Port."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from ai_runtime.config import DEFAULT_SYSTEM_SETTINGS, deep_update
from ai_runtime.storage.config_store import read_yaml_mapping
from app.features.accounts import SecurityPolicy


class RuntimeSecurityPolicyAdapter:
    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path

    def load(self) -> SecurityPolicy:
        security: dict[str, Any] = copy.deepcopy(
            DEFAULT_SYSTEM_SETTINGS.get("security", {})
        )
        saved = read_yaml_mapping(self._config_path)
        saved_security = saved.get("system", {}).get("security", {})
        if isinstance(saved_security, dict):
            deep_update(security, saved_security)
        rate_limit = security.get("rate_limit", {})
        return SecurityPolicy(
            session_ttl_seconds=int(security.get("session_ttl_days", 7)) * 86_400,
            max_login_attempts=int(rate_limit.get("max_attempts", 5)),
            login_window_seconds=int(rate_limit.get("window_seconds", 300)),
        )


__all__ = ("RuntimeSecurityPolicyAdapter",)
