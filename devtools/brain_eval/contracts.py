"""Versioned data contracts for reproducible Elfie Brain evaluation."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from enum import Enum, unique
from hashlib import sha256
from typing import Dict, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError


class EvalContract(BaseModel):
    """Immutable, closed contract shared by Brain evaluation artifacts."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


def contract_sha256(contract: EvalContract) -> str:
    """Return the canonical content identity used to bind nested artifacts."""

    encoded = json.dumps(
        contract.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


@unique
class QualityDimension(str, Enum):
    """The six product-facing qualities of one complete, continuous Elfie."""

    IDENTITY_CONTINUITY = "identity_continuity"
    UNDERSTANDING_REASONING = "understanding_reasoning"
    MEMORY_RELATIONSHIPS = "memory_relationships"
    EMOTION_ENERGY = "emotion_energy"
    AUTONOMY_BOUNDARIES = "autonomy_boundaries"
    COMMITMENT_RELIABILITY = "commitment_reliability"


@unique
class DecisionStatus(str, Enum):
    PROMOTE = "promote"
    OBSERVE = "observe"
    REJECT = "reject"
    INVALID = "invalid"


@unique
class ConfirmationKind(str, Enum):
    """Independent confirmations that may unlock a promotion decision."""

    PRIVATE_HOLDOUT = "private_holdout"
    CONSTITUTIONAL_ANCHOR = "constitutional_anchor"


@unique
class ScenarioVerdictSource(str, Enum):
    """Authorities allowed to decide whether a scenario goal was achieved."""

    DETERMINISTIC_ADAPTER = "deterministic_adapter"
    HUMAN_REVIEW = "human_review"


@unique
class ScenarioSuite(str, Enum):
    FAST_GATE = "fast_gate"
    BEHAVIOR = "behavior"
    LONG_SOAK = "long_soak"


@unique
class ScenarioScale(str, Enum):
    TURN = "turn"
    EPISODE = "episode"
    TRAJECTORY = "trajectory"


@unique
class SourceDomain(str, Enum):
    COMMUNICATION = "communication"
    EMBODIED = "embodied"
    ACTIVITY = "activity"


@unique
class ExternalDomain(str, Enum):
    COMMUNICATION = "communication"
    EMBODIED = "embodied"


@unique
class EffectStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@unique
class JudgePreference(str, Enum):
    CANDIDATE = "candidate"
    BASELINE = "baseline"
    TIE = "tie"
    INVALID = "invalid"


@unique
class PresentationOrder(str, Enum):
    BASELINE_FIRST = "baseline_first"
    CANDIDATE_FIRST = "candidate_first"


@unique
class SlotPreference(str, Enum):
    A = "a"
    B = "b"
    TIE = "tie"
    INVALID = "invalid"


class CandidateSpec(EvalContract):
    """Everything allowed to differ between baseline and candidate."""

    candidate_id: str = Field(min_length=1, max_length=160)
    code_sha: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    model_provider: str = Field(min_length=1, max_length=160)
    model_id: str = Field(min_length=1, max_length=240)
    model_fingerprint: Optional[str] = Field(default=None, max_length=240)
    model_parameters_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_revision: str = Field(min_length=1, max_length=160)
    context_compiler_revision: str = Field(min_length=1, max_length=160)
    memory_policy_revision: str = Field(min_length=1, max_length=160)
    tool_policy_revision: str = Field(min_length=1, max_length=160)
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    captured_at: datetime

    @model_validator(mode="after")
    def require_utc_capture_time(self) -> CandidateSpec:
        if self.captured_at.utcoffset() != timedelta(0):
            raise PydanticCustomError(
                "candidate_capture_time",
                "captured_at must be timezone-aware UTC",
            )
        return self


class ScenarioFixture(EvalContract):
    """Frozen life state; it is never part of the candidate definition."""

    fixture_id: str = Field(min_length=1, max_length=160)
    fixture_ref: str = Field(min_length=1, max_length=512)
    profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    brain_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    world_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ScenarioFamily(EvalContract):
    family_id: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=240)
    purpose: str = Field(min_length=1, max_length=1200)
    suite: ScenarioSuite
    scale: ScenarioScale
    dimensions: Tuple[QualityDimension, ...] = ()
    p0_gate_codes: Tuple[str, ...] = ()
    variant_axes: Tuple[str, ...] = ()

    @model_validator(mode="after")
    def require_evaluation_target(self) -> ScenarioFamily:
        if not self.dimensions and not self.p0_gate_codes:
            raise PydanticCustomError(
                "scenario_target",
                "scenario family must target a quality dimension or P0 gate",
            )
        return self


