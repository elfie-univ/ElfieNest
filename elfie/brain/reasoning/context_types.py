"""Reasoning-owned composition contracts for one immutable Brain turn.

Each mental system owns its own snapshot contract.  This module owns only
conversation working context, effective capability projection, and the final
cross-system context capsule consumed by Reasoning.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal, Mapping, Optional, Tuple

from pydantic import Field, JsonValue, StringConstraints, model_validator
from pydantic_core import PydanticCustomError

from elfie.brain.activity.context import ActivityContext
from elfie.brain.consolidation.contracts import CognitiveConsolidationSnapshot
from elfie.brain.emotion.contracts import EmotionSnapshot
from elfie.brain.energy.contracts import EnergySnapshot
from elfie.brain.memory.contracts import MemoryContext
from elfie.brain.motivation.contracts import MotivationSnapshot
from elfie.brain.orientation.contracts import OrientationSnapshot
from elfie.brain.selfhood.contracts import SelfhoodPromptProjection
from elfie.brain.workspace.contracts import TurnFrame
from elfie.message_types import (
    ActorRef,
    EventId,
    FrozenContractModel,
    IntentId,
    UTCDateTime,
)

_NonBlankText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, pattern=r".*\S.*"),
]
_Revision = Annotated[int, Field(strict=True, ge=0)]


class ConversationMessage(FrozenContractModel):
    """A source-preserving conversation item used as model context."""

    event_id: EventId
    sender: ActorRef
    occurred_at: UTCDateTime
    content: _NonBlankText


class ContextSummary(FrozenContractModel):
    """Source-backed deterministic compression owned only by Reasoning."""

    summary_id: _NonBlankText
    version: Annotated[int, Field(strict=True, ge=1)] = 1
    source_event_ids: Tuple[EventId, ...]
    occurred_from: UTCDateTime
    occurred_to: UTCDateTime
    content: _NonBlankText
    unresolved_items: Tuple[_NonBlankText, ...] = ()

    @model_validator(mode="after")
    def validate_source_range(self) -> ContextSummary:
        if not self.source_event_ids:
            raise PydanticCustomError(
                "context_summary_sources",
                "context summaries require at least one source event",
            )
        if len(self.source_event_ids) != len(set(self.source_event_ids)):
            raise PydanticCustomError(
                "context_summary_sources",
                "context summary source event IDs must be unique",
            )
        if self.occurred_to < self.occurred_from:
            raise PydanticCustomError(
                "context_summary_range",
                "context summary end cannot precede its start",
            )
        return self


class ConversationContext(FrozenContractModel):
    """Bounded working conversation selected for the current frame."""

    revision: _Revision
    captured_at: UTCDateTime
    conversation_id: Optional[_NonBlankText]
    messages: Tuple[ConversationMessage, ...]
    summaries: Tuple[ContextSummary, ...] = ()
    active_topic_messages: Tuple[ConversationMessage, ...] = ()


class CompletedConversationInteraction(FrozenContractModel):
    """Owner input and Elfie reply joined only by a completed delivery receipt."""

    channel_id: _NonBlankText
    conversation_id: _NonBlankText
    owner: ConversationMessage
    reply: ConversationMessage
    receipt_id: EventId


class PendingReplyProjection(FrozenContractModel):
    """Reply proposal persisted before execution and settled only by Receipt."""

    intent_id: IntentId
    channel_id: _NonBlankText
    conversation_id: _NonBlankText
    reply_event_id: EventId
    content: _NonBlankText
    cause_event_ids: Tuple[EventId, ...]
    prepared_at: UTCDateTime


class ConversationTopicCheckpoint(FrozenContractModel):
    """One active or receipt-pending topic inside a conversation partition."""

    thread_id: _NonBlankText
    lineage_id: _NonBlankText
    messages: Tuple[ConversationMessage, ...] = ()
    summaries: Tuple[ContextSummary, ...] = ()
    started_at: Optional[UTCDateTime] = None
    last_activity_at: Optional[UTCDateTime] = None
    close_after_event_id: Optional[EventId] = None
    participants: Tuple[_NonBlankText, ...] = ()


class ConversationThreadCheckpoint(FrozenContractModel):
    """Bounded messages for one concrete communication endpoint."""

    channel_id: _NonBlankText
    conversation_id: _NonBlankText
    messages: Tuple[ConversationMessage, ...] = ()
    summaries: Tuple[ContextSummary, ...] = ()
    active_topic: Optional[ConversationTopicCheckpoint] = None
    pending_topics: Tuple[ConversationTopicCheckpoint, ...] = ()


class ConversationContextCheckpoint(FrozenContractModel):
    """Persistence-neutral checkpoint for receipt-backed working history."""

    threads: Tuple[ConversationThreadCheckpoint, ...] = ()
    pending_replies: Tuple[PendingReplyProjection, ...] = ()
    pending_closed_episode_payloads: Tuple[str, ...] = ()


class BodyCapabilityDescriptor(FrozenContractModel):
    """Capabilities of the single body currently bound to the Elfie."""

    body_id: _NonBlankText
    body_generation: _Revision = 1
    capability_revision: _Revision
    sensors: Tuple[_NonBlankText, ...]
    actions: Tuple[_NonBlankText, ...]


class CapabilityDescriptor(FrozenContractModel):
    """One model-visible capability with its typed argument contract."""

    capability_id: _NonBlankText
    category: Literal["body", "world"]
    description: Optional[_NonBlankText] = None
    argument_schema: Mapping[str, JsonValue] = Field(default_factory=dict)


class ConnectedChannelDescriptor(FrozenContractModel):
    """Capabilities of one currently connected communication channel."""

    channel_id: _NonBlankText
    account_id: _NonBlankText
    capability_revision: _Revision
    content_kinds: Tuple[_NonBlankText, ...]
    authorized_conversation_ids: Tuple[_NonBlankText, ...] = ()


class EffectiveCapabilities(FrozenContractModel):
    """Current Body, semantic-world capabilities and communication endpoints."""

    revision: _Revision
    captured_at: UTCDateTime
    current_body: Optional[BodyCapabilityDescriptor]
    world_capabilities: Tuple[_NonBlankText, ...] = ()
    capability_catalog: Tuple[CapabilityDescriptor, ...] = ()
    connected_channels: Tuple[ConnectedChannelDescriptor, ...]

    @model_validator(mode="after")
    def validate_unique_channels(self) -> EffectiveCapabilities:
        channel_ids = tuple(channel.channel_id for channel in self.connected_channels)
        if len(set(channel_ids)) != len(channel_ids):
            raise PydanticCustomError(
                "duplicate_channel_id", "connected channel IDs must be unique"
            )
        capability_ids = tuple(
            descriptor.capability_id for descriptor in self.capability_catalog
        )
        if len(set(capability_ids)) != len(capability_ids):
            raise PydanticCustomError(
                "duplicate_capability_id",
                "capability catalog IDs must be unique",
            )
        return self


class BrainContext(FrozenContractModel):
    """Complete immutable input for one reasoning decision."""

    revision: _Revision
    constitution_version: _Revision = 1
    captured_at: UTCDateTime
    frame: TurnFrame
    emotion: EmotionSnapshot
    homeostasis: EnergySnapshot
    motivation: MotivationSnapshot = Field(default_factory=MotivationSnapshot.unknown)
    consolidation: CognitiveConsolidationSnapshot = Field(
        default_factory=CognitiveConsolidationSnapshot.unknown
    )
    conversation: ConversationContext
    memory: MemoryContext
    activities: ActivityContext = Field(default_factory=ActivityContext.unknown)
    capabilities: EffectiveCapabilities
    orientation: OrientationSnapshot = Field(
        default_factory=OrientationSnapshot.unknown
    )
    selfhood: SelfhoodPromptProjection = Field(
        default_factory=lambda: SelfhoodPromptProjection.unknown(
            captured_at=datetime.fromtimestamp(0, timezone.utc)
        )
    )

    @model_validator(mode="after")
    def validate_capture_boundary(self) -> BrainContext:
        captured_times = (
            self.frame.captured_at,
            self.emotion.captured_at,
            self.homeostasis.captured_at,
            self.motivation.captured_at,
            self.consolidation.captured_at,
            self.conversation.captured_at,
            self.memory.captured_at,
            self.activities.captured_at,
            self.capabilities.captured_at,
            self.orientation.captured_at,
            self.selfhood.captured_at,
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
    "CompletedConversationInteraction",
    "ContextSummary",
    "ConversationContext",
    "ConversationContextCheckpoint",
    "ConversationMessage",
    "ConversationTopicCheckpoint",
    "ConversationThreadCheckpoint",
    "EffectiveCapabilities",
    "PendingReplyProjection",
)
