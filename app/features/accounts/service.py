"""Authentication, session and role use-cases for Accounts."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from .errors import AccountForbidden, AuthenticationFailed, LoginRateLimited
from .models import AccountPrincipal, AuthenticatedSession, LoginCommand
from .passwords import verify_password
from .ports import AccountSessionPort, SecurityPolicyPort
from .roles import is_manager, parse_account_role


class RateLimiter:
    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._records: dict[str, list[float]] = {}

    def _key(self, client_key: str, account_id: str) -> str:
        return f"{client_key}:{account_id}"

    def is_limited(self, client_key: str, account_id: str) -> bool:
        key = self._key(client_key, account_id)
        cutoff = time.time() - self._window_seconds
        timestamps = [value for value in self._records.get(key, []) if value > cutoff]
        self._records[key] = timestamps
        return len(timestamps) >= self._max_attempts

    def record_failure(self, client_key: str, account_id: str) -> None:
        self._records.setdefault(self._key(client_key, account_id), []).append(
            time.time()
        )

    def clear(self, client_key: str, account_id: str) -> None:
        self._records.pop(self._key(client_key, account_id), None)


class AccountsService:
    """Public facade for the existing authentication/session capability."""

    def __init__(
        self,
        sessions: AccountSessionPort,
        security_policy: SecurityPolicyPort,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._sessions = sessions
        self._security_policy = security_policy
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._rate_limiters: dict[tuple[int, int], RateLimiter] = {}

    def login(self, command: LoginCommand) -> AuthenticatedSession:
        policy = self._security_policy.load()
        limiter = self._rate_limiter(policy.max_login_attempts, policy.login_window_seconds)
        if limiter.is_limited(command.client_key, command.account_id):
            raise LoginRateLimited

        credentials = self._sessions.find_credentials(command.account_id)
        if credentials is None or not verify_password(
            command.password, credentials.password_hash
        ):
            limiter.record_failure(command.client_key, command.account_id)
            raise AuthenticationFailed

        limiter.clear(command.client_key, command.account_id)
        principal = AccountPrincipal(
            user_id=credentials.user_id,
            account_id=credentials.account_id,
            role=parse_account_role(credentials.role),
            default_landing_page=credentials.default_landing_page,
        )
        token = self._sessions.issue_session(
            principal.user_id,
            self._now() + timedelta(seconds=policy.session_ttl_seconds),
        )
        return AuthenticatedSession(
            principal=principal,
            display_name=credentials.display_name,
            session_token=token,
            ttl_seconds=policy.session_ttl_seconds,
        )

    def authenticate_session(self, token: str) -> AccountPrincipal | None:
        return self._sessions.find_session(token, self._now())

    def create_session(self, user_id: int) -> str:
        policy = self._security_policy.load()
        return self._sessions.issue_session(
            user_id, self._now() + timedelta(seconds=policy.session_ttl_seconds)
        )

    def logout(self, token: str) -> None:
        self._sessions.revoke_session(token, self._now())

    def session_ttl_seconds(self) -> int:
        return self._security_policy.load().session_ttl_seconds

    def require_owner(self, principal: AccountPrincipal) -> AccountPrincipal:
        if principal.role != "owner":
            raise AccountForbidden("需要 Owner 权限")
        return principal

    def require_manager(self, principal: AccountPrincipal) -> AccountPrincipal:
        if not is_manager(principal.role):
            raise AccountForbidden("需要 Owner 或 Admin 权限")
        return principal

    def invalidate_security_cache(self) -> None:
        self._rate_limiters.clear()

    def _rate_limiter(self, max_attempts: int, window_seconds: int) -> RateLimiter:
        key = (max_attempts, window_seconds)
        limiter = self._rate_limiters.get(key)
        if limiter is None:
            limiter = RateLimiter(max_attempts, window_seconds)
            self._rate_limiters[key] = limiter
        return limiter


__all__ = ("AccountsService", "RateLimiter")
