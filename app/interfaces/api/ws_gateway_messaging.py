"""Message routing and persistence helpers for the authenticated WS gateway."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional, Set

from app.infrastructure.persistence.runtime_query_repository import (
    RuntimeQueryRepository,
)
from app.interfaces.api.chat_persistence import (
    record_elfie_chat_reply,
    record_owner_chat_message,
)

logger = logging.getLogger("app.interfaces.api.ws_gateway")


class WebSocketMessagingMixin:
    """Keep message authorization, fan-out, and chat persistence cohesive."""

    async def _handle_message(
        self: Any, user_id: int, raw: str, account_id: Optional[str] = None
    ) -> None:
        """处理单条 WebSocket 消息。"""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return
        if not isinstance(data, dict):
            return

        event = data.get("event")
        payload = data.get("payload", {}) or {}
        if not isinstance(payload, dict):
            return
        if event != "user_message":
            return

        elfie_id = payload.get("elfie_id")
        message = payload.get("message")
        if not isinstance(elfie_id, str) or not isinstance(message, str):
            return
        elfie_id = elfie_id.strip()
        message = message.strip()
        if not elfie_id or not message:
            return
        if not self._is_elfie_owned_by(elfie_id, user_id):
            logger.warning(
                "用户 %d 尝试给不属于他的精灵 '%s' 发消息，已拒绝",
                user_id,
                elfie_id,
            )
            return

        resolved_account_id = account_id or self._account_id_for_user(user_id)
        if resolved_account_id is None:
            logger.warning("用户 %d 不存在，拒绝投递聊天消息", user_id)
            return

        conversation_id = f"owner:{user_id}"
        if self.nest_session is not None:
            self.nest_session.send_user_message(
                elfie_id,
                message,
                owner_id=str(user_id),
                conversation_id=conversation_id,
                external_message_id=None,
                account_id=resolved_account_id,
            )
            logger.info("WS 用户 %d -> 精灵 '%s' 消息已投递", user_id, elfie_id)
        try:
            record_owner_chat_message(
                elfie_id,
                user_id,
                message,
                conversation_id=conversation_id,
                channel="web",
            )
        except RuntimeError as exc:
            logger.warning("用户聊天消息持久化失败: %s", exc)

    def _is_elfie_owned_by(self: Any, elfie_id: str, user_id: int) -> bool:
        """检查 elfie_id 是否属于 user_id。"""
        return RuntimeQueryRepository(self.db_path).elfie_is_owned_by(elfie_id, user_id)

    def _get_elfie_owner(self: Any, elfie_id: str) -> Optional[int]:
        """查询精灵的 owner_user_id。"""
        return RuntimeQueryRepository(self.db_path).owner_id_for_elfie(elfie_id)

    def _account_id_for_user(self: Any, user_id: int) -> Optional[str]:
        """Read the canonical account identifier for a verified user id."""
        account = RuntimeQueryRepository(self.db_path).find_account_by_id(user_id)
        return account.account_id if account is not None else None

    def send_to_user(self: Any, user_id: int, message_dict: Dict[str, Any]) -> None:
        """向指定 user_id 的所有 WS 连接发送消息。"""
        if user_id not in self.connections:
            return
        msg_str = json.dumps(message_dict, ensure_ascii=False)
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._async_send_to_set(self.connections[user_id].copy(), msg_str),
                self._loop,
            )

    def broadcast_to_owners(
        self: Any, elfie_id: str, message_dict: Dict[str, Any]
    ) -> None:
        """只向精灵所属用户的连接广播消息。"""
        owner_id = self._get_elfie_owner(elfie_id)
        if owner_id is None:
            return

        msg_str = json.dumps(message_dict, ensure_ascii=False)
        recorded = self._record_elfie_message(elfie_id, owner_id, message_dict)
        if recorded and self.product_chat_hub is not None:
            self.product_chat_hub.publish_elfie_reply(elfie_id)

        target: Set[Any] = set()
        if owner_id in self.connections:
            target.update(self.connections[owner_id])
        if not target:
            return
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._async_send_to_set(target, msg_str), self._loop
            )

    async def _async_send_to_set(
        self: Any, targets: Set[Any], message_str: str
    ) -> None:
        """异步向一组 WebSocket 连接发送消息。"""
        if not targets:
            return
        valid_targets: list[Any] = []
        revoked_targets: list[Any] = []
        for ws in targets:
            info = self._user_info.get(ws)
            if info is None:
                continue
            token = info.get("token", "")
            user_id = info.get("user_id")
            if (
                isinstance(token, str)
                and isinstance(user_id, int)
                and self._session_is_current(token, user_id)
            ):
                valid_targets.append(ws)
            else:
                revoked_targets.append(ws)
        if revoked_targets:
            await asyncio.gather(
                *(ws.close(4004, "Session revoked") for ws in revoked_targets),
                return_exceptions=True,
            )
            for ws in revoked_targets:
                info = self._user_info.get(ws)
                if info is not None and isinstance(info.get("user_id"), int):
                    self._remove_connection(info["user_id"], ws)
        tasks = [ws.send(message_str) for ws in valid_targets if ws in self._user_info]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _record_elfie_message(
        self: Any,
        elfie_id: str,
        user_id: int,
        message_dict: Dict[str, Any],
    ) -> bool:
        event = message_dict.get("event") or message_dict.get("action")
        payload = message_dict.get("payload") or {}
        if not isinstance(payload, dict):
            return False
        text = self._elfie_message_text(str(event), payload)
        if not text:
            return False
        emotion = str(payload.get("emotion") or "").strip()
        try:
            record_elfie_chat_reply(
                elfie_id,
                user_id,
                text,
                conversation_id=f"owner:{user_id}",
                channel="web",
                meta=f"情绪：{emotion}" if emotion else "实时回复",
            )
        except RuntimeError as exc:
            logger.warning("精灵聊天消息持久化失败: %s", exc)
            return False
        return True

    @staticmethod
    def _elfie_message_text(event: str, payload: Dict[str, Any]) -> str:
        if event == "speak_event":
            return str(payload.get("text") or "").strip()
        if event != "owner_message":
            return ""
        parts = payload.get("parts") or []
        if not isinstance(parts, list):
            return ""
        texts = [
            str(part.get("text") or "").strip()
            for part in parts
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        return "\n".join(text for text in texts if text)


__all__ = ("WebSocketMessagingMixin",)
