"""Typed Telegram outbound channel for one Elfie and one private conversation."""

from __future__ import annotations

import logging
from typing import Optional, Protocol

from elfie.communication.contracts import (
    CommunicationEnvelope,
    DeliveryReceipt,
    DeliveryStatus,
    TextPart,
)

from .client import TelegramSentMessage

logger = logging.getLogger("infrastructure.communication.telegram.channel")


class TelegramSendClient(Protocol):
    def send_message(self, chat_id: str, text: str) -> TelegramSentMessage: ...

    def close(self) -> None: ...


class TelegramReplyHistory(Protocol):
    def record_reply(
        self,
        *,
        elfie_id: str,
        conversation_id: str,
        text: str,
        source_message_key: str,
    ) -> None: ...


class TelegramConnector:
    """Small stateful edge around an already authenticated Bot API client."""

    def __init__(self, client: TelegramSendClient) -> None:
        self._client = client
        self.is_connected = False

    def connect(self) -> bool:
        self.is_connected = True
        return True

    def disconnect(self) -> None:
        if not self.is_connected:
            return
        self.is_connected = False
        self._client.close()

    def send_message(self, chat_id: str, text: str) -> TelegramSentMessage:
        if not self.is_connected:
            raise RuntimeError("Telegram channel is disconnected")
        return self._client.send_message(chat_id, text)


class TelegramChannel:
    """Send P0 text replies only to the pairing-authorized Telegram chat."""

    channel_id = "telegram"

    def __init__(
        self,
        connector: TelegramConnector,
        *,
        elfie_id: str,
        bot_id: str,
        conversation_id: str,
        history: Optional[TelegramReplyHistory] = None,
    ) -> None:
        self.connector = connector
        self._elfie_id = elfie_id
        self._bot_id = bot_id
        self._conversation_id = conversation_id
        self._history = history

    @property
    def authorized_conversation_ids(self) -> tuple[str, ...]:
        return (self._conversation_id,)

    @property
    def is_connected(self) -> bool:
        return self.connector.is_connected

    def connect(self) -> bool:
        return self.connector.connect()

    def disconnect(self) -> None:
        self.connector.disconnect()

    def send_envelope(self, envelope: CommunicationEnvelope) -> DeliveryReceipt:
        if envelope.conversation_id != self._conversation_id:
            return DeliveryReceipt.for_envelope(
                envelope,
                status=DeliveryStatus.FAILED,
                error_code="telegram_conversation_forbidden",
                error_message="Telegram conversation is not authorized",
            )
        chat_id = _chat_id(self._conversation_id)
        if chat_id is None:
            return DeliveryReceipt.for_envelope(
                envelope,
                status=DeliveryStatus.FAILED,
                error_code="telegram_conversation_invalid",
                error_message="Telegram conversation is invalid",
            )
        for part in envelope.parts:
            if not isinstance(part, TextPart):
                return DeliveryReceipt.for_envelope(
                    envelope,
                    status=DeliveryStatus.FAILED,
                    error_code="telegram_content_unsupported",
                    error_message="Telegram P0 supports text messages only",
                )
            try:
                sent = self.connector.send_message(chat_id, part.text)
            except (OSError, RuntimeError):
                return DeliveryReceipt.for_envelope(
                    envelope,
                    status=DeliveryStatus.FAILED,
                    error_code="telegram_send_failed",
                    error_message="Telegram did not confirm message delivery",
                    retryable=True,
                )
            if self._history is not None:
                try:
                    self._history.record_reply(
                        elfie_id=self._elfie_id,
                        conversation_id=self._conversation_id,
                        text=part.text,
                        source_message_key=(
                            f"telegram:{self._bot_id}:chat:{chat_id}:"
                            f"message:{sent.message_id}"
                        ),
                    )
                except RuntimeError:
                    # Telegram already accepted the message. Retrying would create a
                    # visible duplicate, so history failure cannot change the receipt.
                    logger.warning(
                        "Telegram reply delivered but local history recording failed "
                        "for Elfie %s",
                        self._elfie_id,
                    )
        return DeliveryReceipt.for_envelope(envelope, status=DeliveryStatus.SENT)


def _chat_id(conversation_id: str) -> Optional[str]:
    prefix = "telegram:"
    candidate = (
        conversation_id[len(prefix) :] if conversation_id.startswith(prefix) else ""
    )
    if not candidate or not candidate.lstrip("-").isdigit():
        return None
    return candidate


__all__ = ("TelegramChannel", "TelegramConnector")
