"""精灵网络消息收发的基础策略。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet

from elfie.communication.channel import CommunicationMessage, MessageDirection


class CommunicationPolicyError(ValueError):
    """消息不符合当前精灵的通信策略。"""


@dataclass(frozen=True)
class CommunicationPolicy:
    allowed_channels: FrozenSet[str] = frozenset()
    allow_inbound: bool = True
    allow_outbound: bool = True
    max_content_length: int = 4096

    def validate(self, message: CommunicationMessage) -> None:
        if self.allowed_channels and message.channel_id not in self.allowed_channels:
            raise CommunicationPolicyError(f"不允许使用通信通道: {message.channel_id}")
        if message.direction is MessageDirection.INBOUND and not self.allow_inbound:
            raise CommunicationPolicyError("当前禁止接收网络消息")
        if message.direction is MessageDirection.OUTBOUND and not self.allow_outbound:
            raise CommunicationPolicyError("当前禁止发送网络消息")
        if not message.content:
            raise CommunicationPolicyError("消息内容不能为空")
        if len(message.content) > self.max_content_length:
            raise CommunicationPolicyError(
                f"消息长度超过限制: {len(message.content)}/{self.max_content_length}"
            )
