from __future__ import annotations

import subprocess
from datetime import datetime, timezone

from devtools.brain_eval.contracts import QualityDimension
from devtools.elfie_lab.evaluation_models import (
    EvaluationDimensionResult,
    EvaluationScenarioResult,
    EvaluationViolation,
    LabEvaluationResultStatus,
    LabEvaluationRun,
    LabEvaluationStatus,
    LabEvaluationSuite,
    LabEvaluationVerdict,
)
from devtools.elfie_lab.evaluation_presets import scenarios_for_suite
from devtools.elfie_lab.evaluation_service import (
    EvaluationService,
    _parse_judge_response,
    _score_dimensions,
    _source_state,
    _summarize_absolute_dimensions,
)


def test_standard_score_is_versioned_and_p0_aware() -> None:
    dimensions = tuple(
        EvaluationDimensionResult(
            dimension=dimension,
            label=dimension.value,
            status=LabEvaluationResultStatus.PASSED,
            score=100.0,
        )
        for dimension in QualityDimension
    )

    score, coverage, grade = _score_dimensions(dimensions)

    assert score == 100.0
    assert coverage == 1.0
    assert grade.value == "A"
    violation = EvaluationViolation(
        code="P0", title="测试红线", evidence=("evidence-1",)
    )
    assert (
        _score_dimensions(dimensions, p0_violations=(violation,))[2].value
        == "P0_FAILED"
    )


def test_score_dimensions_uses_dimension_weights_and_coverage() -> None:
    dimensions = (
        EvaluationDimensionResult(
            dimension=QualityDimension.IDENTITY_CONTINUITY,
            label="角色",
            status=LabEvaluationResultStatus.PASSED,
            weight=1.0,
            score=100.0,
        ),
        EvaluationDimensionResult(
            dimension=QualityDimension.MEMORY_RELATIONSHIPS,
            label="记忆",
            status=LabEvaluationResultStatus.EVIDENCE_READY,
            weight=3.0,
            score=50.0,
        ),
    )

    score, coverage, grade = _score_dimensions(dimensions)

    assert score == 62.5
    assert coverage == 1.0
    assert grade.value == "D"


def test_absolute_dimensions_use_observed_scenario_scores() -> None:
    scenarios = scenarios_for_suite(LabEvaluationSuite.QUICK, elfie_name="小岚")
    rows = tuple(
        EvaluationScenarioResult(
            index=index,
            family_id=item.definition.scenario_family_id,
            title=item.title,
            purpose=item.purpose,
            dimension=item.dimension,
            status=(
                LabEvaluationResultStatus.PASSED
                if index == 1
                else LabEvaluationResultStatus.EVIDENCE_READY
            ),
            candidate_score=100.0 if index == 1 else 80.0,
        )
        for index, item in enumerate(scenarios)
    )

    dimensions = _summarize_absolute_dimensions(rows, scenarios)

    identity = next(
        item
        for item in dimensions
        if item.dimension is QualityDimension.IDENTITY_CONTINUITY
    )
    assert identity.score == 100.0
    assert identity.scoring_rule == "absolute-scenario-status-v1"


def test_judge_response_preserves_confidence_and_rationale() -> None:
    result = _parse_judge_response(
        '{"preference":"B","evidence":["B:output:0"],'
        '"confidence":0.75,"rationale":["候选回答更完整"]}'
    )

    assert result.confidence == 0.75
    assert result.rationale == ("候选回答更完整",)


def test_service_recovers_interrupted_run_as_failed(tmp_path) -> None:
    root = tmp_path / "evaluations"
    elfie_id = "elfie_recovery"
    run = LabEvaluationRun(
        run_id="evaluation_interrupted",
        elfie_id=elfie_id,
        suite=LabEvaluationSuite.QUICK,
        status=LabEvaluationStatus.RUNNING,
        verdict=LabEvaluationVerdict.INCOMPLETE,
        created_at=datetime.now(timezone.utc),
        source_revision="1234567",
        source_dirty=False,
        source_snapshot_sha256="c" * 64,
        candidate_label="1234567",
        candidate_spec_sha256="a" * 64,
        fixture_sha256="b" * 64,
        food_key="mock",
        food_model="ollama/elfie-mock",
        judge_subscription_id="mock",
        judge_model="ollama/elfie-mock",
        judge_spec_sha256="d" * 64,
        total_scenarios=1,
        completed_scenarios=0,
        scenarios=(
            EvaluationScenarioResult(
                family_id="q1-anchor-continuity",
                title="角色锚点连续性",
                purpose="验证异常退出恢复",
                dimension=QualityDimension.IDENTITY_CONTINUITY,
                status=LabEvaluationResultStatus.RUNNING,
            ),
        ),
    )
    directory = root / elfie_id
    directory.mkdir(parents=True)
    (directory / f"{run.run_id}.json").write_text(
        run.model_dump_json(indent=2),
        encoding="utf-8",
    )

    service = EvaluationService(root, str(tmp_path / "runtime"))
    try:
        recovered = service.get_run(elfie_id, run.run_id)
    finally:
        service.close()

    assert recovered.status is LabEvaluationStatus.FAILED
    assert recovered.verdict is LabEvaluationVerdict.INCOMPLETE
    assert recovered.completed_at is not None
    assert recovered.scenarios[0].status is LabEvaluationResultStatus.INCOMPLETE
    assert recovered.error == "Elfie Lab 上次退出，评测未能完成"
    assert "可重新运行" in recovered.warnings[-1]


def test_source_snapshot_changes_for_each_dirty_worktree_state(tmp_path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init")
    source = repository / "brain.txt"
    source.write_text("baseline\n", encoding="utf-8")
    _git(repository, "add", "brain.txt")
    _git(
        repository,
        "-c",
        "user.name=Elfie Test",
        "-c",
        "user.email=elfie@example.invalid",
        "commit",
        "-m",
        "baseline",
    )

    revision, dirty, clean_snapshot = _source_state(repository)
    source.write_text("candidate one\n", encoding="utf-8")
    first_revision, first_dirty, first_snapshot = _source_state(repository)
    untracked = repository / "new-policy.txt"
    untracked.write_text("untracked one\n", encoding="utf-8")
    second_revision, second_dirty, second_snapshot = _source_state(repository)
    untracked.write_text("untracked two\n", encoding="utf-8")
    _, _, third_snapshot = _source_state(repository)

    assert revision == first_revision == second_revision
    assert dirty is False
    assert first_dirty is second_dirty is True
    assert len({clean_snapshot, first_snapshot, second_snapshot, third_snapshot}) == 4


def _git(repository, *arguments: str) -> None:
    subprocess.run(
        ("git", *arguments),
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
