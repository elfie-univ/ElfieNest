"""Map untrusted Discord Gateway JSON into the narrow private-message DTO."""

from __future__ import annotations

from typing import Mapping, Optional

from app.features.communication.discord_port_models import DiscordPrivateUpdate


def map_message_create(raw: Mapping[str, object]) -> Optional[DiscordPrivateUpdate]:
    message_id = _snowflake(raw.get("id"))
    channel_id = _snowflake(raw.get("channel_id"))
    author = raw.get("author")
    if message_id is None or channel_id is None or not isinstance(author, dict):
        return None
    user_id = _snowflake(author.get("id"))
    if user_id is None:
        return None
    username = author.get("username")
    global_name = author.get("global_name")
    display_name = (
        global_name
        if isinstance(global_name, str) and global_name.strip()
        else username
        if isinstance(username, str) and username.strip()
        else user_id
    )
    guild_id = _snowflake(raw.get("guild_id"))
    content = raw.get("content")
    return DiscordPrivateUpdate(
        message_id=message_id,
        channel_id=channel_id,
        discord_user_id=user_id,
        discord_username=username if isinstance(username, str) and username else None,
        display_name=display_name,
        text=content if isinstance(content, str) else None,
        is_dm=guild_id is None,
        sender_is_bot=author.get("bot") is True,
        guild_id=guild_id,
    )


def _snowflake(value: object) -> Optional[str]:
    if isinstance(value, str) and value.isdigit():
        return value
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return str(value)
    return None


__all__ = ("map_message_create",)
