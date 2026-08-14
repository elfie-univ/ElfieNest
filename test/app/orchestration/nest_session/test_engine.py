from unittest.mock import MagicMock

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
