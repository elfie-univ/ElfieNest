"""Narrow credential boundary for refreshable Provider OAuth tokens."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class OAuthToken:
    credential_ref: str
    access_token: str = field(repr=False)
    refresh_token: str = field(default="", repr=False)
    expires_at: str | None = None
    scopes: tuple[str, ...] = ()
    account_id: str | None = None
    token_type: str = "Bearer"


class OAuthCredentialPort(Protocol):
    def load(self, credential_ref: str) -> OAuthToken | None: ...

    def save(self, token: OAuthToken) -> None: ...

    def delete(self, credential_ref: str) -> bool: ...

    def has(self, credential_ref: str) -> bool: ...


__all__ = ("OAuthCredentialPort", "OAuthToken")
