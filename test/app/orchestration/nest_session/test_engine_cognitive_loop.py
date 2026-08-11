from unittest.mock import MagicMock, patch

from app.orchestration.nest_session import ElfieNestEngine
from elfie import Elfie
from elfie.brain.runtime_port import ModelPort
from test.app.orchestration.nest_session.fakes import FakeWorldRuntime


def test_start_loop_uses_injected_model_port_factory_for_resident_elfies() -> None:
    runtime = FakeWorldRuntime()
    engine = ElfieNestEngine(runtime)
    elfie = MagicMock(spec=Elfie)
    elfie.is_running = True
    elfie.cognition_configured = False
    engine.session.register_elfie("elfie-1", elfie)
    model_port = MagicMock(spec=ModelPort)

    with patch("app.orchestration.nest_session.engine.time.sleep"):
        engine.start_loop(
            lambda elfie_id: model_port,
            ticks_to_run=1,
            interval_sec=0.0,
        )

    elfie.configure_cognition.assert_called_once_with(model_port)
    elfie.start.assert_called_once_with()
    elfie.stop.assert_called_once_with()
    elfie.join.assert_called_once_with()
