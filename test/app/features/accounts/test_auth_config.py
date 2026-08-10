"""Typed security policy adapter tests."""

from pathlib import Path

from app.features.configuration.runtime_store import write_runtime_config
from infrastructure.platform import RuntimeSecurityPolicyAdapter


def test_runtime_security_policy_reads_selected_product_root(tmp_path: Path) -> None:
    config_path = tmp_path / "configs" / "runtime.yaml"
    write_runtime_config(
        config_path,
        {
            "system": {
                "security": {
                    "session_ttl_days": 5,
                    "rate_limit": {"max_attempts": 2, "window_seconds": 45},
                }
            }
        },
    )

    policy = RuntimeSecurityPolicyAdapter(config_path).load()

    assert policy.session_ttl_seconds == 5 * 86_400
    assert policy.max_login_attempts == 2
    assert policy.login_window_seconds == 45
