"""Immutable read and state contracts owned by the Memory system."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal, Mapping, Optional, Tuple, cast

from pydantic import Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from elfie.brain.memory.memory_records import (
    JsonValue,
    RecallAssertion,
    RecallBundle,
    RecallConflict,
    RecallEpisode,
    RecallEvidence,
    RecallLimits,
    RecallNode,
    RecallPath,
)
from elfie.message_types import EventId, FrozenContractModel, UTCDateTime

_Revision = Annotated[int, Field(strict=True, ge=0)]


class MemoryStateSnapshot(FrozenContractModel):
    """Versioned durable-memory projection beside retrieved excerpts."""

    revision: _Revision
    captured_at: UTCDateTime
    episodic_count: _Revision
    total_count: _Revision
    source_event_ids: Tuple[EventId, ...] = ()
    snapshot_freshness: Literal["current", "stale", "unknown"] = "current"

    @classmethod
    def unknown(cls) -> MemoryStateSnapshot:
        return cls(
            revision=0,
            captured_at=datetime.fromtimestamp(0, timezone.utc),
            episodic_count=0,
            total_count=0,
            snapshot_freshness="unknown",
        )

    @model_validator(mode="after")
    def validate_counts(self) -> MemoryStateSnapshot:
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
        if (
            self.revision == 0
            and self.total_count == 0
            and self.snapshot_freshness != "unknown"
        ):
            raise PydanticCustomError(
                "memory_state_revision",
                "revision zero memory state must be marked unknown",
            )
        return self


class MemoryContext(FrozenContractModel):
    """Bounded, lossless RecallBundle selected for one reasoning turn."""

    revision: _Revision
    captured_at: UTCDateTime
    # ``RecallBundle`` contains a recursive JSON value alias.  Pydantic would
    # recursively expand that alias while building this outer contract.  The
    # runtime validator still seals the field to the exact typed bundle, while
    # ``object`` lets Pydantic serialize the frozen dataclass losslessly.
    recall: object = Field(default_factory=RecallBundle)
    state: MemoryStateSnapshot = Field(default_factory=MemoryStateSnapshot.unknown)
    # Monotonic MemorySystem revision for binding a model's explicit use
    # proposal to the exact Recall snapshot that supplied its IDs.
    recall_revision: _Revision = 0

    @field_validator("recall", mode="before")
    @classmethod
    def validate_recall_bundle(cls, value: object) -> RecallBundle:
        if isinstance(value, Mapping):
            raw = cast(Mapping[str, object], value)
            return RecallBundle(
                focus_nodes=tuple(
                    _recall_node(cast(Mapping[str, object], item))
                    for item in cast(tuple[object, ...], raw.get("focus_nodes", ()))
                ),
                assertions=tuple(
                    _recall_assertion(cast(Mapping[str, object], item))
                    for item in cast(tuple[object, ...], raw.get("assertions", ()))
                ),
                paths=tuple(
                    _recall_path(cast(Mapping[str, object], item))
                    for item in cast(tuple[object, ...], raw.get("paths", ()))
                ),
                episodes=tuple(
                    _recall_episode(cast(Mapping[str, object], item))
                    for item in cast(tuple[object, ...], raw.get("episodes", ()))
                ),
                evidence=tuple(
                    _recall_evidence(cast(Mapping[str, object], item))
                    for item in cast(tuple[object, ...], raw.get("evidence", ()))
                ),
                conflicts=tuple(
                    _recall_conflict(cast(Mapping[str, object], item))
                    for item in cast(tuple[object, ...], raw.get("conflicts", ()))
                ),
                limits=_recall_limits(
                    cast(Mapping[str, object], raw.get("limits", {}))
                ),
            )
        if not isinstance(value, RecallBundle):
            raise TypeError("memory recall must be a RecallBundle")
        return value

    @model_validator(mode="after")
    def validate_state_cutoff(self) -> MemoryContext:
        if self.state.captured_at > self.captured_at:
            raise PydanticCustomError(
                "memory_state_captured_at",
                "memory state cannot be newer than MemoryContext",
            )
        return self


__all__ = ("MemoryContext", "MemoryStateSnapshot")


def _recall_node(raw: Mapping[str, object]) -> RecallNode:
    return RecallNode(
        node_id=str(raw["node_id"]),
        node_type=str(raw["node_type"]),
        label=str(raw["label"]),
        description=_optional_text(raw.get("description")),
        relevance=_as_float(raw["relevance"]),
        importance=_as_float(raw.get("importance", 0.5)),
        confidence=_as_float(raw.get("confidence", 0.5)),
        properties=cast(Mapping[str, JsonValue], raw.get("properties", {})),
    )


def _recall_assertion(raw: Mapping[str, object]) -> RecallAssertion:
    return RecallAssertion(
        assertion_id=str(raw["assertion_id"]),
        subject_id=str(raw["subject_id"]),
        predicate=str(raw["predicate"]),
        object_node_id=_optional_text(raw.get("object_node_id")),
        object_literal=cast(Optional[JsonValue], raw.get("object_literal")),
        qualifiers=cast(Mapping[str, JsonValue], raw.get("qualifiers", {})),
        status=str(raw["status"]),
        evidence_ids=_string_tuple(raw.get("evidence_ids", ())),
        relevance=_as_float(raw["relevance"]),
        importance=_as_float(raw.get("importance", 0.5)),
        confidence=_as_float(raw.get("confidence", 0.5)),
    )


def _recall_path(raw: Mapping[str, object]) -> RecallPath:
    return RecallPath(
        node_ids=_string_tuple(raw.get("node_ids", ())),
        assertion_ids=_string_tuple(raw.get("assertion_ids", ())),
        hop_count=_as_int(raw["hop_count"]),
    )


def _recall_episode(raw: Mapping[str, object]) -> RecallEpisode:
    return RecallEpisode(
        episode_id=str(raw["episode_id"]),
        occurred_from=_optional_text(raw.get("occurred_from")),
        occurred_to=_optional_text(raw.get("occurred_to")),
        excerpt=str(raw["excerpt"]),
        detail_level=str(raw["detail_level"]),
        relevance=_as_float(raw["relevance"]),
        occurrence_precision=cast(
            Literal["exact", "range", "unknown"],
            raw.get("occurrence_precision", "exact"),
        ),
        life_stage=_optional_text(raw.get("life_stage")),
        temporal_label=_optional_text(raw.get("temporal_label")),
        importance=_as_float(raw.get("importance", 0.5)),
        source_event_ids=_string_tuple(raw.get("source_event_ids", ())),
    )


def _recall_evidence(raw: Mapping[str, object]) -> RecallEvidence:
    return RecallEvidence(
        evidence_id=str(raw["evidence_id"]),
        source_id=str(raw["source_id"]),
        excerpt=_optional_text(raw.get("excerpt")),
        media_locator=_optional_text(raw.get("media_locator")),
        stance=str(raw["stance"]),
        source_type=str(raw.get("source_type", "episode")),
        source_version=_optional_text(raw.get("source_version")),
        modality=str(raw.get("modality", "text")),
        span_start=_optional_int(raw.get("span_start")),
        span_end=_optional_int(raw.get("span_end")),
        speaker=_optional_text(raw.get("speaker")),
        viewpoint=_optional_text(raw.get("viewpoint")),
        captured_at=_optional_text(raw.get("captured_at")),
        attribution=cast(
            Optional[Literal["observed", "told", "inferred", "felt"]],
            raw.get("attribution"),
        ),
    )


def _recall_conflict(raw: Mapping[str, object]) -> RecallConflict:
    return RecallConflict(
        assertion_ids=_string_tuple(raw.get("assertion_ids", ())),
        reason=str(raw["reason"]),
    )


def _recall_limits(raw: Mapping[str, object]) -> RecallLimits:
    return RecallLimits(
        requested=cast(Mapping[str, int], raw.get("requested", {})),
        returned=cast(Mapping[str, int], raw.get("returned", {})),
        truncated=bool(raw.get("truncated", False)),
    )


def _string_tuple(value: object) -> Tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise TypeError("expected a sequence of strings")
    return tuple(str(item) for item in value)


def _optional_text(value: object) -> Optional[str]:
    return None if value is None else str(value)


def _optional_int(value: object) -> Optional[int]:
    return None if value is None else _as_int(value)


def _as_float(value: object) -> float:
    return float(str(value))


def _as_int(value: object) -> int:
    return int(str(value))
