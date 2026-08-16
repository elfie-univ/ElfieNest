"""Map untrusted Telegram JSON into the narrow private-message DTO."""

from __future__ import annotations

import re
from typing import Mapping, Optional

from app.features.communication.telegram_port_models import TelegramPrivateUpdate

_START = re.compile(
    r"^/start(?:@(?P<username>[A-Za-z0-9_]{1,64}))?\s+(?P<code>[A-Za-z0-9_-]{1,64})$"
)


def map_private_update(raw: Mapping[str, object]) -> Optional[TelegramPrivateUpdate]:
    update_id = _integer(raw.get("update_id"))
    message = raw.get("message")
    if update_id is None or not isinstance(message, dict):
        return None
    message_id = _integer(message.get("message_id"))
    chat = message.get("chat")
    sender = message.get("from")
    if message_id is None or not isinstance(chat, dict) or not isinstance(sender, dict):
        return None
    chat_id = _integer(chat.get("id"))
    telegram_user_id = _integer(sender.get("id"))
    chat_type = chat.get("type")
    if chat_id is None or telegram_user_id is None or not isinstance(chat_type, str):
        return None
    first_name = sender.get("first_name")
    last_name = sender.get("last_name")
    username = sender.get("username")
    text = message.get("text")
    names = [
        value.strip()
        for value in (first_name, last_name)
        if isinstance(value, str) and value.strip()
    ]
    display_name = " ".join(names) or (
        username if isinstance(username, str) and username else str(telegram_user_id)
    )
    return TelegramPrivateUpdate(
        update_id=update_id,
        message_id=message_id,
        chat_id=str(chat_id),
        chat_type=chat_type,
        telegram_user_id=str(telegram_user_id),
        telegram_username=username if isinstance(username, str) and username else None,
        display_name=display_name,
        text=text if isinstance(text, str) else None,
        sender_is_bot=sender.get("is_bot") is True,
    )


def update_identifier(raw: Mapping[str, object]) -> Optional[int]:
    return _integer(raw.get("update_id"))


def pairing_code(text: Optional[str], bot_username: str) -> Optional[str]:
    if text is None:
        return None
    match = _START.fullmatch(text.strip())
    if match is None:
        return None
    addressed = match.group("username")
    if addressed is not None and addressed.casefold() != bot_username.casefold():
        return None
    return match.group("code")


def _integer(value: object) -> Optional[int]:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


__all__ = ("map_private_update", "pairing_code", "update_identifier")