class RunSpec(EvalContract):
    """One replayable candidate/fixture/scenario binding."""

    run_id: str = Field(min_length=1, max_length=160)
    protocol_version: str = Field(min_length=1, max_length=40)
    candidate: CandidateSpec
    fixture: ScenarioFixture
    scenario_family_id: str = Field(min_length=1, max_length=160)
    scenario_version: str = Field(min_length=1, max_length=40)
    variant_id: str = Field(min_length=1, max_length=160)
    seed: int = Field(ge=0)
    virtual_start: datetime
    event_schedule_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    judge_protocol_version: str = Field(min_length=1, max_length=160)

    @model_validator(mode="after")
    def require_utc_virtual_start(self) -> RunSpec:
        if self.virtual_start.utcoffset() != timedelta(0):
            raise PydanticCustomError(
                "run_virtual_start",
                "virtual_start must be timezone-aware UTC",
            )
        return self


class TurnEvidence(EvalContract):
    turn_id: str = Field(min_length=1, max_length=160)
    source_domain: SourceDomain
    source_scope_id: Optional[str] = Field(default=None, max_length=240)
    output_domains: Tuple[ExternalDomain, ...] = ()
    output_scope_ids: Tuple[str, ...] = ()

    @model_validator(mode="after")
    def align_output_scope_evidence(self) -> TurnEvidence:
        if len(self.output_domains) != len(self.output_scope_ids):
            raise PydanticCustomError(
                "turn_output_scope",
                "each output domain requires one matching scope identity",
            )
        return self


class EffectEvidence(EvalContract):
    effect_id: str = Field(min_length=1, max_length=160)
    domain: ExternalDomain
    status: EffectStatus
    receipt_id: Optional[str] = Field(default=None, max_length=160)
    irreversible: bool
    authorized: bool
    trigger_kind: str = Field(min_length=1, max_length=160)


class CompletionClaimEvidence(EvalContract):
    claim_id: str = Field(min_length=1, max_length=160)
    effect_id: str = Field(min_length=1, max_length=160)


class IdentityChangeEvidence(EvalContract):
    change_id: str = Field(min_length=1, max_length=160)
    field_name: str = Field(min_length=1, max_length=160)
    immutable_anchor: bool
    evidence_authorized: bool


class DisclosureEvidence(EvalContract):
    disclosure_id: str = Field(min_length=1, max_length=160)
    private: bool
    authorized: bool


class CapabilityUseEvidence(EvalContract):
    use_id: str = Field(min_length=1, max_length=160)
    capability: str = Field(min_length=1, max_length=240)
    authorized: bool


class ResourceObservation(EvalContract):
    latency_ms: float = Field(ge=0.0)
    model_calls: int = Field(ge=0)
    input_tokens: Optional[int] = Field(default=None, ge=0)
    output_tokens: Optional[int] = Field(default=None, ge=0)
    cost_microunits: Optional[int] = Field(default=None, ge=0)


class ModelExecutionEvidence(EvalContract):
    """Actual provider/model identity observed for one Brain model call."""

    food_key: str = Field(min_length=1, max_length=160)
    provider: Optional[str] = Field(default=None, min_length=1, max_length=160)
    model_id: Optional[str] = Field(default=None, min_length=1, max_length=240)
    skipped: bool
    degraded: bool
    error: Optional[str] = Field(default=None, max_length=1200)

    @model_validator(mode="after")
    def require_executed_model_identity(self) -> ModelExecutionEvidence:
        if not self.skipped and (self.provider is None or self.model_id is None):
            raise PydanticCustomError(
                "model_execution_identity",
                "non-skipped model execution requires provider and model_id",
            )
        return self


