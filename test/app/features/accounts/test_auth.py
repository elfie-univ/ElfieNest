"""Focused Accounts facade tests without HTTP or concrete persistence."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from app.features.accounts import (
    AccountConflict,
    AccountCredentials,
    AccountForbidden,
    AccountPersistenceConflict,
    AccountPrincipal,
    AccountsService,
    AuthenticationFailed,
    LoginCommand,
    LoginRateLimited,
    OwnerAccountRecord,
    RateLimiter,
    RegisterAccountCommand,
    RegistrationUnavailable,
    SecurityPolicy,
    hash_password,
    parse_account_role,
    verify_password,
)


class MemoryAccounts:
    def __init__(self, *, owner_available: bool = True) -> None:
        self.credentials = AccountCredentials(
            user_id=1,
            account_id="owner",
            password_hash=hash_password("owner-secret"),
            role="owner",
            display_name="Owner",
            default_landing_page="manage",
        )
        self._credentials = {self.credentials.account_id: self.credentials}
        self._next_user_id = 2
        self._owner_available = owner_available
        self.sessions: dict[str, AccountPrincipal] = {}
        self.revoked: list[str] = []

    def find_credentials(self, account_id: str) -> AccountCredentials | None:
        return self._credentials.get(account_id)

    def issue_session(self, user_id: int, expires_at: datetime) -> str:
        assert expires_at > datetime.now(timezone.utc)
        credentials = next(
            item for item in self._credentials.values() if item.user_id == user_id
        )
        principal = AccountPrincipal(
            credentials.user_id,
            credentials.account_id,
            parse_account_role(credentials.role),
            credentials.default_landing_page,
        )
        self.sessions["session-token"] = principal
        return "session-token"

    def find_session(self, raw_token: str, now: datetime) -> AccountPrincipal | None:
        return self.sessions.get(raw_token)

    def revoke_session(self, raw_token: str, revoked_at: datetime) -> None:
        self.sessions.pop(raw_token, None)
        self.revoked.append(raw_token)

    def create_user_account(
        self,
        *,
        account_id: str,
        display_name: str,
        password_hash: str,
    ) -> int:
        if account_id in self._credentials:
            raise AccountPersistenceConflict("duplicate account")
        user_id = self._next_user_id
        self._next_user_id += 1
        self._credentials[account_id] = AccountCredentials(
            user_id=user_id,
            account_id=account_id,
            password_hash=password_hash,
            role="user",
            display_name=display_name,
            default_landing_page="chat",
        )
        return user_id

    def find_owner_account(self) -> OwnerAccountRecord | None:
        if not self._owner_available:
            return None
        return OwnerAccountRecord(
            user_id=1,
            account_id="owner",
            display_name="Owner",
            created_at="2026-08-01T00:00:00+00:00",
            updated_at="2026-08-01T00:00:00+00:00",
        )


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


def _registration_service(
    *, owner_available: bool = True
) -> tuple[AccountsService, MemoryAccounts]:
    adapter = MemoryAccounts(owner_available=owner_available)
    return AccountsService(
        adapter,
        StaticSecurityPolicy(),
        management=adapter,
    ), adapter


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


def test_registration_creates_a_user_and_issues_a_session_without_relogin() -> None:
    service, adapter = _registration_service()

    result = service.register(
        RegisterAccountCommand(
            account_id=" member01 ",
            display_name=" Member One ",
            password="member-secret",
        )
    )

    assert result.principal == AccountPrincipal(2, "member01", "user", "chat")
    assert result.display_name == "Member One"
    assert result.session_token == "session-token"
    assert (
        adapter.find_session(result.session_token, datetime.now(timezone.utc))
        == result.principal
    )


def test_registration_rejects_duplicate_account_ids() -> None:
    service, _ = _registration_service()
    command = RegisterAccountCommand("member01", "Member One", "member-secret")

    service.register(command)
    with pytest.raises(AccountConflict):
        service.register(command)


def test_registration_waits_for_first_owner_setup() -> None:
    service, _ = _registration_service(owner_available=False)

    with pytest.raises(RegistrationUnavailable):
        service.register(
            RegisterAccountCommand("member01", "Member One", "member-secret")
        )


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
