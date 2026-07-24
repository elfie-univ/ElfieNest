"""HTTP 与 WebSocket 共用的精灵聊天持久化适配。"""

from __future__ import annotations

from uuid import uuid4

from app.infrastructure.persistence.elfie_chat_history import (
    ElfieChatMessageInput,
    ElfieChatMessageRecord,
    ElfieChatSender,
    record_elfie_chat_message,
)


def record_owner_chat_message(
    elfie_id: str,
    user_id: int,
    text: str,
    *,
    conversation_id: str,
    channel: str,
    message_id: str | None = None,
    meta: str = "已投递到下一次 tick",
) -> ElfieChatMessageRecord:
    """把 Owner 发往精灵的文本写入该精灵自己的工作区。"""
    return record_elfie_chat_message(
        elfie_id,
        ElfieChatMessageInput(
            message_id=message_id or _new_message_id(channel),
            conversation_id=conversation_id,
            sender=ElfieChatSender.USER,
            text=text,
            channel=channel,
            user_id=user_id,
            meta=meta,
        ),
    )


def record_elfie_chat_reply(
    elfie_id: str,
    user_id: int,
    text: str,
    *,
    conversation_id: str,
    channel: str,
    meta: str,
) -> ElfieChatMessageRecord:
    """把精灵对指定 Owner 会话的文本回复写入精灵工作区。"""
    return record_elfie_chat_message(
        elfie_id,
        ElfieChatMessageInput(
            message_id=_new_message_id(channel),
            conversation_id=conversation_id,
            sender=ElfieChatSender.ELFIE,
            text=text,
            channel=channel,
            user_id=user_id,
            meta=meta,
        ),
    )


def _new_message_id(channel: str) -> str:
    return f"{channel}:{uuid4().hex}"
