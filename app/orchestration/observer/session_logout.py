"""Logout workflow that revokes both product and Observer sessions."""

from __future__ import annotations

from app.features.accounts import AccountsService

from .service import ObserverFacade, session_token_fingerprint


class SessionLogoutWorkflow:
    """Coordinate the existing two revocations behind one inbound boundary."""

    def __init__(self, accounts: AccountsService, observer: ObserverFacade) -> None:
        self._accounts = accounts
        self._observer = observer

    def logout(self, token: str) -> None:
        self._observer.revoke_session(session_token_fingerprint(token))
        self._accounts.logout(token)


__all__ = ("SessionLogoutWorkflow",)
