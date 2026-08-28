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
    PASSED = "passed"
    EVIDENCE_READY = "evidence_ready"
    FAILED = "failed"
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
    EVIDENCE_READY = "evidence_ready"
    FAILED = "failed"
    IMPROVED = "improved"
    UNCHANGED = "unchanged"
    REGRESSED = "regressed"
    INCOMPLETE = "incomplete"


@unique
class LabEvaluationBatchKind(str, Enum):
    SINGLE = "single"
    PAIRED = "paired"


@unique
class LabEvaluationBatchStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL_FAILED = "partial_failed"
    FAILED = "failed"


@unique
class LabEvaluationComparisonVariable(str, Enum):
    FOOD = "food"
    CODE = "code"


@unique
class LabEvaluationComparisonGrade(str, Enum):
    STRICT = "strict"
    OBSERVATIONAL = "observational"
    INCOMPATIBLE = "incompatible"


@unique
class LabEvaluationScoreGrade(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"
    P0_FAILED = "P0_FAILED"
    INCOMPLETE = "INCOMPLETE"


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
    index: int = Field(default=0, ge=0)
    attempt_id: Optional[str] = Field(default=None, max_length=160)
    family_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=160)
    purpose: str = Field(min_length=1, max_length=500)
    dimension: Optional[QualityDimension] = None
    input_messages: Tuple[str, ...] = ()
    execution_steps: Tuple[str, ...] = ()
    assertions: Tuple[str, ...] = ()
    assertion_results: Tuple[Optional[bool], ...] = ()
    status: LabEvaluationResultStatus
    baseline_outputs: Tuple[str, ...] = ()
    candidate_outputs: Tuple[str, ...] = ()
    evidence: Tuple[str, ...] = ()
    judge_preference: Optional[Literal["a", "b", "tie", "invalid"]] = None
    judge_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    judge_rationale: Tuple[str, ...] = ()
    baseline_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    candidate_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    latency_ms: float = Field(default=0.0, ge=0.0)
    model_calls: int = Field(default=0, ge=0)
    input_tokens: Optional[int] = Field(default=None, ge=0)
    output_tokens: Optional[int] = Field(default=None, ge=0)
    cost_microunits: Optional[int] = Field(default=None, ge=0)
    retries: int = Field(default=0, ge=0)
    timed_out: bool = False
    error: Optional[str] = Field(default=None, max_length=500)


class EvaluationDimensionResult(_EvaluationModel):
    dimension: QualityDimension
    label: str = Field(min_length=1, max_length=80)
    status: LabEvaluationResultStatus
    weight: float = Field(default=1.0, gt=0.0)
    scenario_count: int = Field(default=0, ge=0)
    valid_scenario_count: int = Field(default=0, ge=0)
    coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    value: Optional[int] = Field(default=None, ge=-1, le=1)
    score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    baseline_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    candidate_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    delta: Optional[float] = Field(default=None, ge=-100.0, le=100.0)
    baseline_source: str = Field(default="", max_length=240)
    scoring_rule: str = Field(default="", max_length=240)
    confidence_lower: Optional[float] = Field(default=None, ge=-100.0, le=100.0)
    confidence_upper: Optional[float] = Field(default=None, ge=-100.0, le=100.0)
    evidence: Tuple[str, ...] = ()


