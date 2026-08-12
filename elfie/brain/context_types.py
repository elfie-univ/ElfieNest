"""Immutable context snapshots assembled for one cortical turn."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal, Optional, Tuple

from pydantic import Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError

from elfie.brain.perception_types import TurnFrame
from elfie.message_types import (
    ActorRef,
    EventId,
    FrozenContractModel,
    TurnId,
    UTCDateTime,
)

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
    source_event_ids: Tuple[EventId, ...] = ()
    freshness: Literal["current", "stale", "unknown"] = "current"


class HomeostasisSnapshot(FrozenContractModel):
    """Energy and fatigue captured after timestamp-driven advancement."""

    revision: _Revision
    captured_at: UTCDateTime
    energy: _Percent
    fatigue: _Percent
    sleeping: bool
    cognitive_mode: Literal["normal", "long", "degraded", "emergency"] = "normal"
    long_reasoning_allowed: bool = False
    available_cognitive_budget: _Percent = 0.0


class MotivationSnapshot(FrozenContractModel):
    """Bounded fixed-drive state captured for one cortical turn."""

    revision: _Revision
    captured_at: UTCDateTime
    recovery_pressure: _Ratio
    recovery_status: Literal["ready", "blocked", "cooldown", "satisfied", "unknown"] = (
        "unknown"
    )
    last_trigger_id: Optional[EventId] = None
    cooldown_until: Optional[UTCDateTime] = None
    satisfaction_until: Optional[UTCDateTime] = None

    @classmethod
    def unknown(cls) -> MotivationSnapshot:
        """Return an explicit unknown drive state for isolated context tests."""
        return cls(
            revision=0,
            captured_at=datetime.fromtimestamp(0, timezone.utc),
            recovery_pressure=0.0,
            recovery_status="unknown",
        )


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
    state: MemoryStateSnapshot = Field(
        default_factory=lambda: MemoryStateSnapshot.unknown()
    )

    @model_validator(mode="after")
    def validate_state_cutoff(self) -> MemoryContext:
        """Keep durable memory state inside this retrieval's cutoff."""
        if self.state.captured_at > self.captured_at:
            raise PydanticCustomError(
                "memory_state_captured_at",
                "memory state cannot be newer than MemoryContext",
            )
        return self


class MemoryStateSnapshot(FrozenContractModel):
    """Versioned durable-memory projection used beside retrieved excerpts."""

    revision: _Revision
    captured_at: UTCDateTime
    episodic_count: _Revision
    total_count: _Revision
    source_event_ids: Tuple[EventId, ...] = ()
    freshness: Literal["current", "stale", "unknown"] = "current"

    @classmethod
    def unknown(cls) -> MemoryStateSnapshot:
        """Return an explicit unknown state for isolated context tests."""
        return cls(
            revision=0,
            captured_at=datetime.fromtimestamp(0, timezone.utc),
            episodic_count=0,
            total_count=0,
            freshness="unknown",
        )

    @model_validator(mode="after")
    def validate_counts(self) -> MemoryStateSnapshot:
        """Reject impossible durable-memory counts and duplicate provenance."""
        if self.episodic_count > self.total_count:
            raise PydanticCustomError(
                "memory_state_counts",
                "episodic memory count cannot exceed total memory count",
            )
        if len(set(self.source_event_ids)) != len(self.source_event_ids):
            raise PydanticCustomError(
                "memory_state_source_identity",
                "memory state source event IDs must be unique",
            )
        if self.revision == 0 and self.total_count == 0 and self.freshness != "unknown":
            raise PydanticCustomError(
                "memory_state_revision",
                "revision zero memory state must be marked unknown",
            )
        return self


class OrientationSnapshot(FrozenContractModel):
    """Current self/world placement with explicit unknown and provenance fields."""

    revision: _Revision
    captured_at: UTCDateTime
    current_turn_id: Optional[TurnId] = None
    body_id: Optional[_NonBlankText] = None
    body_generation: Optional[_Revision] = None
    location: Optional[_NonBlankText] = None
    location_source: Literal["runtime", "observation", "unknown"] = "unknown"
    active_channel_id: Optional[_NonBlankText] = None
    active_conversation_id: Optional[_NonBlankText] = None
    nearby_actors: Tuple[ActorRef, ...] = ()
    activity_id: Optional[_NonBlankText] = None
    affordances: Tuple[_NonBlankText, ...] = ()
    source_event_ids: Tuple[EventId, ...] = ()
    unknown_fields: Tuple[_NonBlankText, ...] = ()
    freshness: Literal["current", "stale", "unknown"] = "current"

    @classmethod
    def unknown(cls) -> OrientationSnapshot:
        """Return a safe empty snapshot for callers without an orientation owner."""
        return cls(
            revision=0,
            captured_at=datetime.fromtimestamp(0, timezone.utc),
            location_source="unknown",
            unknown_fields=(
                "body",
                "location",
                "nearby_actors",
                "activity",
                "affordances",
            ),
            freshness="unknown",
        )

    @model_validator(mode="after")
    def validate_identity(self) -> OrientationSnapshot:
        """Keep paired identities and provenance internally coherent."""
        if (self.body_id is None) != (self.body_generation is None):
            raise PydanticCustomError(
                "orientation_body_identity",
                "body_id and body_generation must be provided together",
            )
        if (self.active_channel_id is None) != (self.active_conversation_id is None):
            raise PydanticCustomError(
                "orientation_conversation_identity",
                "channel and conversation must be provided together",
            )
        if self.location is None and self.location_source != "unknown":
            raise PydanticCustomError(
                "orientation_location_source",
                "unknown location must use the unknown source",
            )
        if self.location is not None and self.location_source == "unknown":
            raise PydanticCustomError(
                "orientation_location_source",
                "known location must declare a source",
            )
        actor_ids = tuple(str(actor.actor_id) for actor in self.nearby_actors)
        if len(set(actor_ids)) != len(actor_ids):
            raise PydanticCustomError(
                "orientation_actor_identity",
                "nearby actor identities must be unique",
            )
        if len(set(self.source_event_ids)) != len(self.source_event_ids):
            raise PydanticCustomError(
                "orientation_source_identity",
                "orientation source event IDs must be unique",
            )
        return self


