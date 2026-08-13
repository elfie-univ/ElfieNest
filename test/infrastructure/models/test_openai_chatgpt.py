from __future__ import annotations

import asyncio
import base64
import json
import urllib.error
from unittest.mock import Mock, patch

from infrastructure.models.oauth_credentials import OAuthToken
from infrastructure.models.providers.dispatch import call_codex_responses_api
from infrastructure.models.providers.openai_chatgpt import OpenAIChatGptOAuthAdapter


class MemoryCredentials:
    def __init__(self) -> None:
        self.items: dict[str, OAuthToken] = {}

    def load(self, credential_ref: str) -> OAuthToken | None:
        return self.items.get(credential_ref)

    def save(self, token: OAuthToken) -> None:
        self.items[token.credential_ref] = token

    def delete(self, credential_ref: str) -> bool:
        return self.items.pop(credential_ref, None) is not None

    def has(self, credential_ref: str) -> bool:
        return credential_ref in self.items


def _jwt(claims: dict[str, object]) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"header.{encoded}.signature"


def test_device_authorization_persists_refreshable_chatgpt_token() -> None:
    credentials = MemoryCredentials()
    responses = iter(
        (
            {"device_auth_id": "device-1", "user_code": "ABCD-1234", "interval": 5},
            {"authorization_code": "code-1", "code_verifier": "verifier-1"},
            {
                "access_token": "access-secret",
                "refresh_token": "refresh-secret",
                "id_token": _jwt({"chatgpt_account_id": "account-1"}),
                "expires_in": 3600,
            },
        )
    )
    adapter = OpenAIChatGptOAuthAdapter(
        credentials,
        request_json=lambda _request, _timeout: next(responses),
    )

    started = asyncio.run(adapter.start_login("openai_chatgpt"))
    completed = asyncio.run(adapter.poll_login(started.login_id))

    assert started.authorization_url == "https://auth.openai.com/codex/device"
    assert started.poll_interval_seconds == 8
    assert completed.state == "completed"
    saved = credentials.load(completed.credential_ref)
    assert saved is not None
    assert saved.access_token == "access-secret"
    assert saved.refresh_token == "refresh-secret"
    assert saved.account_id == "account-1"
    assert "access-secret" not in repr(saved)


def test_device_authorization_keeps_403_as_pending() -> None:
    credentials = MemoryCredentials()

    def request_json(request, _timeout):
        if request.full_url.endswith("/usercode"):
            return {"device_auth_id": "device-1", "user_code": "CODE", "interval": 1}
        raise urllib.error.HTTPError(request.full_url, 403, "pending", {}, None)

    adapter = OpenAIChatGptOAuthAdapter(credentials, request_json=request_json)
    started = asyncio.run(adapter.start_login("openai_chatgpt"))

    status = asyncio.run(adapter.poll_login(started.login_id))

    assert status.state == "pending"
    assert credentials.items == {}


def test_codex_responses_transport_uses_account_header_and_parses_sse() -> None:
    response = Mock()
    response.read.return_value = (
        b'data: {"type":"response.output_text.delta","delta":"Hello"}\n\n'
        b'data: {"type":"response.output_text.delta","delta":"!"}\n\n'
        b'data: {"type":"response.completed","response":{"usage":'
        b'{"input_tokens":4,"output_tokens":2}}}\n\n'
        b"data: [DONE]\n\n"
    )
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)

    with patch(
        "infrastructure.models.providers.dispatch.open_provider_request",
        return_value=response,
    ) as opener:
        text, usage = call_codex_responses_api(
            "https://chatgpt.com/backend-api/codex",
            "access-secret",
            "gpt-5.4-mini",
            [
                {"role": "system", "content": "Be concise"},
                {"role": "user", "content": "Hi"},
            ],
            0.7,
            100,
            account_id="account-1",
        )

    request = opener.call_args.args[0]
    payload = json.loads(request.data)
    assert request.full_url == "https://chatgpt.com/backend-api/codex/responses"
    assert request.headers["Authorization"] == "Bearer access-secret"
    assert request.headers["Chatgpt-account-id"] == "account-1"
    assert payload["instructions"] == "Be concise"
    assert payload["stream"] is True
    assert text == "Hello!"
    assert usage == {"prompt_tokens": 4, "completion_tokens": 2}


def test_codex_responses_transport_translates_and_returns_tool_arguments() -> None:
    response = Mock()
    response.read.return_value = (
        b'data: {"type":"response.function_call_arguments.delta",'
        b'"delta":"{\\"answer\\":42}"}\n\n'
        b'data: {"type":"response.completed","response":{}}\n\n'
    )
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)

    with patch(
        "infrastructure.models.providers.dispatch.open_provider_request",
        return_value=response,
    ) as opener:
        text, _usage = call_codex_responses_api(
            "https://chatgpt.com/backend-api/codex",
            "access-secret",
            "gpt-5.4-mini",
            [{"role": "user", "content": "Answer"}],
            0.7,
            100,
            request_options={
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "answer",
                            "parameters": {"type": "object"},
                        },
                    }
                ],
                "tool_choice": {
                    "type": "function",
                    "function": {"name": "answer"},
                },
            },
        )

    payload = json.loads(opener.call_args.args[0].data)
    assert payload["tools"][0]["name"] == "answer"
    assert payload["tool_choice"] == {"type": "function", "name": "answer"}
    assert text == '{"answer":42}'
