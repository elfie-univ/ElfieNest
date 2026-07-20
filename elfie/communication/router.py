"""通信通道注册和出站路由。"""

from __future__ import annotations

from threading import RLock
from typing import Dict, List, Optional

from elfie.communication.channel import CommunicationChannel, CommunicationMessage
from elfie.communication.outbox import DeliveryReceipt, DeliveryStatus


class ChannelRegistrationError(ValueError):
    """通道没有实现协议或标识发生冲突。"""


class CommunicationRouter:
    def __init__(self) -> None:
        self._channels: Dict[str, CommunicationChannel] = {}
        self._lock = RLock()

    def register(
        self, channel: CommunicationChannel, *, replace: bool = False
    ) -> CommunicationChannel:
        if not isinstance(channel, CommunicationChannel):
            raise ChannelRegistrationError("通道没有完整实现 CommunicationChannel")
        channel_id = str(channel.channel_id).strip()
        if not channel_id:
            raise ChannelRegistrationError("channel_id 不能为空")
        with self._lock:
            existing = self._channels.get(channel_id)
            if existing is not None and existing is not channel and not replace:
                raise ChannelRegistrationError(f"通信通道已经注册: {channel_id}")
            self._channels[channel_id] = channel
        return channel

    def unregister(self, channel_id: str) -> CommunicationChannel:
        with self._lock:
            try:
                return self._channels.pop(channel_id)
            except KeyError as exc:
                raise KeyError(f"通信通道未注册: {channel_id}") from exc

    def get(self, channel_id: str) -> Optional[CommunicationChannel]:
        with self._lock:
            return self._channels.get(channel_id)

    def list_channels(self) -> List[CommunicationChannel]:
        with self._lock:
            return list(self._channels.values())

    def connect(self, channel_id: str) -> bool:
        channel = self.get(channel_id)
        if channel is None:
            raise KeyError(f"通信通道未注册: {channel_id}")
        return channel.connect()

    def disconnect_all(self) -> None:
        for channel in self.list_channels():
            channel.disconnect()

    def route(self, message: CommunicationMessage) -> DeliveryReceipt:
        channel = self.get(message.channel_id)
        if channel is None:
            return self._failed(message, f"通信通道未注册: {message.channel_id}")
        if not channel.is_connected:
            return self._failed(message, f"通信通道尚未连接: {message.channel_id}")
        try:
            delivered = channel.send(message)
        except Exception as exc:
            return self._failed(message, f"通信通道发送失败: {exc}")
        if not delivered:
            return self._failed(message, "通信通道未确认发送成功")
        return DeliveryReceipt(
            message_id=message.message_id,
            channel_id=message.channel_id,
            status=DeliveryStatus.SENT,
        )

    @staticmethod
    def _failed(message: CommunicationMessage, error: str) -> DeliveryReceipt:
        return DeliveryReceipt(
            message_id=message.message_id,
            channel_id=message.channel_id,
            status=DeliveryStatus.FAILED,
            error=error,
        )