class BigFiveTraits(FrozenContractModel):
    """The bounded personality tendencies owned by Brain Selfhood."""

    openness: _Ratio = 0.5
    conscientiousness: _Ratio = 0.5
    extraversion: _Ratio = 0.5
    agreeableness: _Ratio = 0.5
    neuroticism: _Ratio = 0.5


class SelfhoodSpeechStyle(FrozenContractModel):
    """Small expressive preferences that are safe to project into a Turn."""

    greetings: Tuple[_NonBlankText, ...] = ()
    verbal_tick: Optional[_NonBlankText] = None


class SelfhoodDerivation(FrozenContractModel):
    """Initialization evidence retained by Selfhood, not by Profile identity."""

    preset: Optional[_NonBlankText] = None
    matched_keywords: Tuple[_NonBlankText, ...] = ()
    provenance: Optional[_NonBlankText] = None
    overridden_traits: Tuple[_NonBlankText, ...] = ()
    seed: Optional[int] = Field(default=None, strict=True)


class SelfhoodSnapshot(FrozenContractModel):
    """Versioned mutable self-model anchored to the immutable Profile."""

    revision: _Revision
    captured_at: UTCDateTime
    profile_revision: _Revision
    big_five: BigFiveTraits
    self_description: Optional[_NonBlankText] = None
    speech_style: SelfhoodSpeechStyle = Field(default_factory=SelfhoodSpeechStyle)
    derivation: SelfhoodDerivation = Field(default_factory=SelfhoodDerivation)
    norms: Tuple[_NonBlankText, ...] = ()
    source_event_ids: Tuple[EventId, ...] = ()
    unknown_fields: Tuple[_NonBlankText, ...] = ()
    freshness: Literal["current", "stale", "unknown"] = "current"

    @classmethod
    def unknown(cls) -> SelfhoodSnapshot:
        """Return a neutral snapshot for context sources without Selfhood wiring."""
        return cls(
            revision=0,
            captured_at=datetime.fromtimestamp(0, timezone.utc),
            profile_revision=0,
            big_five=BigFiveTraits(),
            unknown_fields=("personality", "self_description", "speech_style", "norms"),
            freshness="unknown",
        )

    @model_validator(mode="after")
    def validate_provenance(self) -> SelfhoodSnapshot:
        """Reject duplicate source identities in a Selfhood snapshot."""
        if len(set(self.source_event_ids)) != len(self.source_event_ids):
            raise PydanticCustomError(
                "selfhood_source_identity",
                "selfhood source event IDs must be unique",
            )
        if self.profile_revision == 0 and self.freshness != "unknown":
            raise PydanticCustomError(
                "selfhood_profile_revision",
                "unknown profile anchors require unknown Selfhood freshness",
            )
        return self


class ProfileAnchorSnapshot(FrozenContractModel):
    """Immutable identity/appearance facts projected from Profile into Brain."""

    revision: _Revision
    captured_at: UTCDateTime
    elfie_id: Optional[_NonBlankText] = None
    display_name: Optional[_NonBlankText] = None
    species_id: Optional[_NonBlankText] = None
    appearance_seed: Optional[int] = Field(default=None, strict=True)
    appearance_genome_version: Optional[_Revision] = None
    primary_morphology: Optional[_NonBlankText] = None
    unknown_fields: Tuple[_NonBlankText, ...] = ()

    @classmethod
    def unknown(cls) -> ProfileAnchorSnapshot:
        """Return an explicit empty anchor for isolated Brain tests."""
        return cls(
            revision=0,
            captured_at=datetime.fromtimestamp(0, timezone.utc),
            unknown_fields=("identity", "appearance", "embodiment"),
        )

    @model_validator(mode="after")
    def validate_identity(self) -> ProfileAnchorSnapshot:
        """Keep the stable identity projection all-or-nothing."""
        identity_values = (self.elfie_id, self.display_name, self.species_id)
        if any(value is not None for value in identity_values) and not all(
            value is not None for value in identity_values
        ):
            raise PydanticCustomError(
                "profile_anchor_identity",
                "profile identity anchors must be complete",
            )
        if self.revision == 0 and any(value is not None for value in identity_values):
            raise PydanticCustomError(
                "profile_anchor_revision",
                "unknown profile anchors cannot contain identity values",
            )
        return self


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
    motivation: MotivationSnapshot = Field(default_factory=MotivationSnapshot.unknown)
    conversation: ConversationContext
    memory: MemoryContext
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
        """Prevent snapshots captured after the context cutoff from leaking in."""
        captured_times = (
            self.frame.captured_at,
            self.emotion.captured_at,
            self.homeostasis.captured_at,
            self.motivation.captured_at,
            self.conversation.captured_at,
            self.memory.captured_at,
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
    "EmotionSnapshot",
    "EmotionValue",
    "BigFiveTraits",
    "HomeostasisSnapshot",
    "MotivationSnapshot",
    "MemoryContext",
    "MemoryItem",
    "MemoryStateSnapshot",
    "OrientationSnapshot",
    "ProfileAnchorSnapshot",
    "SelfhoodSnapshot",
    "SelfhoodDerivation",
    "SelfhoodSpeechStyle",
)
