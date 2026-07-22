"""Tests for shared cross-module message primitives."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from elfie.message_types import (
    ActorId,
    ActorRef,
    CorrelationId,
    ErrorInfo,
    EventId,
    MediaId,
    MediaRef,
    MessageMeta,
    Priority,
    TraceId,
)


def _valid_meta() -> MessageMeta:
    occurred_at = datetime(2026, 7, 21, 8, 15, tzinfo=timezone.utc)
    return MessageMeta(
        event_id=EventId("event-001"),
        elfie_id="elfie-001",
        source=ActorRef(
            actor_id=ActorId("actor-001"),
            source_kind="owner",
            display_name="主人",
        ),
        occurred_at=occurred_at,
        received_at=occurred_at + timedelta(milliseconds=25),
        trace_id=TraceId("trace-001"),
        causation_id=EventId("event-000"),
        correlation_id=CorrelationId("conversation-001"),
        priority=Priority.HIGH,
    )


def test_message_meta_round_trip_preserves_identity_and_utc_time() -> None:
    # Given
    meta = _valid_meta()

    # When
    restored = MessageMeta.model_validate_json(meta.model_dump_json())

    # Then
    assert restored == meta
    assert restored.occurred_at.tzinfo is timezone.utc
    assert restored.causation_id == EventId("event-000")
    assert restored.correlation_id == CorrelationId("conversation-001")
    assert restored.priority is Priority.HIGH


def test_contract_models_and_nested_collections_are_frozen() -> None:
    # Given
    error = ErrorInfo(
        code="transport_timeout",
        message="transport did not acknowledge the command",
        causes=(ErrorInfo(code="socket_closed", message="socket closed"),),
    )

    # When / Then
    with pytest.raises(ValidationError, match="frozen"):
        error.code = "changed"
    assert isinstance(error.causes, tuple)


def test_media_ref_uses_a_strict_frozen_boundary() -> None:
    # Given
    media = MediaRef(
        media_id=MediaId("media-001"),
        uri="elfie-media://capture/media-001",
        mime_type="image/png",
        size_bytes=128,
        sha256="a" * 64,
    )

    # When / Then
    assert MediaRef.model_validate_json(media.model_dump_json()) == media
    with pytest.raises(ValidationError, match="frozen"):
        media.uri = "elfie-media://capture/changed"


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("event_id", ""),
        ("event_id", "   "),
        ("elfie_id", "\t"),
        ("trace_id", " trace-001 "),
    ],
)
def test_message_meta_rejects_empty_or_whitespace_ids(
    field_name: str,
    invalid_value: str,
) -> None:
    # Given
    fields = _valid_meta().model_dump()
    fields[field_name] = invalid_value

    # When / Then
    with pytest.raises(ValidationError):
        MessageMeta.model_validate(fields)


@pytest.mark.parametrize(
    "invalid_time",
    [
        datetime(2026, 7, 21, 8, 15),
        datetime(2026, 7, 21, 8, 15, tzinfo=timezone(timedelta(hours=8))),
    ],
)
def test_message_meta_rejects_naive_or_non_utc_datetime(
    invalid_time: datetime,
) -> None:
    # Given
    fields = _valid_meta().model_dump()
    fields["occurred_at"] = invalid_time

    # When / Then
    with pytest.raises(ValidationError):
        MessageMeta.model_validate(fields)


def test_message_meta_rejects_unknown_fields() -> None:
    # Given
    fields = _valid_meta().model_dump()
    fields["metadata"] = {"escape_hatch": True}

    # When / Then
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        MessageMeta.model_validate(fields)


def test_message_meta_rejects_unsupported_schema_version() -> None:
    # Given
    fields = _valid_meta().model_dump()
    fields["schema_version"] = 2

    # When / Then
    with pytest.raises(ValidationError):
        MessageMeta.model_validate(fields)


def test_message_meta_rejects_loose_python_values() -> None:
    # Given
    fields = _valid_meta().model_dump()
    fields["priority"] = "high"

    # When / Then
    with pytest.raises(ValidationError):
        MessageMeta.model_validate(fields)