class ScenarioVerdict(EvalContract):
    """Goal-state verdict; technical execution success cannot substitute for it."""

    source: ScenarioVerdictSource
    evaluator_id: str = Field(min_length=1, max_length=160)
    evaluator_revision: str = Field(min_length=1, max_length=160)
    passed: bool
    evidence: Tuple[str, ...] = Field(min_length=1)


class EpisodeEvidence(EvalContract):
    """Observable facts for one candidate trajectory, excluding hidden thought."""

    candidate_id: str = Field(min_length=1, max_length=160)
    candidate_spec_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scenario_family_id: str = Field(min_length=1, max_length=160)
    scenario_version: str = Field(min_length=1, max_length=40)
    variant_id: str = Field(min_length=1, max_length=160)
    fixture_id: str = Field(min_length=1, max_length=160)
    seed: int = Field(ge=0)
    execution_success: bool
    scenario_verdict: Optional[ScenarioVerdict] = None
    hidden: bool
    turns: Tuple[TurnEvidence, ...] = ()
    effects: Tuple[EffectEvidence, ...] = ()
    completion_claims: Tuple[CompletionClaimEvidence, ...] = ()
    identity_changes: Tuple[IdentityChangeEvidence, ...] = ()
    disclosures: Tuple[DisclosureEvidence, ...] = ()
    capability_uses: Tuple[CapabilityUseEvidence, ...] = ()
    public_outputs: Tuple[str, ...] = ()
    model_executions: Tuple[ModelExecutionEvidence, ...] = ()
    resources: ResourceObservation

    @model_validator(mode="after")
    def keep_scenario_success_grounded(self) -> EpisodeEvidence:
        if (
            self.scenario_verdict is not None
            and self.scenario_verdict.passed
            and not self.execution_success
        ):
            raise PydanticCustomError(
                "scenario_verdict_execution",
                "a technically failed episode cannot have a passing scenario verdict",
            )
        return self

    @property
    def pair_key(self) -> Tuple[str, str, str, int]:
        return (
            self.scenario_family_id,
            self.variant_id,
            self.fixture_id,
            self.seed,
        )


class GateViolation(EvalContract):
    code: str = Field(min_length=1, max_length=160)
    scenario_family_id: str = Field(min_length=1, max_length=160)
    message: str = Field(min_length=1, max_length=1200)
    evidence_ids: Tuple[str, ...] = Field(min_length=1)


class JudgeVote(EvalContract):
    pair_id: str = Field(min_length=1, max_length=160)
    pair_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scenario_family_id: str = Field(min_length=1, max_length=160)
    scenario_version: str = Field(min_length=1, max_length=40)
    variant_id: str = Field(min_length=1, max_length=160)
    fixture_id: str = Field(min_length=1, max_length=160)
    seed: int = Field(ge=0)
    dimension: QualityDimension
    judge_id: str = Field(min_length=1, max_length=160)
    judge_revision: str = Field(min_length=1, max_length=240)
    rubric_version: str = Field(min_length=1, max_length=160)
    presentation_order: PresentationOrder
    preference: JudgePreference
    evidence: Tuple[str, ...] = ()
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: Tuple[str, ...] = ()

    @model_validator(mode="after")
    def require_evidence_for_decision(self) -> JudgeVote:
        if self.preference is not JudgePreference.INVALID and not self.evidence:
            raise PydanticCustomError(
                "judge_evidence",
                "non-invalid judge votes must cite observable evidence",
            )
        return self


class JudgeObservableFact(EvalContract):
    """Candidate-ID-free structured fact made inspectable to a soft-quality Judge."""

    evidence_ref: str = Field(min_length=1, max_length=240)
    kind: str = Field(min_length=1, max_length=80)
    value_json: str = Field(min_length=1, max_length=16000)


