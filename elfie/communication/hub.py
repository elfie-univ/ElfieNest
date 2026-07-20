"""一只精灵独立拥有的网络消息通信中心。"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from elfie.communication.channel import (
    CommunicationChannel,
    CommunicationMessage,
    MessageDirection,
    MessageKind,
)
from elfie.communication.inbox import CommunicationInbox
from elfie.communication.outbox import CommunicationOutbox, DeliveryReceipt
from elfie.communication.policy import CommunicationPolicy
from elfie.communication.router import CommunicationRouter


class CommunicationHub:
    """管理网络通道、收件箱和发件箱，不经过身体动作链路。"""

    def __init__(
        self,
        elfie_id: str,
        *,
        policy: Optional[CommunicationPolicy] = None,
        router: Optional[CommunicationRouter] = None,
    ) -> None:
        self.elfie_id = elfie_id
        self.policy = policy or CommunicationPolicy()
        self.router = router or CommunicationRouter()
        self.inbox = CommunicationInbox()
        self.outbox = CommunicationOutbox()

    def bind_identity(self, elfie_id: str) -> None:
        self.elfie_id = elfie_id

    def register_channel(
        self,
        channel: CommunicationChannel,
        *,
        connect: bool = False,
        replace: bool = False,
    ) -> CommunicationChannel:
        registered = self.router.register(channel, replace=replace)
        if connect:
            registered.connect()
        return registered

    def receive(
        self,
        *,
        channel_id: str,
        sender_id: str,
        content: str,
        kind: MessageKind = MessageKind.TEXT,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> CommunicationMessage:
        message = CommunicationMessage(
            channel_id=channel_id,
            direction=MessageDirection.INBOUND,
            sender_id=sender_id,
            recipient_id=self.elfie_id,
            content=content,
            kind=kind,
            metadata=dict(metadata or {}),
        )
        self.policy.validate(message)
        if self.router.get(channel_id) is None:
            raise KeyError(f"通信通道未注册: {channel_id}")
        self.inbox.receive(message)
        return message

    def send(
        self,
        *,
        channel_id: str,
        recipient_id: str,
        content: str,
        kind: MessageKind = MessageKind.TEXT,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> DeliveryReceipt:
        message = CommunicationMessage(
            channel_id=channel_id,
            direction=MessageDirection.OUTBOUND,
            sender_id=self.elfie_id,
            recipient_id=recipient_id,
            content=content,
            kind=kind,
            metadata=dict(metadata or {}),
        )
        self.policy.validate(message)
        receipt = self.router.route(message)
        self.outbox.record(message, receipt)
        return receipt

    def drain_inbox(
        self, limit: Optional[int] = None
    ) -> List[CommunicationMessage]:
        return self.inbox.drain(limit)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "elfie_id": self.elfie_id,
            "channels": [
                {
                    "channel_id": channel.channel_id,
                    "connected": channel.is_connected,
                }
                for channel in self.router.list_channels()
            ],
            "pending_inbox": self.inbox.pending_count,
            "outbox_count": len(self.outbox.history),
        }
