"""Focused Accounts facade tests without HTTP or concrete persistence."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from app.features.accounts import (
    AccountCredentials,
    AccountForbidden,
    AccountPrincipal,
    AccountsService,
    AuthenticationFailed,
    LoginCommand,
    LoginRateLimited,
    RateLimiter,
    SecurityPolicy,
    hash_password,
    verify_password,
)


class MemoryAccounts:
    def __init__(self) -> None:
        self.credentials = AccountCredentials(
            user_id=1,
            account_id="owner",
            password_hash=hash_password("owner-secret"),
            role="owner",
            display_name="Owner",
            default_landing_page="manage",
        )
        self.sessions: dict[str, AccountPrincipal] = {}
        self.revoked: list[str] = []

    def find_credentials(self, account_id: str) -> AccountCredentials | None:
        return self.credentials if account_id == self.credentials.account_id else None

    def issue_session(self, user_id: int, expires_at: datetime) -> str:
        assert user_id == self.credentials.user_id
        assert expires_at > datetime.now(timezone.utc)
        principal = AccountPrincipal(1, "owner", "owner", "manage")
        self.sessions["session-token"] = principal
        return "session-token"

    def find_session(
        self, raw_token: str, now: datetime
    ) -> AccountPrincipal | None:
        return self.sessions.get(raw_token)

    def revoke_session(self, raw_token: str, revoked_at: datetime) -> None:
        self.sessions.pop(raw_token, None)
        self.revoked.append(raw_token)


class StaticSecurityPolicy:
    def __init__(self, max_attempts: int = 2) -> None:
        self.max_attempts = max_attempts

    def load(self) -> SecurityPolicy:
        return SecurityPolicy(
            session_ttl_seconds=86_400,
            max_login_attempts=self.max_attempts,
            login_window_seconds=300,
        )


def _service(max_attempts: int = 2) -> tuple[AccountsService, MemoryAccounts]:
    adapter = MemoryAccounts()
    return AccountsService(adapter, StaticSecurityPolicy(max_attempts)), adapter


def test_password_hash_round_trip_and_malformed_input() -> None:
    password_hash = hash_password("test123")
    parts = password_hash.split("$")
    assert parts[0:2] == ["pbkdf2_sha256", "260000"]
    assert len(parts[2]) == 32
    assert len(parts[3]) == 64
    assert verify_password("test123", password_hash) is True
    assert verify_password("wrong", password_hash) is False
    assert verify_password("test123", "pbkdf2_sha256$bad$salt$digest") is False


def test_login_returns_strict_principal_and_session_result() -> None:
    service, adapter = _service()
    result = service.login(LoginCommand("owner", "owner-secret", "127.0.0.1"))
    assert result.principal == AccountPrincipal(1, "owner", "owner", "manage")
    assert result.display_name == "Owner"
    assert result.session_token == "session-token"
    assert result.ttl_seconds == 86_400
    assert service.authenticate_session(result.session_token) == result.principal
    assert adapter.sessions


def test_login_failure_is_rate_limited_by_client_and_account() -> None:
    service, _ = _service(max_attempts=2)
    command = LoginCommand("owner", "wrong", "127.0.0.1")
    with pytest.raises(AuthenticationFailed):
        service.login(command)
    with pytest.raises(AuthenticationFailed):
        service.login(command)
    with pytest.raises(LoginRateLimited):
        service.login(command)


def test_logout_is_idempotent() -> None:
    service, adapter = _service()
    token = service.login(
        LoginCommand("owner", "owner-secret", "127.0.0.1")
    ).session_token
    service.logout(token)
    service.logout(token)
    assert service.authenticate_session(token) is None
    assert adapter.revoked == [token, token]


def test_accounts_authorizes_manager_and_owner_roles() -> None:
    service, _ = _service()
    owner = AccountPrincipal(1, "owner", "owner", "manage")
    admin = AccountPrincipal(2, "admin", "admin", "manage")
    user = AccountPrincipal(3, "user", "user", "chat")
    assert service.require_owner(owner) is owner
    assert service.require_manager(admin) is admin
    with pytest.raises(AccountForbidden):
        service.require_owner(admin)
    with pytest.raises(AccountForbidden):
        service.require_manager(user)


def test_rate_limiter_window_and_clear() -> None:
    limiter = RateLimiter(max_attempts=2, window_seconds=0.01)
    limiter.record_failure("127.0.0.1", "owner")
    limiter.record_failure("127.0.0.1", "owner")
    assert limiter.is_limited("127.0.0.1", "owner") is True
    limiter.clear("127.0.0.1", "owner")
    assert limiter.is_limited("127.0.0.1", "owner") is False
    limiter.record_failure("127.0.0.1", "owner")
    limiter.record_failure("127.0.0.1", "owner")
    time.sleep(0.02)
    assert limiter.is_limited("127.0.0.1", "owner") is False
