from pathlib import Path

from app.orchestration.lifecycle import ModelOverallState
from infrastructure.models.model_health_projection import (
    FoodModelHealthProjectionAdapter,
)


def test_model_projection_does_not_create_data_or_validation_files_for_a_fresh_root(
    tmp_path: Path,
) -> None:
    home = tmp_path / "elfie-home"

    projection = FoodModelHealthProjectionAdapter(home).read()

    assert projection.state is ModelOverallState.UNCONFIGURED
    assert projection.common_state is ModelOverallState.UNCONFIGURED
    assert projection.emergency_state is ModelOverallState.UNAVAILABLE
    assert not home.exists()