class JudgeEvidenceSlot(EvalContract):
    """Anonymous candidate output embedded as untrusted data, never instructions."""

    slot: Literal["A", "B"]
    untrusted_outputs: Tuple[str, ...]
    evidence_refs: Tuple[str, ...]
    observable_facts: Tuple[JudgeObservableFact, ...]

    @model_validator(mode="after")
    def align_slot_evidence(self) -> JudgeEvidenceSlot:
        expected = {
            *(fact.evidence_ref for fact in self.observable_facts),
            *(
                f"{self.slot}:output:{index}"
                for index, _ in enumerate(self.untrusted_outputs)
            ),
        }
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise PydanticCustomError(
                "judge_evidence_refs",
                "evidence_refs must be unique",
            )
        if set(self.evidence_refs) != expected:
            raise PydanticCustomError(
                "judge_evidence_refs",
                "evidence_refs must cover every observable fact and output",
            )
        return self


class JudgeEvidencePacket(EvalContract):
    packet_id: str = Field(min_length=1, max_length=240)
    pair_id: str = Field(min_length=1, max_length=160)
    pair_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scenario_family_id: str = Field(min_length=1, max_length=160)
    scenario_version: str = Field(min_length=1, max_length=40)
    variant_id: str = Field(min_length=1, max_length=160)
    fixture_id: str = Field(min_length=1, max_length=160)
    seed: int = Field(ge=0)
    dimension: QualityDimension
    rubric_version: str = Field(min_length=1, max_length=160)
    presentation_order: PresentationOrder
    scenario_context: str = Field(min_length=1, max_length=8000)
    slot_a: JudgeEvidenceSlot
    slot_b: JudgeEvidenceSlot

    @model_validator(mode="after")
    def require_named_slots(self) -> JudgeEvidencePacket:
        if self.slot_a.slot != "A" or self.slot_b.slot != "B":
            raise PydanticCustomError(
                "judge_slots",
                "slot_a and slot_b must retain anonymous A/B labels",
            )
        return self


class RawJudgeResult(EvalContract):
    preference: SlotPreference
    evidence: Tuple[str, ...] = ()
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: Tuple[str, ...] = ()

    @model_validator(mode="after")
    def require_raw_evidence(self) -> RawJudgeResult:
        if self.preference is not SlotPreference.INVALID and not self.evidence:
            raise PydanticCustomError(
                "raw_judge_evidence",
                "non-invalid raw judge results must cite packet evidence",
            )
        return self


class HumanAnchor(EvalContract):
    pair_id: str = Field(min_length=1, max_length=160)
    pair_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dimension: QualityDimension
    preference: JudgePreference
    evidence: Tuple[str, ...] = Field(min_length=1)
    annotator_count: int = Field(ge=2)
    human_agreement: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def forbid_invalid_human_anchor(self) -> HumanAnchor:
        if self.preference is JudgePreference.INVALID:
            raise PydanticCustomError(
                "human_anchor_invalid",
                "invalid samples cannot be calibration anchors",
            )
        return self


class JudgeCalibrationReport(EvalContract):
    calibration_id: str = Field(min_length=1, max_length=160)
    protocol_version: str = Field(min_length=1, max_length=40)
    judge_id: str = Field(min_length=1, max_length=160)
    judge_revision: str = Field(min_length=1, max_length=240)
    rubric_versions: Tuple[str, ...] = Field(min_length=1)
    anchor_set_revision: str = Field(min_length=1, max_length=160)
    anchor_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    calibrated_at: datetime
    dimensions_covered: Tuple[QualityDimension, ...] = ()
    passed: bool
    judge_human_agreement: float = Field(ge=0.0, le=1.0)
    human_human_agreement: float = Field(ge=0.0, le=1.0)
    position_flip_consistency: float = Field(ge=0.0, le=1.0)
    anchor_coverage: float = Field(ge=0.0, le=1.0)
    anchor_count: int = Field(ge=0)
    matched_anchor_count: int = Field(ge=0)
    tolerance: float = Field(ge=0.0, le=1.0)
    minimum_position_consistency: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_calibration_identity(self) -> JudgeCalibrationReport:
        if self.calibrated_at.utcoffset() != timedelta(0):
            raise PydanticCustomError(
                "calibration_time",
                "calibrated_at must be timezone-aware UTC",
            )
        if len(set(self.dimensions_covered)) != len(self.dimensions_covered):
            raise PydanticCustomError(
                "calibration_dimensions",
                "dimensions_covered must not contain duplicates",
            )
        if len(set(self.rubric_versions)) != len(self.rubric_versions):
            raise PydanticCustomError(
                "calibration_rubrics",
                "rubric_versions must not contain duplicates",
            )
        if self.matched_anchor_count > self.anchor_count:
            raise PydanticCustomError(
                "calibration_anchor_count",
                "matched_anchor_count cannot exceed anchor_count",
            )
        return self


