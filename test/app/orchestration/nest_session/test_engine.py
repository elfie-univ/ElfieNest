from threading import Thread
from unittest.mock import MagicMock

import pytest

from app.orchestration.nest_session import ElfieNestEngine
from elfie import Elfie
from test.app.orchestration.nest_session.fakes import FakeWorldRuntime


def test_engine_owns_one_nest_and_live_session() -> None:
    engine = ElfieNestEngine(FakeWorldRuntime())

    assert engine.session.nest is engine.nest


def test_session_owns_real_elfies_and_ticks_only_active_residents() -> None:
    engine = ElfieNestEngine(FakeWorldRuntime())
    elfie = MagicMock(spec=Elfie)

    engine.session.register_elfie("elfie-1", elfie)
    engine.session.tick_elfies(1.0)
    engine.nest.update_resident_posture("elfie-1", "away")
    engine.session.tick_elfies(1.0)

    assert engine.session.get_elfie("elfie-1") is elfie
    assert engine.nest.resident_ids == ("elfie-1",)
    elfie.advance_clock.assert_called_once_with(1.0)


def test_tick_drains_world_events_before_advancing_time() -> None:
    runtime = FakeWorldRuntime()
    engine = ElfieNestEngine(runtime)

    engine.tick_once(2.5)

    assert engine.nest.elapsed_seconds == 2.5


def test_unbounded_engine_loop_runs_until_an_explicit_stop() -> None:
    engine = ElfieNestEngine(FakeWorldRuntime(), tick_interval_sec=0.001)
    thread = Thread(
        target=engine.start_loop,
        kwargs={
            "model_port_factory": lambda _elfie_id: MagicMock(),
            "ticks_to_run": None,
        },
    )

    thread.start()
    try:
        assert engine.wait_until_running(timeout=1.0) is True
        assert engine.is_running is True
        assert thread.is_alive() is True
    finally:
        engine.request_stop()
        thread.join(timeout=1.0)

    assert thread.is_alive() is False
    assert engine.is_running is False


def test_engine_health_turns_false_after_the_loop_crashes() -> None:
    engine = ElfieNestEngine(FakeWorldRuntime())
    engine.tick_once = MagicMock(side_effect=RuntimeError("tick failed"))

    with pytest.raises(RuntimeError, match="tick failed"):
        engine.start_loop(
            lambda _elfie_id: MagicMock(),
            ticks_to_run=1,
            interval_sec=0.0,
        )

    assert engine.is_running is False


def test_engine_progress_records_completed_ticks_and_duration() -> None:
    engine = ElfieNestEngine(FakeWorldRuntime())

    engine.start_loop(
        lambda _elfie_id: MagicMock(),
        ticks_to_run=2,
        interval_sec=0.0,
    )

    progress = engine.progress_snapshot()
    assert progress.completed_ticks == 2
    assert progress.loop_started_at is not None
    assert progress.last_tick_started_at is not None
    assert progress.last_tick_completed_at is not None
    assert progress.last_tick_duration_seconds is not None
    assert progress.last_tick_duration_seconds >= 0.0
    assert engine.progress_age_seconds() is not None


def test_engine_loop_has_no_regression_at_the_previous_100000_tick_boundary() -> None:
    engine = ElfieNestEngine(FakeWorldRuntime())
    engine.tick_once = MagicMock()

    engine.start_loop(
        lambda _elfie_id: MagicMock(),
        ticks_to_run=100_001,
        interval_sec=0.0,
    )

    assert engine.progress_snapshot().completed_ticks == 100_001
    assert engine.tick_once.call_count == 100_001
