"""Lifecycle admission guarantees for the product NestSession."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.orchestration.nest_session import ElfieNestEngine
from elfie import Elfie
from elfie.communication import InboundDisposition, InboundDispositionStatus
from elfie.message_types import EventId
from test.app.orchestration.nest_session.fakes import FakeWorldRuntime


@pytest.fixture
def engine() -> ElfieNestEngine:
    return ElfieNestEngine(FakeWorldRuntime())


def _mock_elfie() -> MagicMock:
    elfie = MagicMock(spec=Elfie)
    elfie.cognition_configured = True
    elfie.is_running = True
    return elfie


def test_registering_after_session_start_starts_elfie_before_return(
    engine: ElfieNestEngine,
) -> None:
    engine.session.start_elfies()
    elfie = _mock_elfie()

    engine.session.register_elfie("late-elfie", elfie)

    elfie.start.assert_called_once_with()
    assert engine.session.get_elfie("late-elfie") is elfie


def test_starting_registered_elfies_is_idempotent(engine: ElfieNestEngine) -> None:
    elfie = _mock_elfie()
    engine.session.register_elfie("elfie-1", elfie)

    engine.session.start_elfies()
    engine.session.start_elfies()

    elfie.start.assert_called_once_with()


def test_registering_during_stop_is_rejected_without_persistence(
    engine: ElfieNestEngine,
) -> None:
    engine.session.start_elfies()
    engine.session.stop_elfies()
    engine.session.join_elfies()

    with pytest.raises(RuntimeError, match="stopped"):
        engine.session.register_elfie("late-elfie", _mock_elfie())

    assert engine.session.get_elfie("late-elfie") is None
    assert engine.nest.resident_state("late-elfie") is None


def test_failed_late_start_rolls_back_registry_and_resident(
    engine: ElfieNestEngine,
) -> None:
    engine.session.start_elfies()
    elfie = _mock_elfie()
    elfie.start.side_effect = RuntimeError("cognitive runtime failed")

    with pytest.raises(RuntimeError, match="cognitive runtime failed"):
        engine.session.register_elfie("late-elfie", elfie)

    assert engine.session.get_elfie("late-elfie") is None
    assert engine.nest.resident_state("late-elfie") is None


def test_start_failure_stops_already_started_elfies(engine: ElfieNestEngine) -> None:
    first = _mock_elfie()
    second = _mock_elfie()
    second.start.side_effect = RuntimeError("second runtime failed")
    engine.session.register_elfie("first", first)
    engine.session.register_elfie("second", second)

    with pytest.raises(RuntimeError, match="second runtime failed"):
        engine.session.start_elfies()

    first.stop.assert_called_once_with()
    first.join.assert_called_once_with()


def test_elfie_items_snapshot_is_stable_during_later_admission(
    engine: ElfieNestEngine,
) -> None:
    engine.session.register_elfie("first", _mock_elfie())
    initial = engine.session.elfie_items_snapshot()

    engine.session.register_elfie("second", _mock_elfie())

    assert tuple(elfie_id for elfie_id, _ in initial) == ("first",)


def test_owner_message_catches_up_brain_clock_for_inactive_resident(
    engine: ElfieNestEngine,
) -> None:
    elfie = _mock_elfie()
    elfie.elapsed_time = 3.0
    elfie.receive_communication_envelope.return_value = InboundDisposition(
        status=InboundDispositionStatus.ACCEPTED,
        message_id=EventId("owner:owner-message-1"),
        channel_id="godot-owner",
    )
    engine.session.register_elfie("elfie-1", elfie)
    engine.nest.tick(10.0)
    engine.nest.update_resident_posture("elfie-1", "away")

    engine.session.send_user_message("elfie-1", "你好")

    elfie.advance_clock.assert_called_once_with(7.0)
    assert elfie.receive_communication_envelope.call_count == 1
