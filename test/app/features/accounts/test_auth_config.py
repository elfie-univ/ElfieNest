"""Typed security policy adapter tests."""

from pathlib import Path

from app.features.configuration.settings import (
    StoredLoginRateLimit,
    StoredSecuritySettings,
)
from infrastructure.platform import RuntimeSecurityPolicyAdapter, RuntimeSettingsAdapter


def test_runtime_security_policy_reads_selected_product_root(tmp_path: Path) -> None:
    config_path = tmp_path / "configs" / "runtime.yaml"
    settings = RuntimeSettingsAdapter(config_path)
    settings.save_security_settings(
        StoredSecuritySettings(
            session_ttl_days=5,
            rate_limit=StoredLoginRateLimit(
                max_attempts=2,
                window_seconds=45,
            ),
        )
    )

    policy = RuntimeSecurityPolicyAdapter(settings).load()

    assert policy.session_ttl_seconds == 5 * 86_400
    assert policy.max_login_attempts == 2
    assert policy.login_window_seconds == 45
