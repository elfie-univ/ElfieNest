"""Typed runtime.yaml reader for the Accounts security-policy Port."""

from __future__ import annotations

from app.features.accounts import SecurityPolicy
from app.features.configuration import SettingsStorePort


class RuntimeSecurityPolicyAdapter:
    def __init__(self, settings: SettingsStorePort) -> None:
        self._settings = settings

    def load(self) -> SecurityPolicy:
        security = self._settings.load_security_settings()
        return SecurityPolicy(
            session_ttl_seconds=security.session_ttl_days * 86_400,
            max_login_attempts=security.rate_limit.max_attempts,
            login_window_seconds=security.rate_limit.window_seconds,
        )


__all__ = ("RuntimeSecurityPolicyAdapter",)
