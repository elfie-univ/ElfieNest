"""Typed Discord outbound channel for one Elfie and one authorized DM."""

from __future__ import annotations

import logging
from typing import Optional, Protocol

from elfie.communication.contracts import (
    CommunicationEnvelope,
    DeliveryReceipt,
    DeliveryStatus,
    TextPart,
)

from .client import DiscordSentMessage

logger = logging.getLogger("infrastructure.communication.discord.channel")


class DiscordSendClient(Protocol):
    def send_message(self, channel_id: str, text: str) -> DiscordSentMessage: ...

    def close(self) -> None: ...


class DiscordReplyHistory(Protocol):
    def record_reply(
        self,
        *,
        elfie_id: str,
        conversation_id: str,
        text: str,
        source_message_key: str,
    ) -> None: ...


class DiscordConnector:
    def __init__(self, client: DiscordSendClient) -> None:
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

    def send_message(self, channel_id: str, text: str) -> DiscordSentMessage:
        if not self.is_connected:
            raise RuntimeError("Discord channel is disconnected")
        return self._client.send_message(channel_id, text)


class DiscordChannel:
    """Send P0 text replies only to the pairing-authorized Discord DM."""

    channel_id = "discord"

    def __init__(
        self,
        connector: DiscordConnector,
        *,
        elfie_id: str,
        bot_id: str,
        conversation_id: str,
        history: Optional[DiscordReplyHistory] = None,
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
                error_code="discord_conversation_forbidden",
                error_message="Discord conversation is not authorized",
            )
        channel_id = _channel_id(self._conversation_id)
        if channel_id is None:
            return DeliveryReceipt.for_envelope(
                envelope,
                status=DeliveryStatus.FAILED,
                error_code="discord_conversation_invalid",
                error_message="Discord conversation is invalid",
            )
        for part in envelope.parts:
            if not isinstance(part, TextPart):
                return DeliveryReceipt.for_envelope(
                    envelope,
                    status=DeliveryStatus.FAILED,
                    error_code="discord_content_unsupported",
                    error_message="Discord P0 supports text messages only",
                )
            try:
                sent = self.connector.send_message(channel_id, part.text)
            except (OSError, RuntimeError, ValueError):
                return DeliveryReceipt.for_envelope(
                    envelope,
                    status=DeliveryStatus.FAILED,
                    error_code="discord_send_failed",
                    error_message="Discord did not confirm message delivery",
                    retryable=True,
                )
            if self._history is not None:
                try:
                    self._history.record_reply(
                        elfie_id=self._elfie_id,
                        conversation_id=self._conversation_id,
                        text=part.text,
                        source_message_key=(
                            f"discord:{self._bot_id}:channel:{channel_id}:"
                            f"message:{sent.message_id}"
                        ),
                    )
                except RuntimeError:
                    logger.warning(
                        "Discord reply delivered but local history recording failed "
                        "for Elfie %s",
                        self._elfie_id,
                    )
        return DeliveryReceipt.for_envelope(envelope, status=DeliveryStatus.SENT)


def _channel_id(conversation_id: str) -> Optional[str]:
    prefix = "discord:"
    candidate = (
        conversation_id[len(prefix) :] if conversation_id.startswith(prefix) else ""
    )
    return candidate if candidate and candidate.isdigit() else None


__all__ = ("DiscordChannel", "DiscordConnector")
