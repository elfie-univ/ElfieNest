from pathlib import Path

from app.features.accounts.auth import (
    get_rate_limiter,
    get_session_ttl_seconds,
    invalidate_rate_limiter_cache,
    invalidate_session_cache,
)
from app.features.configuration.runtime_store import write_runtime_config


def test_database_scoped_auth_reads_final_runtime_config(tmp_path: Path) -> None:
    # Given: auth settings stored only at the final selected-root path.
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
    invalidate_session_cache()
    invalidate_rate_limiter_cache()

    # When: auth resolves configuration from the database-selected root.
    ttl_seconds = get_session_ttl_seconds(str(tmp_path / "nest.db"))
    limiter = get_rate_limiter(str(tmp_path / "nest.db"))

    # Then: no retired root-level config path is consulted.
    assert ttl_seconds == 5 * 86_400
    limiter.record_failure("127.0.0.1", "owner")
    limiter.record_failure("127.0.0.1", "owner")
    assert limiter.is_limited("127.0.0.1", "owner") is True
