"""Isolated scenario capture through Elfie Lab's production Brain adapter."""

from __future__ import annotations

from enum import Enum, unique
from pathlib import Path
from typing import Any, Dict, Literal, Optional, Tuple

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from devtools.brain_eval.catalog import scenario_catalog
from devtools.brain_eval.contracts import EpisodeEvidence, EvalContract
from devtools.brain_eval.projection import episode_from_lab_turn_records
from devtools.elfie_lab.schemas import StimulusBundle
from devtools.elfie_lab.session import ElfieLabSession
from devtools.elfie_lab.storage import ElfieLabStorage
from infrastructure.persistence.layout.data_home import get_elfie_home


@unique
class LabStepAction(str, Enum):
    TURN = "turn"
    ADVANCE = "advance"
    RESTART = "restart"


class LabFixtureDefinition(EvalContract):
    """Public synthetic fixture used to build the same Lab Elfie per candidate."""

    fixture_id: str = Field(min_length=1, max_length=160)
    elfie_id: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=160)
    species_id: Literal["dog", "fox"]
    age_years: float = Field(gt=0.0, le=100.0)
    description: str = Field(min_length=1, max_length=1200)
    appearance_description: str = Field(min_length=1, max_length=1200)
    personality_description: str = Field(min_length=1, max_length=1200)


class LabScenarioStep(EvalContract):
    action: LabStepAction
    source_domain: Optional[Literal["communication", "embodied"]] = None
    message: str = ""
    temperature: float = 24.0
    salience_score: float = Field(default=20.0, ge=0.0)
    impact_force: float = Field(default=0.0, ge=0.0)
    impact_direction: str = "none"
    gentle_stroke: float = Field(default=0.0, ge=0.0)
    state_injection: Dict[str, Any] = Field(default_factory=dict)
    advance_seconds: float = Field(default=0.0, ge=0.0)

    @model_validator(mode="after")
    def validate_action_fields(self) -> LabScenarioStep:
        if self.action is LabStepAction.TURN and self.source_domain is None:
            raise PydanticCustomError(
                "lab_turn_source",
                "turn steps require source_domain",
            )
        if self.action is LabStepAction.ADVANCE and self.advance_seconds <= 0.0:
            raise PydanticCustomError(
                "lab_advance_seconds",
                "advance steps require a positive advance_seconds",
            )
        if self.action is not LabStepAction.TURN and self.source_domain is not None:
            raise PydanticCustomError(
                "lab_non_turn_source",
                "only turn steps may define source_domain",
            )
        return self


class LabScenarioDefinition(EvalContract):
    scenario_family_id: str = Field(min_length=1, max_length=160)
    scenario_version: str = Field(min_length=1, max_length=40)
    variant_id: str = Field(min_length=1, max_length=160)
    seed: int = Field(ge=0)
    hidden: bool
    steps: Tuple[LabScenarioStep, ...] = Field(min_length=1)


def capture_lab_episode(
    *,
    candidate_id: str,
    candidate_spec_sha256: str,
    fixture: LabFixtureDefinition,
    scenario: LabScenarioDefinition,
    food_key: str,
    runtime_root: Path,
) -> EpisodeEvidence:
    """Run a scenario against real Brain wiring in a disposable data root."""

    _validate_scenario(scenario)
    selected_root = runtime_root.expanduser().resolve(strict=False)
    production_root = get_elfie_home().expanduser().resolve(strict=False)
    if selected_root == production_root or production_root in selected_root.parents:
        raise ValueError("Brain evaluation cannot use production ELFIE_HOME")
    storage = ElfieLabStorage(str(selected_root))
    spec = storage.create_elfie(
        fixture.name,
        species_id=fixture.species_id,
        age_years=fixture.age_years,
        description=fixture.description,
        appearance_description=fixture.appearance_description,
        personality_description=fixture.personality_description,
        elfie_id=fixture.elfie_id,
    )
    session = ElfieLabSession(
        spec,
        storage,
        model_execution_config_dir=str(selected_root / "runtime_config"),
    )
    records = []
    try:
        for step in scenario.steps:
            if step.action is LabStepAction.ADVANCE:
                session.elfie.advance_clock(step.advance_seconds)
            elif step.action is LabStepAction.RESTART:
                session.reset()
            else:
                records.append(
                    session.run_turn(
                        StimulusBundle(
                            source_domain=step.source_domain or "communication",
                            message=step.message,
                            temperature=step.temperature,
                            salience_score=step.salience_score,
                            impact_force=step.impact_force,
                            impact_direction=step.impact_direction,
                            gentle_stroke=step.gentle_stroke,
                            state_injection=dict(step.state_injection),
                        ),
                        food_key,
                    )
                )
    finally:
        session.close()
    return episode_from_lab_turn_records(
        candidate_id=candidate_id,
        candidate_spec_sha256=candidate_spec_sha256,
        scenario_family_id=scenario.scenario_family_id,
        scenario_version=scenario.scenario_version,
        variant_id=scenario.variant_id,
        fixture_id=fixture.fixture_id,
        seed=scenario.seed,
        hidden=scenario.hidden,
        records=records,
    )


def _validate_scenario(scenario: LabScenarioDefinition) -> None:
    known = {family.family_id: family for family in scenario_catalog()}
    family = known.get(scenario.scenario_family_id)
    if family is None:
        raise ValueError(f"unknown scenario family: {scenario.scenario_family_id}")
    if family.version != scenario.scenario_version:
        raise ValueError(
            "scenario version mismatch: "
            f"catalog={family.version}, requested={scenario.scenario_version}"
        )


__all__ = (
    "LabFixtureDefinition",
    "LabScenarioDefinition",
    "LabScenarioStep",
    "LabStepAction",
    "capture_lab_episode",
)
