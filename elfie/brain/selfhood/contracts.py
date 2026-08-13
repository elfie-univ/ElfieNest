"""Immutable identity anchors and mutable self-model contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal, Optional, Tuple

from pydantic import Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError

from elfie.message_types import EventId, FrozenContractModel, UTCDateTime

_NonBlankText = Annotated[
    str, StringConstraints(strict=True, min_length=1, pattern=r".*\S.*")
]
_Revision = Annotated[int, Field(strict=True, ge=0)]
_Ratio = Annotated[float, Field(strict=True, ge=0.0, le=1.0)]


class BigFiveTraits(FrozenContractModel):
    openness: _Ratio = 0.5
    conscientiousness: _Ratio = 0.5
    extraversion: _Ratio = 0.5
    agreeableness: _Ratio = 0.5
    neuroticism: _Ratio = 0.5


class SelfhoodSpeechStyle(FrozenContractModel):
    greetings: Tuple[_NonBlankText, ...] = ()
    verbal_tick: Optional[_NonBlankText] = None


class SelfhoodDerivation(FrozenContractModel):
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
        if len(set(self.source_event_ids)) != len(self.source_event_ids):
            raise PydanticCustomError(
                "selfhood_source_identity", "selfhood source event IDs must be unique"
            )
        if self.profile_revision == 0 and self.freshness != "unknown":
            raise PydanticCustomError(
                "selfhood_profile_revision",
                "unknown profile anchors require unknown Selfhood freshness",
            )
        return self


class ProfileAnchorSnapshot(FrozenContractModel):
    """Immutable identity/appearance facts projected into Selfhood context."""

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
        return cls(
            revision=0,
            captured_at=datetime.fromtimestamp(0, timezone.utc),
            unknown_fields=("identity", "appearance", "embodiment"),
        )

    @model_validator(mode="after")
    def validate_identity(self) -> ProfileAnchorSnapshot:
        identity_values = (self.elfie_id, self.display_name, self.species_id)
        if any(value is not None for value in identity_values) and not all(
            value is not None for value in identity_values
        ):
            raise PydanticCustomError(
                "profile_anchor_identity", "profile identity anchors must be complete"
            )
        if self.revision == 0 and any(value is not None for value in identity_values):
            raise PydanticCustomError(
                "profile_anchor_revision",
                "unknown profile anchors cannot contain identity values",
            )
        return self


__all__ = (
    "BigFiveTraits",
    "ProfileAnchorSnapshot",
    "SelfhoodDerivation",
    "SelfhoodSnapshot",
    "SelfhoodSpeechStyle",
)
