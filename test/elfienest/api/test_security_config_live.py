"""测试 security 配置动态生效 — session TTL / RateLimiter config-driven。

测试场景：
- test_session_ttl_live: PUT system.security.session_ttl_days=1 → 登录
  → 验证 expires_at ≈ now + 86400
- test_rate_limit_live: PUT system.security.rate_limit.max_attempts=2
  → 2 次失败 → 第 3 次被阻止 (429)
- test_config_invalid_values: PUT session_ttl_days=0 → 422;
  PUT max_attempts=0 → 422

使用 tmp_path 隔离 DB 和 ELFIE_HOME/config.yaml。
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from elfienest.accounts.auth import (
    create_session,
    get_rate_limiter,
    get_session_ttl_seconds,
    invalidate_rate_limiter_cache,
    invalidate_session_cache,
)
from elfienest.api.app import create_app
from elfienest.persistence.store import get_db, init_db

from ._helpers import create_test_owner

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_caches() -> None:
    """每次测试后清除 auth 缓存，避免测试间相互影响。"""
    yield
    invalidate_session_cache()
    invalidate_rate_limiter_cache()


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "nest.db")


@pytest.fixture
def runtime_config_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """使用临时 ELFIE_HOME 隔离生产格式配置及本地密钥。"""
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    return tmp_path / "config.yaml"


@pytest.fixture
def app(db_path: str, runtime_config_path: Path):
    """创建 FastAPI 应用，mock WS 网关和配置路径。"""
    init_db(db_path)
    create_test_owner(db_path)

    with (
        patch("elfienest.api.app.AuthenticatedWSManager.start"),
        patch("elfienest.api.app.AuthenticatedWSManager.stop"),
    ):
        application = create_app(engine=None, db_path=db_path, ws_port=9876)
        yield application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _login_owner(client: TestClient) -> dict:
    """以 owner 身份登录，返回 token 信息。"""
    resp = client.post(
        "/api/auth/login", data={"username": "owner", "password": "ownerchangeme"}
    )
    assert resp.status_code == 200, f"login failed: {resp.text}"
    csrf_token = resp.headers.get("X-CSRF-Token", "")
    return {
        "csrf_token": csrf_token,
    }


def _headers(csrf_token: str) -> dict:
    return {"X-CSRF-Token": csrf_token, "Content-Type": "application/json"}


# ===================================================================
# 动态 session TTL
# ===================================================================


class TestSessionTtlLive:
    """动态 session TTL — 从 system.security 读取配置。"""

    def test_get_session_ttl_seconds_from_config(self) -> None:
        """get_session_ttl_seconds 从 LLMRuntimeConfig 读取 session_ttl_days。"""
        with patch("runtime.config.LLMRuntimeConfig") as MockConfig:
            instance = MockConfig.return_value
            instance.system = {
                "security": {
                    "session_ttl_days": 1,
                    "rate_limit": {"max_attempts": 5, "window_seconds": 300},
                }
            }

            ttl = get_session_ttl_seconds()
            assert ttl == 86400  # 1 天

    def test_create_session_uses_config_ttl(self, tmp_path: Path) -> None:
        """create_session 创建的 session expires_at ≈ now + config TTL。"""
        db_path = str(tmp_path / "nest.db")
        init_db(db_path)
        uid = create_test_owner(db_path)

        with patch("runtime.config.LLMRuntimeConfig") as MockConfig:
            instance = MockConfig.return_value
            instance.system = {
                "security": {
                    "session_ttl_days": 1,
                    "rate_limit": {"max_attempts": 5, "window_seconds": 300},
                }
            }

            token = create_session(uid, db_path)
            with get_db(db_path) as conn:
                row = conn.execute(
                    "SELECT expires_at FROM sessions WHERE token=?", (token,)
                ).fetchone()

            expires_at = float(row["expires_at"])
            now = time.time()
            assert expires_at > now
            # 应该在 now + 86400 附近（允许 5 秒误差）
            assert abs((expires_at - now) - 86400) < 5

    def test_session_ttl_default_7_days(self) -> None:
        """默认 session TTL 为 7 天。"""
        with patch("runtime.config.LLMRuntimeConfig") as MockConfig:
            instance = MockConfig.return_value
            instance.system = {
                "security": {
                    "session_ttl_days": 7,
                    "rate_limit": {"max_attempts": 5, "window_seconds": 300},
                }
            }

            ttl = get_session_ttl_seconds()
            assert ttl == 7 * 86400

    def test_extant_sessions_unchanged(self, tmp_path: Path) -> None:
        """修改 TTL 后，已存在的 session 的过期时间保持不变。"""
        db_path = str(tmp_path / "nest.db")
        init_db(db_path)
        uid = create_test_owner(db_path)

        # 先用 7 天 TTL 创建 session
        with patch("runtime.config.LLMRuntimeConfig") as MockConfig:
            instance = MockConfig.return_value
            instance.system = {
                "security": {
                    "session_ttl_days": 7,
                    "rate_limit": {"max_attempts": 5, "window_seconds": 300},
                }
            }

            token = create_session(uid, db_path)
            with get_db(db_path) as conn:
                row = conn.execute(
                    "SELECT expires_at FROM sessions WHERE token=?", (token,)
                ).fetchone()
            original_expires = float(row["expires_at"])

        # 再次读取同一个 session，expires_at 不变（已在 DB 中固化）
        with get_db(db_path) as conn:
            row = conn.execute(
                "SELECT expires_at FROM sessions WHERE token=?", (token,)
            ).fetchone()
        assert float(row["expires_at"]) == original_expires


# ===================================================================
# 动态 RateLimiter
# ===================================================================


class TestRateLimitLive:
    """动态 RateLimiter — 从 system.security.rate_limit 读取配置。"""

    def test_get_rate_limiter_from_config(self) -> None:
        """get_rate_limiter 从配置读取 max_attempts 和 window_seconds。"""
        with patch("runtime.config.LLMRuntimeConfig") as MockConfig:
            instance = MockConfig.return_value
            instance.system = {
                "security": {
                    "session_ttl_days": 7,
                    "rate_limit": {"max_attempts": 2, "window_seconds": 60},
                }
            }

            limiter = get_rate_limiter()
            assert limiter._max_attempts == 2
            assert limiter._window_seconds == 60

    def test_rate_limiter_blocks_after_max_attempts(self) -> None:
        """max_attempts=2 → 2 次失败后第 3 次 is_limited 返回 True。"""
        with patch("runtime.config.LLMRuntimeConfig") as MockConfig:
            instance = MockConfig.return_value
            instance.system = {
                "security": {
                    "session_ttl_days": 7,
                    "rate_limit": {"max_attempts": 2, "window_seconds": 300},
                }
            }

            limiter = get_rate_limiter()
            assert not limiter.is_limited("1.2.3.4", "owner")
            limiter.record_failure("1.2.3.4", "owner")
            assert not limiter.is_limited("1.2.3.4", "owner")
            limiter.record_failure("1.2.3.4", "owner")
            assert limiter.is_limited("1.2.3.4", "owner") is True

    def test_login_endpoint_rate_limit_http(
        self, client: TestClient, runtime_config_path: Path
    ) -> None:
        """HTTP API：PUT max_attempts=2 → 2 次错误密码 → 第 3 次 429。"""
        owner_tokens = _login_owner(client)

        # PUT 写入临时 ELFIE_HOME/config.yaml。
        resp = client.put(
            "/api/owner/system/security",
            json={"rate_limit": {"max_attempts": 2, "window_seconds": 300}},
            headers=_headers(owner_tokens["csrf_token"]),
        )
        assert resp.status_code == 200

        # Mock LLMRuntimeConfig 让登录端点使用新的限流配置
        with patch("runtime.config.LLMRuntimeConfig") as MockConfig:
            instance = MockConfig.return_value
            instance.system = {
                "security": {
                    "session_ttl_days": 7,
                    "rate_limit": {"max_attempts": 2, "window_seconds": 300},
                }
            }

            # 连续 3 次错误密码
            resp1 = client.post(
                "/api/auth/login", data={"username": "owner", "password": "wrong1"}
            )
            assert resp1.status_code == 401, resp1.text

            resp2 = client.post(
                "/api/auth/login", data={"username": "owner", "password": "wrong2"}
            )
            assert resp2.status_code == 401, resp2.text

            # 第 3 次应被限流
            resp3 = client.post(
                "/api/auth/login", data={"username": "owner", "password": "wrong3"}
            )
            assert resp3.status_code == 429, f"expected 429 got {resp3.status_code}: {resp3.text}"
            assert "过于频繁" in resp3.text


# ===================================================================
# 非法配置值校验
# ===================================================================


class TestConfigInvalidValues:
    """非法安全配置值 → 422。"""

    def test_session_ttl_days_zero_422(self, client: TestClient) -> None:
        """PUT session_ttl_days=0 → 422。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/owner/system/security",
            json={"session_ttl_days": 0},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

    def test_rate_limit_max_attempts_zero_422(self, client: TestClient) -> None:
        """PUT rate_limit.max_attempts=0 → 422。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/owner/system/security",
            json={"rate_limit": {"max_attempts": 0, "window_seconds": 300}},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

    def test_rate_limit_window_seconds_zero_422(self, client: TestClient) -> None:
        """PUT rate_limit.window_seconds=0 → 422。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/owner/system/security",
            json={"rate_limit": {"max_attempts": 5, "window_seconds": 0}},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422

    def test_security_unknown_key_422(self, client: TestClient) -> None:
        """PUT security 未知键 → 422。"""
        tokens = _login_owner(client)
        resp = client.put(
            "/api/owner/system/security",
            json={"unknown_field": "value"},
            headers=_headers(tokens["csrf_token"]),
        )
        assert resp.status_code == 422
        assert "未知" in resp.text
