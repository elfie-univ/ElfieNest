"""Typed contracts for the two-layer Selfhood state.

Selfhood is deliberately independent from ``Profile`` and ``Canon`` after the
Genesis hand-off.  The durable state has one envelope and exactly two semantic
layers: creation-frozen ``identity_core`` and slowly changing
``adaptive_self``.  Prompt text is a derived projection and is never stored.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal, Optional, Tuple

from pydantic import Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError

from elfie.message_types import EventId, FrozenContractModel, UTCDateTime

_NonBlankText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=512, pattern=r".*\S.*"),
]
_OptionalText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=512, pattern=r".*\S.*"),
]
_ProjectionText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=4096, pattern=r".*\S.*"),
]
_Revision = Annotated[int, Field(strict=True, ge=0)]
_Ratio = Annotated[float, Field(strict=True, ge=0.0, le=1.0)]

_FIXED_HEADER_LABELS = (
    "[APPLICATION_FRAME]",
    "[IDENTITY_CORE]",
    "[ADAPTIVE_SELF]",
    "[OPERATING_CONTRACT]",
    "[TURN_PROTOCOL]",
    "[CURRENT_BRAIN_STATE]",
)


class BigFiveTraits(FrozenContractModel):
    """Internal bounded personality vector; never render its raw values."""

    openness: _Ratio = 0.5
    conscientiousness: _Ratio = 0.5
    extraversion: _Ratio = 0.5
    agreeableness: _Ratio = 0.5
    neuroticism: _Ratio = 0.5


class IdentityCore(FrozenContractModel):
    """Creation-frozen individual facts owned by Selfhood."""

    elfie_id: Optional[_OptionalText] = None
    display_name: Optional[_OptionalText] = None
    species_id: Optional[_OptionalText] = None
    species_name: Optional[_OptionalText] = None
    resident_role: Optional[_OptionalText] = None

    @property
    def complete(self) -> bool:
        """Whether Genesis supplied the minimum stable identity facts."""

        required = (
            self.elfie_id,
            self.display_name,
            self.species_id,
            self.species_name,
            self.resident_role,
        )
        return all(value is not None for value in required)

    @model_validator(mode="after")
    def validate_text(self) -> IdentityCore:
        _validate_data_texts(self.model_dump().values())
        return self


class AdaptiveSelf(FrozenContractModel):
    """Slow, bounded personal tendencies; automatic growth is phase-gated."""

    big_five: BigFiveTraits = Field(default_factory=BigFiveTraits)
    interaction_tendency_ids: Tuple[_NonBlankText, ...] = ()
    coping_tendency_ids: Tuple[_NonBlankText, ...] = ()
    expression_tendency_ids: Tuple[_NonBlankText, ...] = ()
    value_ids: Tuple[_NonBlankText, ...] = ()
    speech_marker_ids: Tuple[_NonBlankText, ...] = ()
    source_event_ids: Tuple[EventId, ...] = ()

    @model_validator(mode="after")
    def validate_collections(self) -> AdaptiveSelf:
        collections = (
            self.interaction_tendency_ids,
            self.coping_tendency_ids,
            self.expression_tendency_ids,
            self.value_ids,
            self.speech_marker_ids,
        )
        if any(len(values) > 8 for values in collections):
            raise PydanticCustomError(
                "selfhood_tendency_limit",
                "Selfhood tendency collections must contain at most eight values",
            )
        if len(set(self.source_event_ids)) != len(self.source_event_ids):
            raise PydanticCustomError(
                "selfhood_source_identity", "selfhood source event IDs must be unique"
            )
        _validate_data_texts(item for values in collections for item in values)
        return self


class SelfhoodState(FrozenContractModel):
    """One atomic Selfhood snapshot with exactly two semantic layers."""

    state_schema_version: Literal[1] = 1
    revision: _Revision
    committed_at: UTCDateTime
    identity_core: IdentityCore
    adaptive_self: AdaptiveSelf

    @classmethod
    def unknown(cls, *, committed_at: UTCDateTime | None = None) -> SelfhoodState:
        return cls(
            revision=0,
            committed_at=committed_at or datetime.fromtimestamp(0, timezone.utc),
            identity_core=IdentityCore(),
            adaptive_self=AdaptiveSelf(),
        )

    @property
    def complete(self) -> bool:
        return self.identity_core.complete

    # These read-only views keep diagnostics and existing Brain owners narrow;
    # they are not serialized fields and cannot become a second state source.
    @property
    def big_five(self) -> BigFiveTraits:
        return self.adaptive_self.big_five

    @property
    def species_name(self) -> str | None:
        return self.identity_core.species_name

    @property
    def norms(self) -> Tuple[str, ...]:
        return self.adaptive_self.value_ids

    @property
    def speech_style(self) -> SelfhoodSpeechStyle:
        return SelfhoodSpeechStyle(
            greetings=(),
            verbal_tick=(
                self.adaptive_self.speech_marker_ids[0]
                if self.adaptive_self.speech_marker_ids
                else None
            ),
        )

    @property
    def self_description(self) -> str | None:
        if not self.complete:
            return None
        core = self.identity_core
        return (
            f"我是 {core.display_name}，正式物种是 {core.species_name}，"
            f"现在是 ElfieNest 的{core.resident_role}。"
        )

    @property
    def identity_facts(self) -> Tuple[str, ...]:
        core = self.identity_core
        facts = []
        if core.display_name:
            facts.append(f"我的名字是 {core.display_name}。")
        if core.species_name:
            facts.append(f"正式物种名是 {core.species_name}。")
        if core.resident_role:
            facts.append(f"我现在是 ElfieNest 的{core.resident_role}。")
        return tuple(facts)

    @property
    def behavior_anchors(self) -> Tuple[str, ...]:
        return self.adaptive_self.interaction_tendency_ids

    @property
    def sensory_biases(self) -> Tuple[str, ...]:
        return self.adaptive_self.coping_tendency_ids

    @property
    def species_knowledge(self) -> Tuple[str, ...]:
        return ()

    @property
    def knowledge_boundaries(self) -> Tuple[str, ...]:
        return ()


class SelfhoodPromptProjection(FrozenContractModel):
    """Deterministic model-facing Selfhood text, rebuilt on every Turn."""

    revision: _Revision
    captured_at: UTCDateTime
    identity_core_text: _ProjectionText
    adaptive_self_text: _ProjectionText

    @classmethod
    def unknown(cls, *, captured_at: UTCDateTime) -> SelfhoodPromptProjection:
        """Construct an explicit unavailable marker for non-model diagnostics."""

        return cls(
            revision=0,
            captured_at=captured_at,
            identity_core_text="Selfhood identity is unavailable.",
            adaptive_self_text="Selfhood adaptive state is unavailable.",
        )

    @model_validator(mode="after")
    def validate_projection(self) -> SelfhoodPromptProjection:
        _validate_texts((self.identity_core_text, self.adaptive_self_text))
        return self


class SelfhoodSpeechStyle(FrozenContractModel):
    """Narrow diagnostic view retained for non-prompt callers."""

    greetings: Tuple[_NonBlankText, ...] = ()
    verbal_tick: Optional[_NonBlankText] = None


def _validate_texts(values) -> None:
    for value in values:
        if not isinstance(value, str):
            continue
        if any(ord(char) < 32 and char not in "\n\t" for char in value):
            raise PydanticCustomError(
                "selfhood_control_character",
                "Selfhood text cannot contain control characters",
            )
        if any(label in value for label in _FIXED_HEADER_LABELS):
            raise PydanticCustomError(
                "selfhood_reserved_header",
                "Selfhood text cannot contain fixed-header labels",
            )


def _validate_data_texts(values) -> None:
    """Validate stored data slots before the renderer quotes them."""

    for value in values:
        if not isinstance(value, str):
            continue
        if any(ord(char) < 32 for char in value):
            raise PydanticCustomError(
                "selfhood_data_control_character",
                "Selfhood data cannot contain control characters",
            )
        if any(delimiter in value for delimiter in ("〈", "〉", "[/", "<|", "|>")):
            raise PydanticCustomError(
                "selfhood_data_delimiter",
                "Selfhood data cannot contain prompt delimiters",
            )
        if any(label in value for label in _FIXED_HEADER_LABELS):
            raise PydanticCustomError(
                "selfhood_reserved_header",
                "Selfhood text cannot contain fixed-header labels",
            )


def normalize_selfhood_mapping(raw) -> dict:
    """Normalize YAML sequence containers before strict typed validation.

    Runtime contracts stay strict tuples; this tiny boundary helper is the
    only place where the YAML list representation is accepted.
    """

    data = dict(raw)
    adaptive = data.get("adaptive_self")
    if isinstance(adaptive, dict):
        adaptive = dict(adaptive)
        for field in (
            "interaction_tendency_ids",
            "coping_tendency_ids",
            "expression_tendency_ids",
            "value_ids",
            "speech_marker_ids",
            "source_event_ids",
        ):
            value = adaptive.get(field)
            if isinstance(value, list):
                adaptive[field] = tuple(value)
        data["adaptive_self"] = adaptive
    return data


__all__ = (
    "AdaptiveSelf",
    "BigFiveTraits",
    "IdentityCore",
    "SelfhoodPromptProjection",
    "SelfhoodSpeechStyle",
    "SelfhoodState",
    "normalize_selfhood_mapping",
)
