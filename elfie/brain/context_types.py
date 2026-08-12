"""Immutable context snapshots assembled for one cortical turn."""

from __future__ import annotations

from typing import Annotated, Optional, Tuple

from pydantic import Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError

from elfie.brain.perception_types import TurnFrame
from elfie.message_types import ActorRef, EventId, FrozenContractModel, UTCDateTime

_NonBlankText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, pattern=r".*\S.*"),
]
_Revision = Annotated[int, Field(strict=True, ge=0)]
_Ratio = Annotated[float, Field(strict=True, ge=0.0, le=1.0)]
_Percent = Annotated[float, Field(strict=True, ge=0.0, le=100.0)]


class EmotionValue(FrozenContractModel):
    """One named normalized emotion value."""

    name: _NonBlankText
    intensity: _Ratio


class EmotionSnapshot(FrozenContractModel):
    """Emotion state captured by the single Brain owner."""

    revision: _Revision
    captured_at: UTCDateTime
    values: Tuple[EmotionValue, ...]
    dominant: Optional[_NonBlankText]


class HomeostasisSnapshot(FrozenContractModel):
    """Energy and fatigue captured after timestamp-driven advancement."""

    revision: _Revision
    captured_at: UTCDateTime
    energy: _Percent
    fatigue: _Percent
    sleeping: bool


class ConversationMessage(FrozenContractModel):
    """A source-preserving conversation item used as model context."""

    event_id: EventId
    sender: ActorRef
    occurred_at: UTCDateTime
    content: _NonBlankText


class ConversationContext(FrozenContractModel):
    """Bounded conversation history selected for the current frame."""

    revision: _Revision
    captured_at: UTCDateTime
    conversation_id: Optional[_NonBlankText]
    messages: Tuple[ConversationMessage, ...]


class MemoryItem(FrozenContractModel):
    """A typed memory excerpt with explicit causal sources."""

    memory_id: EventId
    content: _NonBlankText
    relevance: _Ratio
    source_event_ids: Tuple[EventId, ...]


class MemoryContext(FrozenContractModel):
    """Bounded memory excerpts selected for one cortical turn."""

    revision: _Revision
    captured_at: UTCDateTime
    items: Tuple[MemoryItem, ...]


class BodyCapabilityDescriptor(FrozenContractModel):
    """Capabilities of the single body currently bound to the Elfie."""

    body_id: _NonBlankText
    body_generation: _Revision = 1
    capability_revision: _Revision
    sensors: Tuple[_NonBlankText, ...]
    actions: Tuple[_NonBlankText, ...]


class ConnectedChannelDescriptor(FrozenContractModel):
    """Capabilities of one currently connected communication channel."""

    channel_id: _NonBlankText
    account_id: _NonBlankText
    capability_revision: _Revision
    content_kinds: Tuple[_NonBlankText, ...]
    authorized_conversation_ids: Tuple[_NonBlankText, ...] = ()


class EffectiveCapabilities(FrozenContractModel):
    """Only the current Body and currently connected channel endpoints."""

    revision: _Revision
    captured_at: UTCDateTime
    current_body: Optional[BodyCapabilityDescriptor]
    connected_channels: Tuple[ConnectedChannelDescriptor, ...]

    @model_validator(mode="after")
    def validate_unique_channels(self) -> EffectiveCapabilities:
        """Reject ambiguous duplicate channel identities."""
        channel_ids = tuple(channel.channel_id for channel in self.connected_channels)
        if len(set(channel_ids)) != len(channel_ids):
            raise PydanticCustomError(
                "duplicate_channel_id",
                "connected channel IDs must be unique",
            )
        return self


class BrainContext(FrozenContractModel):
    """Complete immutable input for one cortical decision."""

    revision: _Revision
    captured_at: UTCDateTime
    frame: TurnFrame
    emotion: EmotionSnapshot
    homeostasis: HomeostasisSnapshot
    conversation: ConversationContext
    memory: MemoryContext
    capabilities: EffectiveCapabilities

    @model_validator(mode="after")
    def validate_capture_boundary(self) -> BrainContext:
        """Prevent snapshots captured after the context cutoff from leaking in."""
        captured_times = (
            self.frame.captured_at,
            self.emotion.captured_at,
            self.homeostasis.captured_at,
            self.conversation.captured_at,
            self.memory.captured_at,
            self.capabilities.captured_at,
        )
        if any(captured_at > self.captured_at for captured_at in captured_times):
            raise PydanticCustomError(
                "context_captured_at",
                "nested captured_at values cannot be newer than BrainContext",
            )
        return self


__all__ = (
    "BodyCapabilityDescriptor",
    "BrainContext",
    "ConnectedChannelDescriptor",
    "ConversationContext",
    "ConversationMessage",
    "EffectiveCapabilities",
    "EmotionSnapshot",
    "EmotionValue",
    "HomeostasisSnapshot",
    "MemoryContext",
    "MemoryItem",
)
