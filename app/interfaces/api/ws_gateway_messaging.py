"""Message routing for the authenticated legacy WebSocket transport."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Set

from app.features.accounts import AccountPrincipal
from app.features.communication import CommunicationError
from app.orchestration.message_delivery import (
    DeliverElfieReplyCommand,
    MessageDeliveryError,
    MessageDeliveryFacade,
    SubmitUserMessageCommand,
)

logger = logging.getLogger("app.interfaces.api.ws_gateway")


class WebSocketMessagingMixin:
    """Map legacy frames onto the one message-delivery workflow."""

    async def _handle_message(
        self: Any,
        principal: AccountPrincipal,
        raw: str,
    ) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return
        if not isinstance(data, dict):
            return
        payload = data.get("payload", {}) or {}
        if data.get("event") != "user_message" or not isinstance(payload, dict):
            return
        elfie_id = payload.get("elfie_id")
        message = payload.get("message")
        if not isinstance(elfie_id, str) or not isinstance(message, str):
            return
        try:
            self._delivery().submit_user_message(
                principal,
                SubmitUserMessageCommand(
                    elfie_id=elfie_id,
                    text=message,
                    channel="web",
                ),
            )
        except (CommunicationError, MessageDeliveryError) as error:
            logger.warning(
                "WS 用户 %d 的聊天消息被拒绝: %s",
                principal.user_id,
                error,
            )
            return
        logger.info(
            "WS 用户 %d -> 精灵 '%s' 消息已投递",
            principal.user_id,
            elfie_id.strip(),
        )

    def send_to_user(self: Any, user_id: int, message_dict: Dict[str, Any]) -> None:
        """Send one legacy frame to all current sockets for a member."""
        if user_id not in self.connections:
            return
        message = json.dumps(message_dict, ensure_ascii=False)
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._async_send_to_set(self.connections[user_id].copy(), message),
                self._loop,
            )

    def broadcast_to_owners(
        self: Any,
        elfie_id: str,
        message_dict: Dict[str, Any],
    ) -> None:
        """Persist one Elfie reply, then fan it out through both transports."""
        event = message_dict.get("event") or message_dict.get("action")
        payload = message_dict.get("payload") or {}
        if not isinstance(payload, dict):
            return
        text = self._elfie_message_text(str(event), payload)
        if not text:
            return
        emotion = str(payload.get("emotion") or "").strip()
        try:
            delivered = self._delivery().deliver_elfie_reply(
                DeliverElfieReplyCommand(
                    elfie_id=elfie_id,
                    text=text,
                    channel="web",
                    meta=f"情绪：{emotion}" if emotion else "实时回复",
                )
            )
        except (CommunicationError, MessageDeliveryError) as error:
            logger.warning("精灵聊天消息投递失败: %s", error)
            return

        targets: Set[Any] = set(self.connections.get(delivered.owner_user_id, set()))
        if not targets:
            return
        message = json.dumps(message_dict, ensure_ascii=False)
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._async_send_to_set(targets, message),
                self._loop,
            )

    async def _async_send_to_set(
        self: Any,
        targets: Set[Any],
        message_str: str,
    ) -> None:
        if not targets:
            return
        valid_targets: list[Any] = []
        revoked_targets: list[Any] = []
        for websocket in targets:
            info = self._user_info.get(websocket)
            if info is None:
                continue
            token = info.get("token", "")
            user_id = info.get("user_id")
            if (
                isinstance(token, str)
                and isinstance(user_id, int)
                and self._session_is_current(token, user_id)
            ):
                valid_targets.append(websocket)
            else:
                revoked_targets.append(websocket)
        if revoked_targets:
            await asyncio.gather(
                *(
                    websocket.close(4004, "Session revoked")
                    for websocket in revoked_targets
                ),
                return_exceptions=True,
            )
            for websocket in revoked_targets:
                info = self._user_info.get(websocket)
                if info is not None and isinstance(info.get("user_id"), int):
                    self._remove_connection(info["user_id"], websocket)
        tasks = [
            websocket.send(message_str)
            for websocket in valid_targets
            if websocket in self._user_info
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _delivery(self: Any) -> MessageDeliveryFacade:
        service = getattr(self, "message_delivery", None)
        if not isinstance(service, MessageDeliveryFacade):
            raise RuntimeError("WebSocket gateway has no message-delivery service")
        return service

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
