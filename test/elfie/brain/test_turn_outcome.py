"""Contract tests for minimal turn outcomes and workspace ports."""

from datetime import datetime, timezone
from typing import Optional

import pytest
from pydantic import ValidationError

from elfie.brain.perception_types import (
    IngestDisposition,
    IngestReceipt,
    PerceptionEvent,
    PerceptionFrame,
)
from elfie.brain.turn_outcome import (
    ModelMode,
    TerminalStatus,
    TurnOutcome,
)
from elfie.brain.workspace_ports import PerceptionFrameSource, PerceptionSink
from elfie.message_types import EventId, PlanId, TurnId

NOW = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)


def test_completed_outcome_round_trip_keeps_only_terminal_evidence() -> None:
    # Given: the minimal evidence required to close a successful turn.
    outcome = TurnOutcome(
        turn_id=TurnId("turn-1"),
        frame_id=EventId("frame-1"),
        plan_id=PlanId("plan-1"),
        status=TerminalStatus.COMPLETED,
        model_mode=ModelMode.TEXT_FALLBACK,
        fallback_reason="structured decode failed",
        timeout_reason=None,
        stale_reason=None,
        error_code=None,
        receipt_ids=(EventId("receipt-1"), EventId("receipt-2")),
    )

    # When: outcome evidence crosses JSON.
    restored = TurnOutcome.model_validate_json(outcome.model_dump_json())

    # Then: only stable IDs and terminal facts remain.
    assert restored == outcome
    assert "prompt" not in TurnOutcome.model_fields
    assert "stage_trace" not in TurnOutcome.model_fields


def test_timed_out_outcome_requires_timeout_reason() -> None:
    # Given: a timed-out status without its terminal reason.
    # When / Then: the incomplete evidence is rejected.
    with pytest.raises(ValidationError, match="timeout_reason"):
        TurnOutcome(
            turn_id=TurnId("turn-1"),
            frame_id=EventId("frame-1"),
            plan_id=PlanId("plan-1"),
            status=TerminalStatus.TIMED_OUT,
            model_mode=ModelMode.NO_OP,
            fallback_reason=None,
            timeout_reason=None,
            stale_reason=None,
            error_code=None,
            receipt_ids=(),
        )


def test_outcome_rejects_rich_trace_fields() -> None:
    # Given: a caller tries to turn the outcome into a rich debug trace.
    raw = {
        "turn_id": "turn-1",
        "frame_id": "frame-1",
        "plan_id": "plan-1",
        "status": "completed",
        "model_mode": "structured",
        "fallback_reason": None,
        "timeout_reason": None,
        "stale_reason": None,
        "error_code": None,
        "receipt_ids": [],
        "stage_trace": ["prompt", "decode"],
    }

    # When / Then: the closed minimal model rejects trace expansion.
    with pytest.raises(ValidationError, match="stage_trace"):
        TurnOutcome.model_validate(raw)


class _PortExample:
    def publish(self, item: PerceptionEvent) -> IngestReceipt:
        return IngestReceipt(
            event_id=item.meta.event_id,
            disposition=IngestDisposition.ACCEPTED,
            ingest_seq=1,
            retryable=False,
            reason=None,
        )

    def seal(self, *, reason: str, captured_at: datetime) -> Optional[EventId]:
        del reason, captured_at
        return None

    def claim(self, frame_id: EventId, turn_id: TurnId) -> PerceptionFrame:
        raise LookupError(frame_id, turn_id)

    def commit(self, frame_id: EventId, turn_id: TurnId) -> None:
        del frame_id, turn_id

    def release(self, frame_id: EventId, turn_id: TurnId, reason: str) -> None:
        del frame_id, turn_id, reason


def test_workspace_protocols_are_structural_without_queue_members() -> None:
    # Given: a structural implementation exposing only boundary operations.
    port = _PortExample()

    # When: runtime-checkable protocols inspect the implementation.
    supports_sink = isinstance(port, PerceptionSink)
    supports_source = isinstance(port, PerceptionFrameSource)

    # Then: no queue/storage inheritance or attributes are required.
    assert supports_sink is True
    assert supports_source is True
    assert not hasattr(port, "queue")