class EvaluationConfirmation(EvalContract):
    """Auditable result from a protected suite, bound to one exact comparison."""

    confirmation_id: str = Field(min_length=1, max_length=160)
    kind: ConfirmationKind
    protocol_version: str = Field(min_length=1, max_length=40)
    baseline_candidate_id: str = Field(min_length=1, max_length=160)
    candidate_id: str = Field(min_length=1, max_length=160)
    baseline_candidate_spec_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_spec_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    suite_revision: str = Field(min_length=1, max_length=160)
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    access_count: int = Field(ge=1)
    passed: bool
    evaluated_at: datetime

    @model_validator(mode="after")
    def require_utc_evaluation_time(self) -> EvaluationConfirmation:
        if self.evaluated_at.utcoffset() != timedelta(0):
            raise PydanticCustomError(
                "confirmation_evaluation_time",
                "evaluated_at must be timezone-aware UTC",
            )
        return self


class PairwiseOutcome(EvalContract):
    pair_id: str
    pair_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scenario_family_id: str
    scenario_version: str
    variant_id: str
    fixture_id: str
    seed: int
    dimension: QualityDimension
    valid: bool
    value: Optional[int] = Field(default=None, ge=-1, le=1)
    invalid_reason: Optional[str] = None
    evidence: Tuple[str, ...] = ()
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    rationale: Tuple[str, ...] = ()

    @model_validator(mode="after")
    def align_validity(self) -> PairwiseOutcome:
        if self.valid != (self.value is not None):
            raise PydanticCustomError(
                "pairwise_validity",
                "valid outcomes require a value and invalid outcomes forbid one",
            )
        if not self.valid and not self.invalid_reason:
            raise PydanticCustomError(
                "pairwise_invalid_reason",
                "invalid outcomes require a reason",
            )
        return self


class DimensionEffect(EvalContract):
    dimension: QualityDimension
    valid: bool
    net_advantage: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    lower_bound: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    upper_bound: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    pair_count: int = Field(ge=0)
    invalid_pair_count: int = Field(ge=0)
    scenario_family_count: int = Field(ge=0)

    @model_validator(mode="after")
    def align_effect_validity(self) -> DimensionEffect:
        values_present = all(
            item is not None
            for item in (self.net_advantage, self.lower_bound, self.upper_bound)
        )
        if self.valid != values_present:
            raise PydanticCustomError(
                "dimension_effect_validity",
                "valid effects require estimate and confidence bounds",
            )
        if self.valid and not (
            self.lower_bound <= self.net_advantage <= self.upper_bound  # type: ignore[operator]
        ):
            raise PydanticCustomError(
                "dimension_effect_bounds",
                "effect estimate must lie within its confidence bounds",
            )
        return self


class ResourceBudget(EvalContract):
    """Absolute candidate envelope; resources never enter the soft EPI."""

    max_mean_latency_ms: float = Field(gt=0.0)
    max_p95_latency_ms: float = Field(gt=0.0)
    max_mean_model_calls: float = Field(gt=0.0)
    max_mean_output_tokens: Optional[float] = Field(default=None, gt=0.0)
    max_mean_cost_microunits: Optional[float] = Field(default=None, gt=0.0)

    @model_validator(mode="after")
    def align_latency_limits(self) -> ResourceBudget:
        if self.max_p95_latency_ms < self.max_mean_latency_ms:
            raise PydanticCustomError(
                "resource_latency",
                "p95 latency budget cannot be lower than the mean latency budget",
            )
        return self