class LabEvaluationRun(_EvaluationModel):
    schema_version: Literal[1] = 1
    run_id: str = Field(min_length=1, max_length=160)
    elfie_id: str = Field(min_length=1, max_length=160)
    elfie_name: str = Field(default="", max_length=160)
    elfie_species_id: str = Field(default="", max_length=40)
    batch_id: Optional[str] = Field(default=None, max_length=160)
    batch_role: Optional[Literal["A", "B"]] = None
    purpose: str = Field(default="", max_length=500)
    suite: LabEvaluationSuite
    status: LabEvaluationStatus
    verdict: LabEvaluationVerdict
    scoring_version: str = Field(default="standard-v1", min_length=1, max_length=80)
    overall_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    grade: Optional[LabEvaluationScoreGrade] = None
    score_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    p0_passed: Optional[bool] = None
    validity: Literal["valid", "incomplete", "p0_blocked", "incomparable"] = (
        "incomplete"
    )
    created_at: datetime
    completed_at: Optional[datetime] = None
    title: str = Field(default="", max_length=80)
    source_revision: str = Field(min_length=1, max_length=160)
    source_ref: str = Field(default="", max_length=240)
    source_dirty: bool
    source_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_label: str = Field(min_length=1, max_length=240)
    candidate_spec_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    food_spec_sha256: str = Field(default="0" * 64, pattern=r"^[0-9a-f]{64}$")
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fixture_snapshot_id: Optional[str] = Field(default=None, max_length=160)
    fixture_captured_at: Optional[datetime] = None
    fixture_memory_count: int = Field(default=0, ge=0)
    fixture_activity_count: int = Field(default=0, ge=0)
    fixture_journal_count: int = Field(default=0, ge=0)
    test_plan_key: str = Field(default="legacy", max_length=160)
    test_plan_title: str = Field(default="历史测试计划", max_length=160)
    test_plan_sha256: str = Field(default="0" * 64, pattern=r"^[0-9a-f]{64}$")
    execution_rules: Tuple[str, ...] = ()
    scenario_order: Tuple[str, ...] = ()
    repeat_count: int = Field(default=1, ge=1)
    timeout_seconds: Optional[float] = Field(default=None, gt=0.0)
    retry_policy: str = Field(default="none", max_length=120)
    baseline_source: str = Field(default="", max_length=240)
    food_key: str = Field(min_length=1, max_length=160)
    food_display_name: str = Field(default="", max_length=240)
    food_model: str = Field(min_length=1, max_length=500)
    # Independent remote reviewer subscription; it is never a candidate Food.
    judge_subscription_id: str = Field(min_length=1, max_length=160)
    judge_model: str = Field(min_length=1, max_length=500)
    judge_spec_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    baseline_run_id: Optional[str] = Field(default=None, max_length=160)
    is_baseline: bool = False
    formal_eligible: bool = False
    total_scenarios: int = Field(ge=1)
    completed_scenarios: int = Field(ge=0)
    total_model_calls: int = Field(default=0, ge=0)
    total_latency_ms: float = Field(default=0.0, ge=0.0)
    total_input_tokens: Optional[int] = Field(default=None, ge=0)
    total_output_tokens: Optional[int] = Field(default=None, ge=0)
    total_cost_microunits: Optional[int] = Field(default=None, ge=0)
    total_retries: int = Field(default=0, ge=0)
    total_timeouts: int = Field(default=0, ge=0)
    evidence_artifact_id: Optional[str] = Field(default=None, max_length=160)
    scenarios: Tuple[EvaluationScenarioResult, ...]
    dimensions: Tuple[EvaluationDimensionResult, ...] = ()
    p0_violations: Tuple[EvaluationViolation, ...] = ()
    warnings: Tuple[str, ...] = ()
    error: Optional[str] = Field(default=None, max_length=1200)
    episodes: Tuple[EpisodeEvidence, ...] = ()

    @model_validator(mode="after")
    def validate_run_state(self) -> LabEvaluationRun:
        for timestamp in (
            self.created_at,
            self.completed_at,
            self.fixture_captured_at,
        ):
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
        if self.scenario_order and self.scenario_order != tuple(
            row.family_id for row in self.scenarios
        ):
            raise PydanticCustomError(
                "evaluation_scenario_order",
                "scenario_order must match persisted scenario rows",
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


class LabEvaluationBatch(_EvaluationModel):
    schema_version: Literal[1] = 1
    batch_id: str = Field(min_length=1, max_length=160)
    kind: LabEvaluationBatchKind
    status: LabEvaluationBatchStatus
    comparison_variable: Optional[LabEvaluationComparisonVariable] = None
    title: str = Field(default="", max_length=80)
    purpose: str = Field(default="", max_length=500)
    elfie_id: str = Field(min_length=1, max_length=160)
    elfie_name: str = Field(default="", max_length=160)
    suite: LabEvaluationSuite
    fixture_snapshot_id: Optional[str] = Field(default=None, max_length=160)
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    test_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    report_ids: Tuple[str, ...] = Field(min_length=1, max_length=2)
    created_at: datetime
    completed_at: Optional[datetime] = None
    comparison_artifact_id: Optional[str] = Field(default=None, max_length=160)
    error: Optional[str] = Field(default=None, max_length=1200)

    @model_validator(mode="after")
    def validate_batch(self) -> LabEvaluationBatch:
        expected = 1 if self.kind is LabEvaluationBatchKind.SINGLE else 2
        if len(self.report_ids) != expected:
            raise PydanticCustomError(
                "evaluation_batch_reports",
                f"{self.kind.value} batches require {expected} report(s)",
            )
        for timestamp in (self.created_at, self.completed_at):
            if timestamp is not None and timestamp.utcoffset() != timedelta(0):
                raise PydanticCustomError(
                    "evaluation_time",
                    "evaluation timestamps must be timezone-aware UTC",
                )
        terminal = self.status in {
            LabEvaluationBatchStatus.COMPLETED,
            LabEvaluationBatchStatus.PARTIAL_FAILED,
            LabEvaluationBatchStatus.FAILED,
        }
        if terminal != (self.completed_at is not None):
            raise PydanticCustomError(
                "evaluation_batch_completion",
                "terminal batch state and completed_at must agree",
            )
        return self


class EvaluationComparisonScenario(_EvaluationModel):
    family_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=160)
    purpose: str = Field(min_length=1, max_length=500)
    dimension: Optional[QualityDimension] = None
    status: LabEvaluationResultStatus
    input_messages: Tuple[str, ...] = ()
    execution_steps: Tuple[str, ...] = ()
    assertions: Tuple[str, ...] = ()
    report_a_outputs: Tuple[str, ...] = ()
    report_b_outputs: Tuple[str, ...] = ()
    evidence: Tuple[str, ...] = ()


