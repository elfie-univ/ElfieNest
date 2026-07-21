"""精灵通信 envelope 的本地准入策略。"""

from __future__ import annotations

from dataclasses import dataclass
from functools import singledispatch
from typing import FrozenSet

from elfie.communication.contracts import (
    AudioPart,
    CommunicationEnvelope,
    ContentPart,
    FilePart,
    ImagePart,
    MessageDirection,
    ReactionPart,
    SystemEventPart,
    TextPart,
)
from elfie.message_types import ErrorInfo


@dataclass(frozen=True, slots=True)
class CommunicationPolicyError(ValueError):
    """A typed policy denial retained as an exception for legacy callers."""

    error: ErrorInfo

    def __str__(self) -> str:
        return self.error.message


@dataclass(frozen=True, slots=True)
class CommunicationPolicy:
    """Local allow-list and content-size policy for both directions."""

    allowed_channels: FrozenSet[str] = frozenset()
    blocked_sender_ids: FrozenSet[str] = frozenset()
    allow_inbound: bool = True
    allow_outbound: bool = True
    max_content_length: int = 4096

    def validate(self, envelope: CommunicationEnvelope) -> None:
        """Raise one typed denial before an envelope reaches storage/transport."""
        if self.allowed_channels and envelope.channel_id not in self.allowed_channels:
            self._deny("channel_not_allowed", f"不允许使用通信通道: {envelope.channel_id}")
        if envelope.sender_id in self.blocked_sender_ids:
            self._deny("sender_blocked", f"通信发送者已被拒绝: {envelope.sender_id}")
        direction_policy = {
            MessageDirection.INBOUND: (
                self.allow_inbound,
                "inbound_disabled",
                "当前禁止接收网络消息",
            ),
            MessageDirection.OUTBOUND: (
                self.allow_outbound,
                "outbound_disabled",
                "当前禁止发送网络消息",
            ),
        }
        allowed, code, message = direction_policy[envelope.direction]
        if not allowed:
            self._deny(code, message)
        content_length = sum(_content_length(part) for part in envelope.parts)
        if content_length > self.max_content_length:
            self._deny(
                "content_too_long",
                f"消息长度超过限制: {content_length}/{self.max_content_length}",
            )

    @staticmethod
    def _deny(code: str, message: str) -> None:
        raise CommunicationPolicyError(
            error=ErrorInfo(code=code, message=message, retryable=False)
        )


@singledispatch
def _content_length(part: ContentPart) -> int:
    raise TypeError(type(part).__name__)


@_content_length.register
def _text_length(part: TextPart) -> int:
    return len(part.text)


@_content_length.register
def _image_length(part: ImagePart) -> int:
    return len(part.caption or "")


@_content_length.register
def _audio_length(part: AudioPart) -> int:
    return len(part.transcript or "")


@_content_length.register
def _file_length(part: FilePart) -> int:
    return len(part.filename)


@_content_length.register
def _reaction_length(part: ReactionPart) -> int:
    return len(part.reaction)


@_content_length.register
def _system_event_length(part: SystemEventPart) -> int:
    return len(part.description or "")


__all__ = ("CommunicationPolicy", "CommunicationPolicyError")
