"""Activity-boundary observations from the real Preflight service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Lock

from elfie.brain.activity.observation_payloads import (
    ActivityPreflightVerdictObservation,
)
from elfie.brain.activity.preflight import ActivityPreflightService
from elfie.brain.activity.system import InMemoryActivityStore
from elfie.brain.observation import BrainObservation
from elfie.brain.reasoning.context_types import (
    ConnectedChannelDescriptor,
    EffectiveCapabilities,
)
from test.elfie.brain.activity.test_activity import _draft

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


class CollectorSink:
    def __init__(self) -> None:
        self._lock = Lock()
        self._events: list[BrainObservation] = []

    def emit(self, event: BrainObservation) -> None:
        with self._lock:
            self._events.append(event)

    def snapshot(self) -> tuple[BrainObservation, ...]:
        with self._lock:
            return tuple(self._events)

    def of(self, boundary: str, kind: str) -> tuple[BrainObservation, ...]:
        return tuple(
            event
            for event in self.snapshot()
            if event.boundary == boundary and event.kind == kind
        )


def _service(
    observation_sink: CollectorSink,
    *,
    target_resolved: bool = True,
    budget: float = 10.0,
) -> ActivityPreflightService:
    capabilities = EffectiveCapabilities(
        revision=0,
        captured_at=NOW,
        current_body=None,
        connected_channels=(
            ConnectedChannelDescriptor(
                channel_id="elfie",
                account_id="owner-account",
                capability_revision=1,
                content_kinds=("text",),
                authorized_conversation_ids=("owner",),
            ),
        ),
    )
    return ActivityPreflightService(
        store=InMemoryActivityStore(),
        clock=lambda: NOW,
        capabilities=lambda: capabilities,
        available_budget=lambda: budget,
        target_resolver=lambda *_args: target_resolved,
        observation_sink=observation_sink,
    )


def _single_verdict(sink: CollectorSink) -> ActivityPreflightVerdictObservation:
    events = sink.of("activity", "preflight_verdict")
    assert len(events) == 1
    payload = events[0].payload
    assert isinstance(payload, ActivityPreflightVerdictObservation)
    return payload


def test_validated_preflight_emits_the_verdict_with_issued_evidence() -> None:
    sink = CollectorSink()
    service = _service(sink)
    draft = _draft(wake_at=NOW + timedelta(minutes=30))

    result = service.preflight(draft)

    assert result.status.value == "validated"
    payload = _single_verdict(sink)
    assert payload.activity_id == "activity-1"
    assert payload.status == "validated"
    assert payload.reason_codes == ()
    assert payload.evidence_issued is True
    assert payload.step_count == 1
    assert payload.estimated_budget == 0.0


def test_unresolved_target_emits_the_clarification_verdict() -> None:
    sink = CollectorSink()
    service = _service(sink, target_resolved=False)

    result = service.preflight(_draft())

    assert result.status.value == "needs_clarification"
    payload = _single_verdict(sink)
    assert payload.status == "needs_clarification"
    assert payload.reason_codes == ("activity_target_unresolved",)
    assert payload.evidence_issued is False


def test_exhausted_budget_emits_the_rejected_verdict() -> None:
    sink = CollectorSink()
    service = _service(sink, budget=-1.0)

    result = service.preflight(_draft())

    assert result.status.value == "rejected"
    payload = _single_verdict(sink)
    assert payload.status == "rejected"
    assert payload.reason_codes == ("activity_budget_unavailable",)
    assert payload.evidence_issued is False
