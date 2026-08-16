from __future__ import annotations

import json

import httpx
import pytest

from app.features.communication.telegram_ports import TelegramBotTokenRejected
from infrastructure.communication.telegram.client import (
    TelegramBotApiClient,
    TelegramBotInspector,
)
from infrastructure.communication.telegram.mapper import (
    map_private_update,
    pairing_code,
)


def _transport(responses: dict[str, dict[str, object]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        method = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, json=responses[method])

    return httpx.MockTransport(handler)


def test_inspector_validates_bot_and_detects_webhook_without_exposing_token() -> None:
    transport = _transport(
        {
            "getMe": {
                "ok": True,
                "result": {
                    "id": 991,
                    "is_bot": True,
                    "first_name": "星星",
                    "username": "elfienest_star_bot",
                },
            },
            "getWebhookInfo": {
                "ok": True,
                "result": {"url": "https://example.invalid/hook"},
            },
        }
    )
    inspector = TelegramBotInspector(
        lambda token: TelegramBotApiClient(token, transport=transport)
    )

    result = inspector.inspect_bot("991:super-secret")

    assert result.bot_id == "991"
    assert result.username == "elfienest_star_bot"
    assert result.webhook_url == "https://example.invalid/hook"
    assert "super-secret" not in repr(result)


def test_invalid_token_raises_only_sanitized_error() -> None:
    transport = _transport(
        {"getMe": {"ok": False, "error_code": 401, "description": "Unauthorized"}}
    )
    client = TelegramBotApiClient("991:super-secret", transport=transport)

    with pytest.raises(TelegramBotTokenRejected) as captured:
        client.get_me()

    assert "super-secret" not in str(captured.value)


def test_get_updates_uses_positive_long_poll_and_send_message_returns_id() -> None:
    requests: list[tuple[str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        method = request.url.path.rsplit("/", 1)[-1]
        requests.append((method, payload))
        if method == "getUpdates":
            return httpx.Response(200, json={"ok": True, "result": []})
        return httpx.Response(
            200,
            json={"ok": True, "result": {"message_id": 17, "date": 1}},
        )

    client = TelegramBotApiClient(
        "991:super-secret", transport=httpx.MockTransport(handler)
    )

    assert client.get_updates(offset=43, timeout_seconds=5) == ()
    sent = client.send_message("1701", "你好")

    assert requests == [
        (
            "getUpdates",
            {
                "allowed_updates": ["message"],
                "limit": 100,
                "offset": 43,
                "timeout": 5,
            },
        ),
        ("sendMessage", {"chat_id": "1701", "text": "你好"}),
    ]
    assert sent.message_id == 17


def test_mapper_accepts_only_typed_message_shape_and_extracts_start_code() -> None:
    update = map_private_update(
        {
            "update_id": 42,
            "message": {
                "message_id": 9,
                "chat": {"id": 1701, "type": "private"},
                "from": {
                    "id": 701,
                    "is_bot": False,
                    "first_name": "七号",
                    "last_name": "主人",
                    "username": "owner_seven",
                },
                "text": "/start abc_DEF-123",
            },
        }
    )

    assert update is not None
    assert update.display_name == "七号 主人"
    assert update.telegram_user_id == "701"
    assert pairing_code(update.text, "elfienest_star_bot") == "abc_DEF-123"
    assert pairing_code("/start@elfienest_star_bot abc", "elfienest_star_bot") == "abc"
    assert pairing_code("/start@another_bot abc", "elfienest_star_bot") is None
    assert map_private_update({"update_id": True}) is None
