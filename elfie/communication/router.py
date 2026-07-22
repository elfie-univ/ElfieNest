"""通信通道注册和完整 envelope 出站路由。"""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Dict, List, Optional

from elfie.communication.channel import CommunicationChannel
from elfie.communication.contracts import (
    CommunicationEnvelope,
    DeliveryReceipt,
    DeliveryStatus,
)

RegisteredChannel = CommunicationChannel


@dataclass(frozen=True)
class ChannelRegistrationError(ValueError):
    """A channel is incomplete or conflicts with an existing registration."""

    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True)
class ChannelNotFoundError(KeyError):
    """A requested channel ID is absent from the registry."""

    channel_id: str

    def __str__(self) -> str:
        return f"通信通道未注册: {self.channel_id}"


class CommunicationRouter:
    """Thread-safe channel registry and typed routing boundary."""

    def __init__(self) -> None:
        self._channels: Dict[str, CommunicationChannel] = {}
        self._lock = RLock()

    def register(
        self,
        channel: RegisteredChannel,
        *,
        replace: bool = False,
    ) -> RegisteredChannel:
        """Register one channel that implements the complete typed contract."""
        if not isinstance(channel, CommunicationChannel):
            raise ChannelRegistrationError(
                reason="通道没有完整实现 CommunicationChannel"
            )
        channel_id = str(channel.channel_id).strip()
        if not channel_id:
            raise ChannelRegistrationError(reason="channel_id 不能为空")
        with self._lock:
            existing = self._channels.get(channel_id)
            if existing is not None and existing is not channel and not replace:
                raise ChannelRegistrationError(reason=f"通信通道已经注册: {channel_id}")
            self._channels[channel_id] = channel
        return channel

    def unregister(self, channel_id: str) -> CommunicationChannel:
        with self._lock:
            try:
                return self._channels.pop(channel_id)
            except KeyError as exc:
                raise ChannelNotFoundError(channel_id=channel_id) from exc

    def get(self, channel_id: str) -> Optional[CommunicationChannel]:
        with self._lock:
            return self._channels.get(channel_id)

    def list_channels(self) -> List[CommunicationChannel]:
        with self._lock:
            return list(self._channels.values())

    def connect(self, channel_id: str) -> bool:
        channel = self.get(channel_id)
        if channel is None:
            raise ChannelNotFoundError(channel_id=channel_id)
        return channel.connect()

    def disconnect_all(self) -> None:
        for channel in self.list_channels():
            channel.disconnect()

    def route(self, envelope: CommunicationEnvelope) -> DeliveryReceipt:
        """Send one canonical envelope and normalize every expected failure."""
        channel = self.get(envelope.channel_id)
        if channel is None:
            return self._failed(
                envelope,
                code="unknown_channel",
                message=f"通信通道未注册: {envelope.channel_id}",
            )
        if not channel.is_connected:
            return self._failed(
                envelope,
                code="channel_disconnected",
                message=f"通信通道尚未连接: {envelope.channel_id}",
                retryable=True,
            )
        try:
            receipt = channel.send_envelope(envelope)
        except (OSError, RuntimeError) as exc:
            return self._failed(
                envelope,
                code="channel_send_failed",
                message=f"通信通道发送失败: {exc}",
                retryable=True,
            )
        if (
            receipt.message_id != envelope.meta.event_id
            or receipt.channel_id != envelope.channel_id
        ):
            return self._failed(
                envelope,
                code="invalid_channel_receipt",
                message="通信通道返回了不匹配的投递回执",
            )
        return receipt

    @staticmethod
    def _failed(
        envelope: CommunicationEnvelope,
        *,
        code: str,
        message: str,
        retryable: bool = False,
    ) -> DeliveryReceipt:
        return DeliveryReceipt.for_envelope(
            envelope,
            status=DeliveryStatus.FAILED,
            error_code=code,
            error_message=message,
            retryable=retryable,
        )


__all__ = (
    "ChannelRegistrationError",
    "ChannelNotFoundError",
    "CommunicationRouter",
    "RegisteredChannel",
)
