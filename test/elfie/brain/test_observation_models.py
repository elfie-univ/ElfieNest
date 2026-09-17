"""Typed brain-observation envelope, status/error models and sink contract."""

import threading
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from elfie.brain.observation import (
    BrainObservation,
    BrainObservationSink,
    NoOpSink,
    ObservationError,
    ObservationStatus,
)
from elfie.message_types import FrozenContractModel

CAPTURED_AT = datetime(2026, 9, 7, 0, 0, tzinfo=timezone.utc)


class _AppraisalPayload(FrozenContractModel):
    """Named payload model standing in for one boundary's observation."""

    stimulus: str
    intensity: float


_AppraisalObservation = BrainObservation[_AppraisalPayload]


def _full_observation() -> _AppraisalObservation:
    return _AppraisalObservation(
        schema_version=1,
        boundary="emotion",
        kind="appraisal",
        sequence=7,
        captured_at=CAPTURED_AT,
        turn_id="turn-1",
        frame_id="frame-1",
        cause_event_ids=("evt-1", "evt-2"),
        duration_ms=12.5,
        status=ObservationStatus.completed,
        error=None,
        payload=_AppraisalPayload(stimulus="fish", intensity=0.8),
    )


def _minimal_observation(**overrides: object) -> BrainObservation:
    fields: dict = {
        "boundary": "emotion",
        "kind": "appraisal",
        "sequence": 1,
        "captured_at": "2026-09-07T00:00:00Z",
        "turn_id": "turn-1",
        "frame_id": "frame-1",
        "status": ObservationStatus.completed,
        "payload": None,
    }
    fields.update(overrides)
    return BrainObservation(**fields)


def test_full_envelope_roundtrips_through_model_dump_and_validate() -> None:
    observation = _full_observation()

    restored = _AppraisalObservation.model_validate(observation.model_dump())

    assert restored == observation
    assert restored.schema_version == 1
    assert restored.boundary == "emotion"
    assert restored.kind == "appraisal"
    assert restored.sequence == 7
    assert restored.captured_at == CAPTURED_AT
    assert restored.turn_id == "turn-1"
    assert restored.frame_id == "frame-1"
    assert restored.cause_event_ids == ("evt-1", "evt-2")
    assert restored.duration_ms == 12.5
    assert restored.status is ObservationStatus.completed
    assert restored.error is None
    assert restored.payload == _AppraisalPayload(stimulus="fish", intensity=0.8)


def test_envelope_is_frozen() -> None:
    observation = _full_observation()

    with pytest.raises(ValidationError, match="frozen"):
        observation.sequence = 8


def test_captured_at_accepts_iso_utc_string_and_rejects_non_utc() -> None:
    observation = _minimal_observation()

    assert observation.captured_at == CAPTURED_AT

    with pytest.raises(ValidationError, match="utc_datetime"):
        _minimal_observation(captured_at="2026-09-07T00:00:00+09:00")


def test_status_enum_exposes_lifecycle_values() -> None:
    assert {status.value for status in ObservationStatus} == {
        "completed",
        "failed",
        "skipped",
        "degraded",
    }


def test_observation_error_carries_type_and_sanitized_message() -> None:
    error = ObservationError(type="ModelCallError", message="provider timeout")

    assert error.type == "ModelCallError"
    assert error.message == "provider timeout"
    with pytest.raises(ValidationError, match="frozen"):
        error.message = "changed"


def test_failed_envelope_with_error_roundtrips() -> None:
    observation = _AppraisalObservation(
        boundary="reasoning.agent_loop",
        kind="model_call",
        sequence=9,
        captured_at=CAPTURED_AT,
        turn_id="turn-1",
        frame_id="frame-1",
        cause_event_ids=("evt-3",),
        duration_ms=2500.0,
        status=ObservationStatus.failed,
        error=ObservationError(type="ModelCallError", message="provider timeout"),
        payload=_AppraisalPayload(stimulus="fish", intensity=0.8),
    )

    restored = _AppraisalObservation.model_validate(observation.model_dump())

    assert restored.status is ObservationStatus.failed
    assert restored.error is not None
    assert restored.error.type == "ModelCallError"
    assert restored.error.message == "provider timeout"


def test_noop_sink_never_raises_and_snapshot_stays_empty() -> None:
    sink = NoOpSink()

    sink.emit(_full_observation())
    sink.emit(_minimal_observation())

    assert isinstance(sink, BrainObservationSink)
    assert sink.snapshot() == ()


def test_collector_satisfies_sink_protocol_structurally() -> None:
    class _Collector:
        """Minimal structural implementation of the sink protocol."""

        def __init__(self) -> None:
            self._events: list = []

        def emit(self, event: BrainObservation) -> None:
            self._events.append(event)

        def snapshot(self) -> tuple:
            return tuple(self._events)

    collector = _Collector()
    observation = _full_observation()

    assert isinstance(collector, BrainObservationSink)
    collector.emit(observation)
    assert collector.snapshot() == (observation,)


def test_noop_sink_is_safe_under_concurrent_emit() -> None:
    sink = NoOpSink()
    observation = _full_observation()

    def _hammer() -> None:
        for _ in range(200):
            sink.emit(observation)

    threads = [threading.Thread(target=_hammer) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sink.snapshot() == ()
