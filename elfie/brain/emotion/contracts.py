"""Typed facts and projections owned by the Emotion system."""

from __future__ import annotations

from enum import Enum, unique
from typing import Annotated, Literal, Optional, Tuple

from pydantic import Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError

from elfie.brain.emotion.emotion_types import EmotionType
from elfie.message_types import EventId, FrozenContractModel, UTCDateTime

_NonBlankText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, pattern=r".*\S.*"),
]
_Ratio = Annotated[float, Field(strict=True, ge=0.0, le=1.0)]
_PositiveRatio = Annotated[float, Field(strict=True, gt=0.0, le=1.0)]
_Strength = Annotated[int, Field(strict=True, ge=1, le=100)]


@unique
class AffectDirection(str, Enum):
    """Semantic direction returned by a fast or slow appraisal."""

    INCREASE = "increase"
    DECREASE = "decrease"


@unique
class AppraisalRelevance(str, Enum):
    """Host-owned relationship between one cause and Elfie's own state."""

    DIRECT = "direct"
    INDIRECT = "indirect"


class ChannelEffect(FrozenContractModel):
    """One channel's semantic effect; programs calculate the numeric delta."""

    channel: EmotionType
    direction: AffectDirection
    strength: _Strength
    confidence: _PositiveRatio = 1.0


class TrustedAppraisalScope(FrozenContractModel):
    """A host-signed cause that a fast or slow appraisal may select."""

    scope_id: _NonBlankText
    cause_event_id: EventId
    relevance: AppraisalRelevance
    related_actor_id: Optional[_NonBlankText] = None
    relationship_revision: Optional[Annotated[int, Field(strict=True, ge=0)]] = None
    relationship_weight: _Ratio = 1.0

    @model_validator(mode="after")
    def validate_relationship_binding(self) -> TrustedAppraisalScope:
        if self.relevance is AppraisalRelevance.DIRECT:
            if (
                self.related_actor_id is not None
                or self.relationship_revision is not None
            ):
                raise PydanticCustomError(
                    "direct_appraisal_relationship",
                    "direct appraisal scopes cannot carry a relationship binding",
                )
            if self.relationship_weight != 1.0:
                raise PydanticCustomError(
                    "direct_appraisal_weight",
                    "direct appraisal scopes must use relationship weight 1",
                )
        elif self.related_actor_id is None or self.relationship_revision is None:
            raise PydanticCustomError(
                "indirect_appraisal_relationship",
                "indirect appraisal scopes require a bound actor and relationship revision",
            )
        return self


class AffectiveAppraisal(FrozenContractModel):
    """One sparse set of Elfie effects bound to a trusted host scope."""

    scope: TrustedAppraisalScope
    effects: Annotated[Tuple[ChannelEffect, ...], Field(min_length=1, max_length=6)]
    reason: Optional[_NonBlankText] = None

    @model_validator(mode="after")
    def validate_unique_channels(self) -> AffectiveAppraisal:
        channels = tuple(effect.channel for effect in self.effects)
        if len(channels) != len(set(channels)):
            raise PydanticCustomError(
                "duplicate_appraisal_channel",
                "one appraisal may affect each emotion channel at most once",
            )
        return self


class EmotionValue(FrozenContractModel):
    """One named normalized absolute stock value."""

    name: EmotionType
    intensity: _Ratio


class EmotionSnapshot(FrozenContractModel):
    """The complete six-channel state plus a sparse derived description."""

    revision: Annotated[int, Field(strict=True, ge=0)]
    captured_at: UTCDateTime
    values: Annotated[Tuple[EmotionValue, ...], Field(min_length=6, max_length=6)]
    active: Annotated[Tuple[EmotionValue, ...], Field(max_length=3)] = ()
    primary: Optional[EmotionType] = None
    secondary: Optional[EmotionType] = None
    trends: Tuple[Tuple[EmotionType, Literal["rising", "falling"]], ...] = ()
    source_event_ids: Tuple[EventId, ...] = ()
    freshness: Literal["current", "stale", "unknown"] = "current"

    @classmethod
    def inactive(
        cls,
        *,
        captured_at: UTCDateTime,
        revision: int = 0,
        freshness: Literal["current", "stale", "unknown"] = "current",
    ) -> EmotionSnapshot:
        """Build a complete six-channel snapshot with no active emotion."""

        return cls(
            revision=revision,
            captured_at=captured_at,
            values=tuple(
                EmotionValue(name=emotion, intensity=0.0) for emotion in EmotionType
            ),
            freshness=freshness,
        )

    @model_validator(mode="after")
    def validate_complete_state(self) -> EmotionSnapshot:
        names = tuple(item.name for item in self.values)
        if set(names) != set(EmotionType) or len(set(names)) != 6:
            raise PydanticCustomError(
                "emotion_snapshot_channels",
                "emotion snapshot must contain each of the six channels exactly once",
            )
        active_names = tuple(item.name for item in self.active)
        if len(active_names) != len(set(active_names)):
            raise PydanticCustomError(
                "emotion_snapshot_active_channels",
                "active emotion channels must be unique",
            )
        return self


__all__ = (
    "AffectDirection",
    "AffectiveAppraisal",
    "AppraisalRelevance",
    "ChannelEffect",
    "EmotionSnapshot",
    "EmotionValue",
    "TrustedAppraisalScope",
)
