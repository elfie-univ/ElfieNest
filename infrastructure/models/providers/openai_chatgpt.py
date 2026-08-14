"""OpenCode-compatible ChatGPT device authorization for the Codex backend."""

from __future__ import annotations

import asyncio
import base64
import json
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

from app.features.configuration import (
    ProviderPortError,
    StoredProviderOAuthLoginStart,
    StoredProviderOAuthLoginStatus,
)
from infrastructure.models.oauth_credentials import OAuthCredentialPort, OAuthToken
from infrastructure.models.providers.http import (
    open_provider_request,
    read_provider_response,
)

OPENAI_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
OPENAI_AUTH_ISSUER = "https://auth.openai.com"
OPENAI_DEVICE_AUTHORIZATION_URL = f"{OPENAI_AUTH_ISSUER}/codex/device"
_DEVICE_REDIRECT_URI = f"{OPENAI_AUTH_ISSUER}/deviceauth/callback"
_MAX_LOGIN_SECONDS = 15 * 60


@dataclass(frozen=True)
class _PendingLogin:
    catalog_id: str
    device_auth_id: str
    user_code: str
    interval: int
    expires_at: datetime


RequestJson = Callable[[urllib.request.Request, float], Mapping[str, Any]]


class OpenAIChatGptOAuthAdapter:
    """Own short-lived device-login state and persist only completed tokens."""

    def __init__(
        self,
        credentials: OAuthCredentialPort,
        *,
        request_json: RequestJson | None = None,
    ) -> None:
        self._credentials = credentials
        self._request_json = request_json or _request_json
        self._pending: dict[str, _PendingLogin] = {}
        self._completed: dict[str, StoredProviderOAuthLoginStatus] = {}

    async def start_login(self, catalog_id: str) -> StoredProviderOAuthLoginStart:
        if catalog_id != "openai_chatgpt":
            raise ProviderPortError("Unsupported OAuth Provider")
        request = _json_request(
            f"{OPENAI_AUTH_ISSUER}/api/accounts/deviceauth/usercode",
            {"client_id": OPENAI_OAUTH_CLIENT_ID},
        )
        try:
            payload = await asyncio.to_thread(self._request_json, request, 15.0)
            device_auth_id = _required(payload, "device_auth_id")
            user_code = _required(payload, "user_code")
            interval = max(1, int(payload.get("interval") or 5))
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise ProviderPortError("Unable to start ChatGPT authorization") from error
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=_MAX_LOGIN_SECONDS)
        login_id = uuid.uuid4().hex
        self._prune(now)
        self._pending[login_id] = _PendingLogin(
            catalog_id, device_auth_id, user_code, interval, expires_at
        )
        return StoredProviderOAuthLoginStart(
            catalog_id=catalog_id,
            login_id=login_id,
            authorization_url=OPENAI_DEVICE_AUTHORIZATION_URL,
            user_code=user_code,
            poll_interval_seconds=interval + 3,
            expires_at=expires_at.isoformat(),
        )

    async def poll_login(self, login_id: str) -> StoredProviderOAuthLoginStatus:
        completed = self._completed.get(login_id)
        if completed is not None:
            return completed
        pending = self._pending.get(login_id)
        if pending is None:
            raise ProviderPortError("ChatGPT authorization session is missing")
        if pending.expires_at <= datetime.now(timezone.utc):
            self._pending.pop(login_id, None)
            raise ProviderPortError("ChatGPT authorization session expired")
        request = _json_request(
            f"{OPENAI_AUTH_ISSUER}/api/accounts/deviceauth/token",
            {
                "device_auth_id": pending.device_auth_id,
                "user_code": pending.user_code,
            },
        )
        try:
            authorization = await asyncio.to_thread(self._request_json, request, 15.0)
        except urllib.error.HTTPError as error:
            if error.code in {403, 404}:
                return StoredProviderOAuthLoginStatus(
                    pending.catalog_id, login_id, "pending"
                )
            raise ProviderPortError("ChatGPT authorization failed") from error
        try:
            token_request = _form_request(
                f"{OPENAI_AUTH_ISSUER}/oauth/token",
                {
                    "grant_type": "authorization_code",
                    "code": _required(authorization, "authorization_code"),
                    "redirect_uri": _DEVICE_REDIRECT_URI,
                    "client_id": OPENAI_OAUTH_CLIENT_ID,
                    "code_verifier": _required(authorization, "code_verifier"),
                },
            )
            tokens = await asyncio.to_thread(self._request_json, token_request, 15.0)
            access_token = _required(tokens, "access_token")
            credential_ref = f"oauth.openai_chatgpt.{uuid.uuid4().hex}"
            expires_at = _token_expiry(tokens)
            account_id = _chatgpt_account_id(
                str(tokens.get("id_token") or access_token)
            )
            raw_scope = str(tokens.get("scope") or "")
            self._credentials.save(
                OAuthToken(
                    credential_ref=credential_ref,
                    access_token=access_token,
                    refresh_token=str(tokens.get("refresh_token") or ""),
                    expires_at=expires_at,
                    scopes=tuple(raw_scope.split()),
                    account_id=account_id,
                    token_type=str(tokens.get("token_type") or "Bearer"),
                )
            )
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise ProviderPortError("Unable to finish ChatGPT authorization") from error
        status = StoredProviderOAuthLoginStatus(
            catalog_id=pending.catalog_id,
            login_id=login_id,
            state="completed",
            credential_ref=credential_ref,
            account_id=account_id,
            expires_at=expires_at,
        )
        self._pending.pop(login_id, None)
        self._completed[login_id] = status
        return status

    def _prune(self, now: datetime) -> None:
        self._pending = {
            key: value for key, value in self._pending.items() if value.expires_at > now
        }


