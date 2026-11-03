from datetime import datetime, timezone

from app.orchestration.nest_session import ElfieNestEngine
from infrastructure.persistence.configuration.settings import RuntimeSettingsAdapter
from nest.public import LifePhase
from test.app.orchestration.nest_session.fakes import FakeWorldRuntime


def test_running_engine_reloads_saved_daylight_without_restarting(tmp_path):
    adapter = RuntimeSettingsAdapter(tmp_path / "configs" / "runtime.yaml")
    current = datetime(2026, 11, 3, 23, tzinfo=timezone.utc)
    engine = ElfieNestEngine(
        FakeWorldRuntime(),
        local_time=lambda: current,
        environment_schedule=adapter.load_environment_settings,
    )
    assert engine.nest.life_phase is LifePhase.DUSK
    adapter.save_environment_settings(
        adapter.load_environment_settings().model_copy(update={"rest_time": "22:00"})
    )
    engine.tick_once(1.5)
    assert engine.nest.life_phase is LifePhase.NIGHT
    assert engine.nest.desired_environment.quiet_mode
    assert engine.nest.elapsed_seconds == 1.5
