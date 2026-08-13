"""Reasoning-owned composition contracts for one immutable Brain turn.

Each mental system owns its own snapshot contract.  This module owns only
conversation working context, effective capability projection, and the final
cross-system context capsule consumed by Reasoning.
"""

from __future__ import annotations

from typing import Annotated, Optional, Tuple

from pydantic import Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError

from elfie.brain.activity.context import ActivityContext
from elfie.brain.consolidation.contracts import CognitiveConsolidationSnapshot
from elfie.brain.emotion.contracts import EmotionSnapshot
from elfie.brain.energy.contracts import EnergySnapshot
from elfie.brain.memory.contracts import MemoryContext
from elfie.brain.motivation.contracts import MotivationSnapshot
from elfie.brain.orientation.contracts import OrientationSnapshot
from elfie.brain.selfhood.contracts import ProfileAnchorSnapshot, SelfhoodSnapshot
from elfie.brain.workspace.contracts import TurnFrame
from elfie.message_types import ActorRef, EventId, FrozenContractModel, UTCDateTime

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


class ConversationContext(FrozenContractModel):
    """Bounded working conversation selected for the current frame."""

    revision: _Revision
    captured_at: UTCDateTime
    conversation_id: Optional[_NonBlankText]
    messages: Tuple[ConversationMessage, ...]


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
    """Only the current Body and connected communication endpoints."""

    revision: _Revision
    captured_at: UTCDateTime
    current_body: Optional[BodyCapabilityDescriptor]
    connected_channels: Tuple[ConnectedChannelDescriptor, ...]

    @model_validator(mode="after")
    def validate_unique_channels(self) -> EffectiveCapabilities:
        channel_ids = tuple(channel.channel_id for channel in self.connected_channels)
        if len(set(channel_ids)) != len(channel_ids):
            raise PydanticCustomError(
                "duplicate_channel_id", "connected channel IDs must be unique"
            )
        return self


class BrainContext(FrozenContractModel):
    """Complete immutable input for one reasoning decision."""

    revision: _Revision
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
    selfhood: SelfhoodSnapshot = Field(default_factory=SelfhoodSnapshot.unknown)
    profile_anchors: ProfileAnchorSnapshot = Field(
        default_factory=ProfileAnchorSnapshot.unknown
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
            self.profile_anchors.captured_at,
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
)