def refresh_openai_chatgpt_token(
    token: OAuthToken,
    credentials: OAuthCredentialPort,
    *,
    request_json: RequestJson | None = None,
) -> OAuthToken:
    if not token.refresh_token:
        raise ProviderPortError("ChatGPT authorization cannot be refreshed")
    request = _form_request(
        f"{OPENAI_AUTH_ISSUER}/oauth/token",
        {
            "grant_type": "refresh_token",
            "refresh_token": token.refresh_token,
            "client_id": OPENAI_OAUTH_CLIENT_ID,
        },
    )
    try:
        payload = (request_json or _request_json)(request, 15.0)
        access_token = _required(payload, "access_token")
        refreshed = OAuthToken(
            credential_ref=token.credential_ref,
            access_token=access_token,
            refresh_token=str(payload.get("refresh_token") or token.refresh_token),
            expires_at=_token_expiry(payload),
            scopes=token.scopes,
            account_id=_chatgpt_account_id(str(payload.get("id_token") or access_token))
            or token.account_id,
            token_type=str(payload.get("token_type") or token.token_type),
        )
        credentials.save(refreshed)
        return refreshed
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise ProviderPortError("Unable to refresh ChatGPT authorization") from error


def _request_json(request: urllib.request.Request, timeout: float) -> Mapping[str, Any]:
    with open_provider_request(request, timeout=timeout) as response:
        payload = json.loads(
            read_provider_response(
                response, max_bytes=1024 * 1024, deadline_seconds=timeout
            ).decode("utf-8")
        )
    if not isinstance(payload, dict):
        raise ValueError("OAuth response must be an object")
    return payload


def _json_request(url: str, payload: Mapping[str, Any]) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "ElfieNest/0.1",
        },
        method="POST",
    )


def _form_request(url: str, payload: Mapping[str, str]) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        data=urllib.parse.urlencode(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "ElfieNest/0.1",
        },
        method="POST",
    )


def _required(payload: Mapping[str, Any], key: str) -> str:
    value = str(payload.get(key) or "")
    if not value:
        raise ValueError(f"OAuth response is missing {key}")
    return value


def _token_expiry(payload: Mapping[str, Any]) -> str | None:
    expires_in = payload.get("expires_in")
    if not isinstance(expires_in, (int, float)):
        return None
    return (
        datetime.now(timezone.utc) + timedelta(seconds=float(expires_in))
    ).isoformat()


def _chatgpt_account_id(token: str) -> str | None:
    try:
        middle = token.split(".")[1]
        middle += "=" * (-len(middle) % 4)
        claims = json.loads(base64.urlsafe_b64decode(middle).decode("utf-8"))
        direct = claims.get("chatgpt_account_id")
        if direct:
            return str(direct)
        auth = claims.get("https://api.openai.com/auth")
        if isinstance(auth, dict) and auth.get("chatgpt_account_id"):
            return str(auth["chatgpt_account_id"])
        organizations = claims.get("organizations")
        if isinstance(organizations, list) and organizations:
            first = organizations[0]
            if isinstance(first, dict) and first.get("id"):
                return str(first["id"])
    except (ValueError, IndexError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return None


__all__ = (
    "OPENAI_DEVICE_AUTHORIZATION_URL",
    "OpenAIChatGptOAuthAdapter",
    "refresh_openai_chatgpt_token",
)