class PromotionPolicy(EvalContract):
    protocol_version: str = Field(min_length=1, max_length=40)
    primary_dimension: QualityDimension
    minimum_meaningful_effect: float = Field(ge=0.0, le=1.0)
    protected_margins: Dict[QualityDimension, float]
    reliability_margin: float = Field(ge=0.0, le=1.0)
    minimum_scenario_families: int = Field(ge=2)
    consistency_k: int = Field(ge=1)
    resource_budget: ResourceBudget
    judge_calibration_required: bool
    minimum_calibration_anchors: int = Field(ge=len(QualityDimension))
    maximum_calibration_tolerance: float = Field(ge=0.0, le=1.0)
    minimum_judge_position_consistency: float = Field(ge=0.0, le=1.0)
    hidden_confirmation_required: bool
    constitutional_anchor_required: bool

    @model_validator(mode="after")
    def protect_every_non_target_dimension(self) -> PromotionPolicy:
        expected = set(QualityDimension) - {self.primary_dimension}
        if set(self.protected_margins) != expected:
            raise PydanticCustomError(
                "protected_dimensions",
                "protected_margins must cover every non-target Q6 dimension",
            )
        if any(
            margin < 0.0 or margin > 1.0 for margin in self.protected_margins.values()
        ):
            raise PydanticCustomError(
                "protected_margin",
                "protected margins must be between zero and one",
            )
        return self


class ReliabilityComparison(EvalContract):
    valid: bool
    baseline_success_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    candidate_success_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    delta: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    delta_lower_bound: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    delta_upper_bound: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    baseline_consistency_at_k: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    candidate_consistency_at_k: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    consistency_delta: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    consistency_delta_lower_bound: Optional[float] = Field(
        default=None,
        ge=-1.0,
        le=1.0,
    )
    consistency_delta_upper_bound: Optional[float] = Field(
        default=None,
        ge=-1.0,
        le=1.0,
    )
    k: int = Field(ge=1)
    paired_episode_count: int = Field(ge=0)
    scenario_family_count: int = Field(ge=0)
    invalid_pair_count: int = Field(ge=0)
    invalid_reason: Optional[str] = None

    @model_validator(mode="after")
    def align_reliability_validity(self) -> ReliabilityComparison:
        measurements = (
            self.baseline_success_rate,
            self.candidate_success_rate,
            self.delta,
            self.delta_lower_bound,
            self.delta_upper_bound,
            self.baseline_consistency_at_k,
            self.candidate_consistency_at_k,
            self.consistency_delta,
            self.consistency_delta_lower_bound,
            self.consistency_delta_upper_bound,
        )
        if self.valid != all(value is not None for value in measurements):
            raise PydanticCustomError(
                "reliability_validity",
                "valid reliability requires every estimate and invalid reliability forbids them",
            )
        if self.valid and self.invalid_reason is not None:
            raise PydanticCustomError(
                "reliability_invalid_reason",
                "valid reliability cannot have an invalid reason",
            )
        if not self.valid and not self.invalid_reason:
            raise PydanticCustomError(
                "reliability_invalid_reason",
                "invalid reliability requires an invalid reason",
            )
        if self.valid:
            delta = self.delta
            delta_lower = self.delta_lower_bound
            delta_upper = self.delta_upper_bound
            consistency_delta = self.consistency_delta
            consistency_lower = self.consistency_delta_lower_bound
            consistency_upper = self.consistency_delta_upper_bound
            if (
                delta is None
                or delta_lower is None
                or delta_upper is None
                or consistency_delta is None
                or consistency_lower is None
                or consistency_upper is None
            ):
                raise PydanticCustomError(
                    "reliability_validity",
                    "valid reliability requires every confidence bound",
                )
            if not delta_lower <= delta <= delta_upper:
                raise PydanticCustomError(
                    "reliability_bounds",
                    "reliability delta must lie within its confidence bounds",
                )
            if not consistency_lower <= consistency_delta <= consistency_upper:
                raise PydanticCustomError(
                    "reliability_consistency_bounds",
                    "consistency delta must lie within its confidence bounds",
                )
        return self


