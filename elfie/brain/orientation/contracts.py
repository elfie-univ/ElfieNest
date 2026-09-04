"""Immutable current self/world placement owned by Orientation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal, Optional, Tuple

from pydantic import Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError

from elfie.message_types import (
    ActorRef,
    EventId,
    FrozenContractModel,
    TurnId,
    UTCDateTime,
)

_NonBlankText = Annotated[
    str, StringConstraints(strict=True, min_length=1, pattern=r".*\S.*")
]
_Revision = Annotated[int, Field(strict=True, ge=0)]


class OrientationSnapshot(FrozenContractModel):
    """Current self/world placement with explicit unknown and provenance."""

    revision: _Revision
    captured_at: UTCDateTime
    current_turn_id: Optional[TurnId] = None
    body_id: Optional[_NonBlankText] = None
    body_generation: Optional[_Revision] = None
    location: Optional[_NonBlankText] = None
    location_source: Literal["runtime", "observation", "unknown"] = "unknown"
    position: Optional[Tuple[float, float, float]] = None
    heading_degrees: Optional[float] = None
    velocity: Optional[Tuple[float, float, float]] = None
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
        return cls(
            revision=0,
            captured_at=datetime.fromtimestamp(0, timezone.utc),
            location_source="unknown",
            unknown_fields=(
                "body",
                "location",
                "position",
                "heading",
                "velocity",
                "nearby_actors",
                "activity",
                "affordances",
            ),
            freshness="unknown",
        )

    @model_validator(mode="after")
    def validate_identity(self) -> OrientationSnapshot:
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
                "orientation_location_source", "known location must declare a source"
            )
        actor_ids = tuple(str(actor.actor_id) for actor in self.nearby_actors)
        if len(set(actor_ids)) != len(actor_ids):
            raise PydanticCustomError(
                "orientation_actor_identity", "nearby actor identities must be unique"
            )
        if len(set(self.source_event_ids)) != len(self.source_event_ids):
            raise PydanticCustomError(
                "orientation_source_identity",
                "orientation source event IDs must be unique",
            )
        return self


__all__ = ("OrientationSnapshot",)
