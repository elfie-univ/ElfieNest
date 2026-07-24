from unittest.mock import MagicMock, patch

import pytest

from app.orchestration.engine import ElfieNestEngine
from elfie import Elfie
from nest import NestFullError


@pytest.fixture
def engine() -> ElfieNestEngine:
    with patch("app.orchestration.engine.GodotAPIServer"):
        return ElfieNestEngine(ws_port=18765)


@pytest.fixture
def mock_elfie() -> MagicMock:
    elfie = MagicMock(spec=Elfie)
    elfie.amygdala = MagicMock()
    elfie.amygdala.get_dominant_mood.return_value = "happy"
    return elfie


def test_engine_owns_nest_and_session(engine: ElfieNestEngine) -> None:
    assert engine.nest is not None
    assert engine.session.nest is engine.nest


def test_session_owns_real_elfie_instances(
    engine: ElfieNestEngine,
    mock_elfie: MagicMock,
) -> None:
    # Given / When
    engine.session.register_elfie("elfie-1", mock_elfie)

    # Then
    assert engine.session.elfies["elfie-1"] is mock_elfie
    assert engine.nest.resident_ids == ("elfie-1",)
    assert not hasattr(engine.nest.state, "elfies")


def test_session_ticks_only_active_elfies(
    engine: ElfieNestEngine,
    mock_elfie: MagicMock,
) -> None:
    # Given
    engine.session.register_elfie("elfie-1", mock_elfie)

    # When
    engine.session.tick_elfies(1.0)
    engine.nest.update_resident_posture("elfie-1", "away")
    engine.session.tick_elfies(1.0)

    # Then
    mock_elfie.advance_clock.assert_called_once_with(1.0)


def test_session_routes_collision_through_nest(
    engine: ElfieNestEngine,
) -> None:
    # Given / When
    engine.nest.register_resident("receiver")
    engine.session.trigger_elfie_interaction("sender", "receiver", "collision")
    tactile = engine.session.consume_tactile("receiver")

    # Then
    assert tactile["intensity"] == 0.25
    assert tactile["direction"] == "back"
    assert tactile["force_newtons_estimate"] == 1.5


def test_engine_capacity_is_enforced_by_nest(mock_elfie: MagicMock) -> None:
    # Given
    with patch("app.orchestration.engine.GodotAPIServer"):
        engine = ElfieNestEngine(max_elfies_per_room=1)
    engine.session.register_elfie("elfie-1", mock_elfie)

    # When / Then
    with pytest.raises(NestFullError, match="1/1"):
        engine.session.register_elfie(
            "elfie-2",
            MagicMock(spec=Elfie),
        )


def test_engine_configuration_is_preserved() -> None:
    # Given / When
    with patch("app.orchestration.engine.GodotAPIServer"):
        engine = ElfieNestEngine(
            tick_interval_sec=2.5,
            max_elfies_per_room=3,
        )

    # Then
    assert engine.tick_interval_sec == 2.5
    assert engine.nest.state.config.max_residents == 3
    assert not hasattr(engine, "_synthesize_voice")


def test_engine_initialization_does_not_create_repository_data_dir(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    with patch("app.orchestration.engine.GodotAPIServer"):
        ElfieNestEngine()

    assert not (tmp_path / "data").exists()