class ResourceCheck(EvalContract):
    metric: str = Field(min_length=1, max_length=160)
    valid: bool = True
    passed: bool
    detail: str = Field(min_length=1, max_length=800)

    @model_validator(mode="after")
    def invalid_evidence_cannot_pass(self) -> ResourceCheck:
        if not self.valid and self.passed:
            raise PydanticCustomError(
                "resource_check_validity",
                "an invalid resource check cannot pass",
            )
        return self


class PromotionDecision(EvalContract):
    status: DecisionStatus
    epi: Optional[float]
    primary_dimension: QualityDimension
    protected_floor: Optional[float]
    reasons: Tuple[str, ...] = Field(min_length=1)


class ComparisonReport(EvalContract):
    protocol_version: str = Field(min_length=1, max_length=40)
    baseline_candidate_id: str = Field(min_length=1, max_length=160)
    candidate_id: str = Field(min_length=1, max_length=160)
    baseline_candidate_spec_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_spec_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    required_p0_families: Tuple[str, ...] = Field(min_length=1)
    covered_p0_families: Tuple[str, ...]
    effects: Tuple[DimensionEffect, ...]
    gate_violations: Tuple[GateViolation, ...]
    reliability: ReliabilityComparison
    resource_checks: Tuple[ResourceCheck, ...]
    judge_calibration: Optional[JudgeCalibrationReport]
    holdout_confirmation: Optional[EvaluationConfirmation]
    constitutional_anchor_confirmation: Optional[EvaluationConfirmation]
    decision: PromotionDecision

    @model_validator(mode="after")
    def validate_p0_coverage_summary(self) -> ComparisonReport:
        if len(set(self.required_p0_families)) != len(self.required_p0_families):
            raise PydanticCustomError(
                "comparison_p0_required",
                "required_p0_families must be unique",
            )
        if len(set(self.covered_p0_families)) != len(self.covered_p0_families):
            raise PydanticCustomError(
                "comparison_p0_covered",
                "covered_p0_families must be unique",
            )
        if not set(self.covered_p0_families).issubset(self.required_p0_families):
            raise PydanticCustomError(
                "comparison_p0_covered",
                "covered_p0_families must be a subset of required_p0_families",
            )
        return self


__all__ = (
    "CandidateSpec",
    "CapabilityUseEvidence",
    "CompletionClaimEvidence",
    "ComparisonReport",
    "ConfirmationKind",
    "DecisionStatus",
    "DimensionEffect",
    "DisclosureEvidence",
    "EffectEvidence",
    "EffectStatus",
    "EpisodeEvidence",
    "EvaluationConfirmation",
    "ExternalDomain",
    "GateViolation",
    "IdentityChangeEvidence",
    "HumanAnchor",
    "JudgeCalibrationReport",
    "JudgeEvidencePacket",
    "JudgeEvidenceSlot",
    "JudgeObservableFact",
    "JudgePreference",
    "JudgeVote",
    "ModelExecutionEvidence",
    "PairwiseOutcome",
    "PresentationOrder",
    "PromotionDecision",
    "PromotionPolicy",
    "QualityDimension",
    "RawJudgeResult",
    "ReliabilityComparison",
    "ResourceCheck",
    "ResourceBudget",
    "ResourceObservation",
    "RunSpec",
    "ScenarioFamily",
    "ScenarioFixture",
    "ScenarioScale",
    "ScenarioSuite",
    "ScenarioVerdict",
    "ScenarioVerdictSource",
    "SourceDomain",
    "SlotPreference",
    "TurnEvidence",
    "contract_sha256",
)
