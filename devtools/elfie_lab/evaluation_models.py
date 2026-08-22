"""Typed persistence and HTTP projections for Elfie Lab evaluation runs."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum, unique
from typing import Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from devtools.brain_eval.contracts import EpisodeEvidence, QualityDimension


class _EvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


@unique
class LabEvaluationSuite(str, Enum):
    QUICK = "quick"
    STANDARD = "standard"


@unique
class LabEvaluationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@unique
class LabEvaluationVerdict(str, Enum):
    BASELINE = "baseline"
    IMPROVED = "improved"
    OBSERVE = "observe"
    REGRESSED = "regressed"
    INCOMPLETE = "incomplete"


@unique
class LabEvaluationResultStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    BASELINE = "baseline"
    PASSED = "passed"
    FAILED = "failed"
    IMPROVED = "improved"
    UNCHANGED = "unchanged"
    REGRESSED = "regressed"
    INCOMPLETE = "incomplete"


class EvaluationPreset(_EvaluationModel):
    key: LabEvaluationSuite
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=240)
    typical_duration: str = Field(min_length=1, max_length=80)
    scenario_count: int = Field(ge=1)
    requires_godot: bool = False


class EvaluationViolation(_EvaluationModel):
    code: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=240)
    evidence: Tuple[str, ...] = Field(min_length=1)


class EvaluationScenarioResult(_EvaluationModel):
    family_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=160)
    purpose: str = Field(min_length=1, max_length=500)
    dimension: Optional[QualityDimension] = None
    status: LabEvaluationResultStatus
    baseline_outputs: Tuple[str, ...] = ()
    candidate_outputs: Tuple[str, ...] = ()
    evidence: Tuple[str, ...] = ()
    latency_ms: float = Field(default=0.0, ge=0.0)
    error: Optional[str] = Field(default=None, max_length=500)


class EvaluationDimensionResult(_EvaluationModel):
    dimension: QualityDimension
    label: str = Field(min_length=1, max_length=80)
    status: LabEvaluationResultStatus
    value: Optional[int] = Field(default=None, ge=-1, le=1)
    evidence: Tuple[str, ...] = ()


class LabEvaluationRun(_EvaluationModel):
    schema_version: Literal[1] = 1
    run_id: str = Field(min_length=1, max_length=160)
    elfie_id: str = Field(min_length=1, max_length=160)
    suite: LabEvaluationSuite
    status: LabEvaluationStatus
    verdict: LabEvaluationVerdict
    created_at: datetime
    completed_at: Optional[datetime] = None
    source_revision: str = Field(min_length=1, max_length=160)
    source_dirty: bool
    source_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_label: str = Field(min_length=1, max_length=240)
    candidate_spec_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    food_key: str = Field(min_length=1, max_length=160)
    food_model: str = Field(min_length=1, max_length=500)
    judge_food_key: str = Field(min_length=1, max_length=160)
    judge_model: str = Field(min_length=1, max_length=500)
    judge_spec_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    baseline_run_id: Optional[str] = Field(default=None, max_length=160)
    is_baseline: bool = False
    formal_eligible: bool = False
    total_scenarios: int = Field(ge=1)
    completed_scenarios: int = Field(ge=0)
    total_model_calls: int = Field(default=0, ge=0)
    total_latency_ms: float = Field(default=0.0, ge=0.0)
    scenarios: Tuple[EvaluationScenarioResult, ...]
    dimensions: Tuple[EvaluationDimensionResult, ...] = ()
    p0_violations: Tuple[EvaluationViolation, ...] = ()
    warnings: Tuple[str, ...] = ()
    error: Optional[str] = Field(default=None, max_length=1200)
    episodes: Tuple[EpisodeEvidence, ...] = ()

    @model_validator(mode="after")
    def validate_run_state(self) -> LabEvaluationRun:
        for timestamp in (self.created_at, self.completed_at):
            if timestamp is not None and timestamp.utcoffset() != timedelta(0):
                raise PydanticCustomError(
                    "evaluation_time",
                    "evaluation timestamps must be timezone-aware UTC",
                )
        if self.completed_scenarios > self.total_scenarios:
            raise PydanticCustomError(
                "evaluation_progress",
                "completed scenarios cannot exceed the run total",
            )
        if len(self.scenarios) != self.total_scenarios:
            raise PydanticCustomError(
                "evaluation_scenarios",
                "scenario rows must match the declared run total",
            )
        if self.status in {LabEvaluationStatus.COMPLETED, LabEvaluationStatus.FAILED}:
            if self.completed_at is None:
                raise PydanticCustomError(
                    "evaluation_completion",
                    "terminal runs require completed_at",
                )
        elif self.completed_at is not None:
            raise PydanticCustomError(
                "evaluation_completion",
                "non-terminal runs cannot have completed_at",
            )
        return self

    def public_payload(self) -> dict[str, object]:
        """Exclude replay evidence from the ordinary Lab API projection."""

        return self.model_dump(mode="json", exclude={"episodes"})


class EvaluationHistory(_EvaluationModel):
    items: Tuple[LabEvaluationRun, ...]
    baseline_run_ids: dict[str, str]

    def public_payload(self) -> dict[str, object]:
        return {
            "items": [item.public_payload() for item in self.items],
            "baseline_run_ids": dict(self.baseline_run_ids),
        }


__all__ = (
    "EvaluationDimensionResult",
    "EvaluationHistory",
    "EvaluationPreset",
    "EvaluationScenarioResult",
    "EvaluationViolation",
    "LabEvaluationResultStatus",
    "LabEvaluationRun",
    "LabEvaluationStatus",
    "LabEvaluationSuite",
    "LabEvaluationVerdict",
)
