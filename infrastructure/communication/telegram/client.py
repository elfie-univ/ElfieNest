"""Sanitized synchronous Telegram Bot API client used by managed workers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from io import BytesIO
from typing import Callable, Mapping, Optional, Tuple

import httpx
from PIL import Image

from app.features.communication.telegram_port_models import TelegramBotInspection
from app.features.communication.telegram_ports import (
    TelegramBotTokenRejected,
    TelegramBotTransportError,
)


@dataclass(frozen=True)
class TelegramSentMessage:
    message_id: int


class TelegramBotApiClient:
    """Call only the P0 methods and never expose the credential in errors."""

    def __init__(
        self,
        bot_token: str,
        *,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        if not bot_token:
            raise ValueError("Telegram bot token is required")
        self._client = httpx.Client(
            base_url=f"https://api.telegram.org/bot{bot_token}/",
            transport=transport,
            headers={"User-Agent": "ElfieNest/0.1 TelegramAdapter"},
        )

    def close(self) -> None:
        self._client.close()

    def get_me(self) -> Mapping[str, object]:
        result = self._call("getMe", {})
        if not isinstance(result, dict) or result.get("is_bot") is not True:
            raise TelegramBotTokenRejected("Telegram rejected the bot credential")
        return result

    def get_webhook_url(self) -> str:
        result = self._call("getWebhookInfo", {})
        if not isinstance(result, dict):
            raise TelegramBotTransportError("Telegram returned an invalid response")
        value = result.get("url")
        return value if isinstance(value, str) else ""

    def get_updates(
        self,
        *,
        offset: Optional[int],
        timeout_seconds: int = 5,
    ) -> Tuple[Mapping[str, object], ...]:
        timeout = max(1, min(30, int(timeout_seconds)))
        payload: dict[str, object] = {
            "allowed_updates": ["message"],
            "limit": 100,
            "timeout": timeout,
        }
        if offset is not None:
            payload["offset"] = offset
        result = self._call("getUpdates", payload, read_timeout=timeout + 5)
        if not isinstance(result, list):
            raise TelegramBotTransportError("Telegram returned an invalid response")
        return tuple(item for item in result if isinstance(item, dict))

    def send_message(self, chat_id: str, text: str) -> TelegramSentMessage:
        result = self._call("sendMessage", {"chat_id": chat_id, "text": text})
        if not isinstance(result, dict):
            raise TelegramBotTransportError("Telegram returned an invalid response")
        message_id = result.get("message_id")
        if not isinstance(message_id, int) or isinstance(message_id, bool):
            raise TelegramBotTransportError("Telegram returned an invalid response")
        return TelegramSentMessage(message_id=message_id)

    def set_profile_photo(self, content: bytes, media_type: str) -> None:
        """Set the bot's static profile photo from the current Elfie headshot."""
        if not content:
            raise ValueError("Telegram profile photo cannot be empty")
        if not media_type.startswith("image/"):
            raise ValueError("Telegram profile photo must be an image")
        jpeg = _as_jpeg(content)
        try:
            response = self._client.post(
                "setMyProfilePhoto",
                data={
                    "photo": json.dumps(
                        {"type": "static", "photo": "attach://profile_photo"}
                    )
                },
                files={"profile_photo": ("elfie-avatar.jpg", jpeg, "image/jpeg")},
                timeout=httpx.Timeout(
                    connect=5.0,
                    read=15.0,
                    write=10.0,
                    pool=5.0,
                ),
            )
            document = response.json()
        except (httpx.HTTPError, ValueError):
            raise TelegramBotTransportError("Telegram request failed") from None
        if not isinstance(document, dict):
            raise TelegramBotTransportError("Telegram returned an invalid response")
        if document.get("ok") is not True:
            code = document.get("error_code")
            if response.status_code in {401, 404} or code in {401, 404}:
                raise TelegramBotTokenRejected(
                    "Telegram rejected the bot credential"
                ) from None
            raise TelegramBotTransportError("Telegram request failed") from None
        if document.get("result") is not True:
            raise TelegramBotTransportError("Telegram returned an invalid response")

    def _call(
        self,
        method: str,
        payload: Mapping[str, object],
        *,
        read_timeout: int = 10,
    ) -> object:
        try:
            response = self._client.post(
                method,
                json=dict(payload),
                timeout=httpx.Timeout(
                    connect=5.0,
                    read=float(read_timeout),
                    write=5.0,
                    pool=5.0,
                ),
            )
            document = response.json()
        except (httpx.HTTPError, ValueError):
            raise TelegramBotTransportError("Telegram request failed") from None
        if not isinstance(document, dict):
            raise TelegramBotTransportError("Telegram returned an invalid response")
        if document.get("ok") is not True:
            code = document.get("error_code")
            if response.status_code in {401, 404} or code in {401, 404}:
                raise TelegramBotTokenRejected(
                    "Telegram rejected the bot credential"
                ) from None
            raise TelegramBotTransportError("Telegram request failed") from None
        return document.get("result")


class TelegramBotInspector:
    """One-shot token validation used before any credential is persisted."""

    def __init__(
        self,
        client_factory: Optional[Callable[[str], TelegramBotApiClient]] = None,
    ) -> None:
        self._client_factory = client_factory or TelegramBotApiClient

    def inspect_bot(self, bot_token: str) -> TelegramBotInspection:
        client = self._client_factory(bot_token)
        try:
            bot = client.get_me()
            webhook_url = client.get_webhook_url()
        finally:
            client.close()
        bot_id = bot.get("id")
        username = bot.get("username")
        display_name = bot.get("first_name")
        if (
            not isinstance(bot_id, int)
            or isinstance(bot_id, bool)
            or not isinstance(username, str)
            or not username
            or not isinstance(display_name, str)
        ):
            raise TelegramBotTransportError("Telegram returned an invalid bot identity")
        return TelegramBotInspection(
            bot_id=str(bot_id),
            username=username,
            display_name=display_name,
            webhook_url=webhook_url,
        )


class TelegramBotAvatarUpdater:
    """One-shot profile update adapter used during account configuration."""

    def __init__(
        self,
        client_factory: Optional[Callable[[str], TelegramBotApiClient]] = None,
    ) -> None:
        self._client_factory = client_factory or TelegramBotApiClient

    def sync_avatar(self, bot_token: str, content: bytes, media_type: str) -> None:
        client = self._client_factory(bot_token)
        try:
            client.set_profile_photo(content, media_type)
        finally:
            client.close()


def _as_jpeg(content: bytes) -> bytes:
    try:
        with Image.open(BytesIO(content)) as source:
            source.load()
            if source.mode in {"RGBA", "LA", "P"} or "transparency" in source.info:
                rgba = source.convert("RGBA")
                image = Image.new("RGB", rgba.size, (255, 255, 255))
                image.paste(rgba, mask=rgba.getchannel("A"))
            else:
                image = source.convert("RGB")
            output = BytesIO()
            image.save(output, format="JPEG", quality=90, optimize=True)
            return output.getvalue()
    except (OSError, ValueError):
        raise TelegramBotTransportError("Telegram profile photo is invalid") from None


__all__ = (
    "TelegramBotApiClient",
    "TelegramBotAvatarUpdater",
    "TelegramBotInspector",
    "TelegramSentMessage",
)
