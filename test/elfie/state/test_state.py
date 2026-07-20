from pathlib import Path

import pytest

from elfie.state import ElfieState, ElfieStateRepository


def test_state_yaml_round_trip(tmp_path: Path) -> None:
    state = ElfieState(
        energy=72.5,
        fatigue=31.0,
        is_sleeping=True,
        emotions={"joy": 64.0, "fear": 12.5},
        elapsed_time=123.25,
        current_body_id="native-main",
    )
    repository = ElfieStateRepository(tmp_path)

    assert repository.save(state) == tmp_path / "state.yaml"
    assert repository.load() == state
    assert not (tmp_path / "state.yaml.tmp").exists()


def test_state_rejects_invalid_emotion_value() -> None:
    with pytest.raises(ValueError, match=r"\[0, 100\]"):
        ElfieState(emotions={"joy": 101.0}).validate()