class LabEvaluationComparison(_EvaluationModel):
    schema_version: Literal[1] = 1
    comparison_id: str = Field(min_length=1, max_length=160)
    batch_id: Optional[str] = Field(default=None, max_length=160)
    report_a_id: str = Field(min_length=1, max_length=160)
    report_b_id: str = Field(min_length=1, max_length=160)
    report_a_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    report_b_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    grade: LabEvaluationComparisonGrade
    scoring_version: str = Field(default="standard-v1", min_length=1, max_length=80)
    report_a_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    report_b_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    report_a_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    report_b_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    report_a_validity: Literal["valid", "incomplete", "p0_blocked", "incomparable"] = (
        "incomplete"
    )
    report_b_validity: Literal["valid", "incomplete", "p0_blocked", "incomparable"] = (
        "incomplete"
    )
    overall_delta: Optional[float] = Field(default=None, ge=-100.0, le=100.0)
    report_a_grade: Optional[LabEvaluationScoreGrade] = None
    report_b_grade: Optional[LabEvaluationScoreGrade] = None
    comparison_variable: Optional[LabEvaluationComparisonVariable] = None
    differing_fields: Tuple[str, ...] = ()
    compatibility_reasons: Tuple[str, ...] = ()
    verdict: LabEvaluationVerdict
    created_at: datetime
    dimensions: Tuple[EvaluationDimensionResult, ...] = ()
    scenarios: Tuple[EvaluationComparisonScenario, ...] = ()
    p0_report_a: Tuple[EvaluationViolation, ...] = ()
    p0_report_b: Tuple[EvaluationViolation, ...] = ()
    warnings: Tuple[str, ...] = ()


class EvaluationHistory(_EvaluationModel):
    items: Tuple[LabEvaluationRun, ...]
    baseline_run_ids: dict[str, str]

    def public_payload(self) -> dict[str, object]:
        return {
            "items": [item.public_payload() for item in self.items],
            "baseline_run_ids": dict(self.baseline_run_ids),
        }


__all__ = (
    "EvaluationComparisonScenario",
    "EvaluationDimensionResult",
    "EvaluationHistory",
    "EvaluationPreset",
    "EvaluationScenarioResult",
    "EvaluationViolation",
    "LabEvaluationBatch",
    "LabEvaluationBatchKind",
    "LabEvaluationBatchStatus",
    "LabEvaluationComparison",
    "LabEvaluationComparisonGrade",
    "LabEvaluationComparisonVariable",
    "LabEvaluationResultStatus",
    "LabEvaluationRun",
    "LabEvaluationScoreGrade",
    "LabEvaluationStatus",
    "LabEvaluationSuite",
    "LabEvaluationVerdict",
)
