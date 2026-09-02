from __future__ import annotations

from pathlib import Path

import pytest

from devtools.brain_eval.gates import evaluate_p0_gates
from devtools.brain_eval.lab_runner import (
    LabFixtureDefinition,
    LabScenarioDefinition,
    LabScenarioStep,
    LabStepAction,
    capture_lab_episode,
)
from infrastructure.persistence.layout.data_home import get_elfie_home


def test_capture_runs_the_real_brain_with_isolated_lab_state(tmp_path: Path) -> None:
    fixture = LabFixtureDefinition(
        fixture_id="anchor-elfie",
        elfie_id="00001001",
        name="小榛",
        species_id="fox",
        age_years=2.0,
        description="Brain evaluation anchor",
        appearance_description="red fox",
        personality_description="curious, warm and independent",
    )
    scenario = LabScenarioDefinition(
        scenario_family_id="p0-response-scope",
        scenario_version="1.0.0",
        variant_id="communication-wave-request",
        seed=11,
        hidden=False,
        steps=(
            LabScenarioStep(
                action=LabStepAction.TURN,
                source_domain="communication",
                message="回复我的同时挥挥手。",
            ),
        ),
    )

    episode = capture_lab_episode(
        candidate_id="candidate",
        candidate_spec_sha256="d" * 64,
        fixture=fixture,
        scenario=scenario,
        food_key="mock",
        runtime_root=tmp_path / "runtime",
    )

    assert episode.candidate_id == "candidate"
    assert episode.turns
    assert episode.public_outputs
    assert episode.resources.model_calls == 1
    assert evaluate_p0_gates((episode,)) == ()
    assert not (tmp_path / "production").exists()


def test_capture_rejects_every_path_inside_production_data_root() -> None:
    fixture = LabFixtureDefinition(
        fixture_id="anchor-elfie",
        elfie_id="00001001",
        name="小榛",
        species_id="fox",
        age_years=2.0,
        description="Brain evaluation anchor",
        appearance_description="red fox",
        personality_description="curious, warm and independent",
    )
    scenario = LabScenarioDefinition(
        scenario_family_id="p0-response-scope",
        scenario_version="1.0.0",
        variant_id="communication-wave-request",
        seed=11,
        hidden=False,
        steps=(
            LabScenarioStep(
                action=LabStepAction.TURN,
                source_domain="communication",
                message="回复我。",
            ),
        ),
    )

    with pytest.raises(ValueError, match="production ELFIE_HOME"):
        capture_lab_episode(
            candidate_id="candidate",
            candidate_spec_sha256="d" * 64,
            fixture=fixture,
            scenario=scenario,
            food_key="mock",
            runtime_root=get_elfie_home() / "brain-eval-forbidden",
        )
