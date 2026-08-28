"""Batch-oriented Elfie Lab evaluation reports and immutable comparisons."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Mapping, Optional, Sequence, Tuple

from devtools.brain_eval.contracts import EpisodeEvidence
from devtools.brain_eval.gates import evaluate_p0_gates
from devtools.elfie_lab.evaluation_models import (
    EvaluationComparisonScenario,
    EvaluationDimensionResult,
    EvaluationScenarioResult,
    EvaluationViolation,
    LabEvaluationBatch,
    LabEvaluationBatchKind,
    LabEvaluationBatchStatus,
    LabEvaluationComparison,
    LabEvaluationComparisonGrade,
    LabEvaluationComparisonVariable,
    LabEvaluationResultStatus,
    LabEvaluationRun,
    LabEvaluationStatus,
    LabEvaluationSuite,
    LabEvaluationVerdict,
)
from devtools.elfie_lab.evaluation_presets import (
    BuiltinEvaluationScenario,
    scenarios_for_suite,
)
from devtools.elfie_lab.evaluation_service import (
    SCORING_VERSION,
    EvaluationService,
    _apply_deterministic_verdict,
    _assertion_results,
    _captured_status,
    _code_branch_refs,
    _compare_scenario,
    _current_source_ref,
    _episode_score,
    _fixture_from_profile,
    _food_fingerprint,
    _merge_dimension_scores,
    _overall_verdict,
    _resolve_source_ref,
    _reviewer_fingerprint,
    _run_validity,
    _scenario_assertions,
    _scenario_inputs,
    _scenario_steps,
    _score_dimensions,
    _sha256_json,
    _source_state_for_ref,
    _sum_optional_metric,
    _summarize_absolute_dimensions,
    _summarize_dimensions,
    _utc_now,
    _validate_id,
)
from devtools.elfie_lab.reviewer_subscriptions import (
    ReviewerModelExecutionAgent,
    ReviewerSubscriptionStore,
)
from devtools.elfie_lab.schemas import ElfieSpec, new_id
from devtools.elfie_lab.session import ElfieLabSession

_EXECUTION_RULES = (
    "场景按测试计划固定顺序执行",
    "每个场景从同一冻结快照重新开始",
    "场景与随机种子固定",
    "候选输出匿名后交给同一评审模型",
)

_BRANCH_EPISODE_WORKER = r"""
from __future__ import annotations

import json
import inspect
import sys
from pathlib import Path

input_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
payload = json.loads(input_path.read_text(encoding="utf-8"))
sys.path.insert(0, str(Path.cwd()))

from devtools.brain_eval.lab_runner import LabFixtureDefinition, LabScenarioDefinition, capture_lab_episode

capture_kwargs = {
    "candidate_id": payload["candidate_id"],
    "candidate_spec_sha256": payload["candidate_spec_sha256"],
    "fixture": LabFixtureDefinition.model_validate(payload["fixture"]),
    "scenario": LabScenarioDefinition.model_validate(payload["scenario"]),
    "food_key": payload["food_key"],
    "runtime_root": Path(payload["runtime_root"]),
}
supported = inspect.signature(capture_lab_episode).parameters
if "fixture_snapshot_root" in supported:
    capture_kwargs["fixture_snapshot_root"] = Path(payload["fixture_snapshot_root"])
if "model_config_dir" in supported:
    capture_kwargs["model_config_dir"] = payload["model_config_dir"]
episode = capture_lab_episode(**capture_kwargs)
output_path.write_text(json.dumps(episode.model_dump(mode="json")), encoding="utf-8")
"""


class BatchEvaluationService(EvaluationService):
    """Add global report batches without changing legacy per-Elfie history APIs."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._batch_root.mkdir(parents=True, exist_ok=True)
        self._comparison_root.mkdir(parents=True, exist_ok=True)
        self._snapshot_root.mkdir(parents=True, exist_ok=True)
        self._recover_batches()

    @property
    def _batch_root(self) -> Path:
        return self.root / "_batches"

    @property
    def _comparison_root(self) -> Path:
        return self.root / "_comparisons"

    @property
    def _snapshot_root(self) -> Path:
        return self.root / "_snapshots"

    def start_single_batch(
        self,
        *,
        spec: ElfieSpec,
        session: ElfieLabSession,
        suite: LabEvaluationSuite,
        food_key: str,
        judge_subscription_id: str,
        food_descriptor: Mapping[str, Any],
        judge_subscription_descriptor: Mapping[str, Any],
        title: str,
        purpose: str,
        judge_model: str = "",
    ) -> LabEvaluationBatch:
        fixture, snapshot_id, captured_at = self._capture_fixture(spec, session)
        source_ref = _current_source_ref(self._project_root)
        source = _source_state_for_ref(self._project_root, source_ref)
        batch_id = new_id("evaluation_batch")
        run = self._build_report(
            spec=spec,
            fixture=fixture,
            snapshot_id=snapshot_id,
            captured_at=captured_at,
            suite=suite,
            food_key=food_key,
            judge_subscription_id=judge_subscription_id,
            food_descriptor=food_descriptor,
            judge_subscription_descriptor=judge_subscription_descriptor,
            judge_model=judge_model,
            title=title,
            purpose=purpose,
            batch_id=batch_id,
            batch_role=None,
            source=source,
            source_ref=source_ref,
        )
        batch = LabEvaluationBatch(
            batch_id=batch_id,
            kind=LabEvaluationBatchKind.SINGLE,
            status=LabEvaluationBatchStatus.PENDING,
            purpose=purpose,
            title=title,
            elfie_id=spec.elfie_id,
            elfie_name=spec.name,
            suite=suite,
            fixture_snapshot_id=snapshot_id,
            fixture_sha256=run.fixture_sha256,
            test_plan_sha256=run.test_plan_sha256,
            report_ids=(run.run_id,),
            created_at=_utc_now(),
        )
        self._write_run(run)
        self._write_batch(batch)
        self._executor.submit(
            self._execute_single_batch,
            batch.batch_id,
            run.run_id,
            fixture,
            scenarios_for_suite(suite, elfie_name=spec.name),
            self._snapshot_path(snapshot_id),
            source_ref,
        )
        return self.get_batch(batch_id)

    def start_food_pair_batch(
        self,
        *,
        spec: ElfieSpec,
        session: ElfieLabSession,
        suite: LabEvaluationSuite,
        food_key_a: str,
        food_key_b: str,
        judge_subscription_id: str,
        food_descriptor_a: Mapping[str, Any],
        food_descriptor_b: Mapping[str, Any],
        judge_subscription_descriptor: Mapping[str, Any],
        title: str,
        purpose: str,
        judge_model: str = "",
    ) -> LabEvaluationBatch:
        fixture, snapshot_id, captured_at = self._capture_fixture(spec, session)
        source_ref = _current_source_ref(self._project_root)
        source = _source_state_for_ref(self._project_root, source_ref)
        batch_id = new_id("evaluation_batch")
        shared = {
            "spec": spec,
            "fixture": fixture,
            "snapshot_id": snapshot_id,
            "captured_at": captured_at,
            "suite": suite,
            "judge_subscription_id": judge_subscription_id,
            "judge_subscription_descriptor": judge_subscription_descriptor,
            "judge_model": judge_model,
            "title": title,
            "purpose": purpose,
            "batch_id": batch_id,
            "source": source,
            "source_ref": source_ref,
        }
        report_a = self._build_report(
            **shared,
            food_key=food_key_a,
            food_descriptor=food_descriptor_a,
            batch_role="A",
        )
        report_b = self._build_report(
            **shared,
            food_key=food_key_b,
            food_descriptor=food_descriptor_b,
            batch_role="B",
        )
        batch = LabEvaluationBatch(
            batch_id=batch_id,
            kind=LabEvaluationBatchKind.PAIRED,
            status=LabEvaluationBatchStatus.PENDING,
            comparison_variable=LabEvaluationComparisonVariable.FOOD,
            purpose=purpose,
            title=title,
            elfie_id=spec.elfie_id,
            elfie_name=spec.name,
            suite=suite,
            fixture_snapshot_id=snapshot_id,
            fixture_sha256=report_a.fixture_sha256,
            test_plan_sha256=report_a.test_plan_sha256,
            report_ids=(report_a.run_id, report_b.run_id),
            created_at=_utc_now(),
        )
        self._write_run(report_a)
        self._write_run(report_b)
        self._write_batch(batch)
        self._executor.submit(
            self._execute_food_pair_batch,
            batch_id,
            report_a.run_id,
            report_b.run_id,
            fixture,
            scenarios_for_suite(suite, elfie_name=spec.name),
            self._snapshot_path(snapshot_id),
            source_ref,
        )
        return self.get_batch(batch_id)

    def start_code_pair_batch(
        self,
        *,
        spec: ElfieSpec,
        session: ElfieLabSession,
        suite: LabEvaluationSuite,
        food_key: str,
        judge_subscription_id: str,
        food_descriptor: Mapping[str, Any],
        judge_subscription_descriptor: Mapping[str, Any],
        code_ref_a: str,
        code_ref_b: str,
        title: str,
        purpose: str,
        judge_model: str = "",
    ) -> LabEvaluationBatch:
        normalized_a = code_ref_a.strip()
        normalized_b = code_ref_b.strip()
        if normalized_a == normalized_b:
            raise ValueError("代码分支 A 与代码分支 B 必须不同")
        source_a = _source_state_for_ref(self._project_root, normalized_a)
        source_b = _source_state_for_ref(self._project_root, normalized_b)
        fixture, snapshot_id, captured_at = self._capture_fixture(spec, session)
        batch_id = new_id("evaluation_batch")
        shared = {
            "spec": spec,
            "fixture": fixture,
            "snapshot_id": snapshot_id,
            "captured_at": captured_at,
            "suite": suite,
            "food_key": food_key,
            "judge_subscription_id": judge_subscription_id,
            "food_descriptor": food_descriptor,
            "judge_subscription_descriptor": judge_subscription_descriptor,
            "judge_model": judge_model,
            "title": title,
            "purpose": purpose,
            "batch_id": batch_id,
        }
        report_a = self._build_report(
            **shared,
            batch_role="A",
            source=source_a,
            source_ref=normalized_a,
        )
        report_b = self._build_report(
            **shared,
            batch_role="B",
            source=source_b,
            source_ref=normalized_b,
        )
        batch = LabEvaluationBatch(
            batch_id=batch_id,
            kind=LabEvaluationBatchKind.PAIRED,
            status=LabEvaluationBatchStatus.PENDING,
            comparison_variable=LabEvaluationComparisonVariable.CODE,
            title=title,
            purpose=purpose,
            elfie_id=spec.elfie_id,
            elfie_name=spec.name,
            suite=suite,
            fixture_snapshot_id=snapshot_id,
            fixture_sha256=report_a.fixture_sha256,
            test_plan_sha256=report_a.test_plan_sha256,
            report_ids=(report_a.run_id, report_b.run_id),
            created_at=_utc_now(),
        )
        self._write_run(report_a)
        self._write_run(report_b)
        self._write_batch(batch)
        self._executor.submit(
            self._execute_code_pair_batch,
            batch_id,
            report_a.run_id,
            report_b.run_id,
            fixture,
            scenarios_for_suite(suite, elfie_name=spec.name),
            self._snapshot_path(snapshot_id),
            normalized_a,
            normalized_b,
        )
        return self.get_batch(batch_id)

    def code_branches(self) -> dict[str, object]:
        current = _current_source_ref(self._project_root)
        return {
            "current_ref": current,
            "items": [
                {"name": name, "is_current": name == current}
                for name in _code_branch_refs(self._project_root)
            ],
        }

    def list_batches(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        query: str = "",
        status: str = "",
        created_after: Optional[datetime] = None,
    ) -> dict[str, object]:
        stored = [
            self._read_batch_path(path) for path in self._batch_root.glob("*.json")
        ]
        batches = [item for item in stored if item is not None]
        claimed = {report_id for item in batches for report_id in item.report_ids}
        for run in self._all_reports():
            if run.run_id in claimed:
                continue
            batches.append(
                LabEvaluationBatch(
                    batch_id=f"legacy-{run.run_id}",
                    kind=LabEvaluationBatchKind.SINGLE,
                    status=_batch_status_for_runs((run,)),
                    title=run.title,
                    purpose=run.purpose,
                    elfie_id=run.elfie_id,
                    elfie_name=run.elfie_name,
                    suite=run.suite,
                    fixture_snapshot_id=run.fixture_snapshot_id,
                    fixture_sha256=run.fixture_sha256,
                    test_plan_sha256=run.test_plan_sha256,
                    report_ids=(run.run_id,),
                    created_at=run.created_at,
                    completed_at=(
                        run.completed_at
                        if run.status
                        in {LabEvaluationStatus.COMPLETED, LabEvaluationStatus.FAILED}
                        else None
                    ),
                    error=run.error,
                )
            )
        needle = query.casefold().strip()
        records = []
        for batch in batches:
            try:
                reports = tuple(self.get_report(item) for item in batch.report_ids)
            except KeyError:
                # Developer Tools data is intentionally isolated and may be
                # rebuilt between schema iterations. A stale report must not
                # make the complete report library unavailable.
                continue
            refreshed = self._refresh_batch(batch, reports)
            searchable = " ".join(
                (
                    refreshed.batch_id,
                    refreshed.elfie_id,
                    refreshed.elfie_name,
                    refreshed.title,
                    refreshed.purpose,
                    *(report.run_id for report in reports),
                    *(
                        report.food_display_name or report.food_model
                        for report in reports
                    ),
                )
            ).casefold()
            if needle and needle not in searchable:
                continue
            if status and refreshed.status.value != status:
                continue
            if created_after is not None and refreshed.created_at < created_after:
                continue
            records.append((refreshed, reports))
        records.sort(key=lambda item: item[0].created_at, reverse=True)
        page = records[offset : offset + limit]
        return {
            "items": [self._batch_payload(batch, reports) for batch, reports in page],
            "total": len(records),
            "offset": offset,
            "limit": limit,
        }

    def get_batch(self, batch_id: str) -> LabEvaluationBatch:
        path = self._batch_path(batch_id)
        if not path.is_file():
            raise KeyError(f"评测批次不存在: {batch_id}")
        batch = LabEvaluationBatch.model_validate_json(path.read_text(encoding="utf-8"))
        reports = tuple(self.get_report(item) for item in batch.report_ids)
        return self._refresh_batch(batch, reports)

    def batch_payload(self, batch_id: str) -> dict[str, object]:
        batch = self.get_batch(batch_id)
        reports = tuple(self.get_report(item) for item in batch.report_ids)
        return self._batch_payload(batch, reports)

    def get_report(self, run_id: str) -> LabEvaluationRun:
        _validate_id(run_id)
        for path in self.root.glob(f"*/{run_id}.json"):
            try:
                return LabEvaluationRun.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                continue
        raise KeyError(f"评测报告不存在: {run_id}")

    def evidence_payload(self, run_id: str) -> dict[str, object]:
        """Return on-demand observable episode evidence, never subscription secrets."""

        report = self.get_report(run_id)
        return {
            "run_id": report.run_id,
            "candidate_spec_sha256": report.candidate_spec_sha256,
            "episodes": [
                episode.model_dump(mode="json") for episode in report.episodes
            ],
        }

    def compare_reports(
        self,
        report_a_id: str,
        report_b_id: str,
        *,
        batch_id: Optional[str] = None,
    ) -> LabEvaluationComparison:
        report_a = self.get_report(report_a_id)
        report_b = self.get_report(report_b_id)
        if report_a.status not in {
            LabEvaluationStatus.COMPLETED,
            LabEvaluationStatus.FAILED,
        }:
            raise ValueError("报告 A 尚未完成")
        if report_b.status not in {
            LabEvaluationStatus.COMPLETED,
            LabEvaluationStatus.FAILED,
        }:
            raise ValueError("报告 B 尚未完成")
        hash_a = _report_hash(report_a)
        hash_b = _report_hash(report_b)
        comparison_id = (
            "comparison-"
            + _sha256_json(
                {
                    "report_a_id": report_a_id,
                    "report_b_id": report_b_id,
                    "report_a_sha256": hash_a,
                    "report_b_sha256": hash_b,
                }
            )[:24]
        )
        path = self._comparison_path(comparison_id)
        if path.is_file():
            return LabEvaluationComparison.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        comparison = self._build_comparison(
            comparison_id=comparison_id,
            batch_id=batch_id,
            report_a=report_a,
            report_b=report_b,
            hash_a=hash_a,
            hash_b=hash_b,
        )
        self._write_json(path, comparison.model_dump(mode="json"))
        return comparison

    def _capture_fixture(
        self,
        spec: ElfieSpec,
        session: ElfieLabSession,
    ) -> tuple[Any, str, datetime]:
        snapshot_id = new_id("evaluation_snapshot")
        snapshot_path = self._snapshot_path(snapshot_id)
        snapshot_path.mkdir(parents=True)
        payload = session.capture_evaluation_snapshot(snapshot_path)
        captured_at = _parse_datetime(str(payload["captured_at"]))
        fixture = _fixture_from_profile(
            spec,
            _mapping(payload.get("profile")),
            _mapping(payload.get("current_state")),
            preserve_elfie_id=True,
        )
        return fixture, snapshot_id, captured_at

    def _build_report(
        self,
        *,
        spec: ElfieSpec,
        fixture: Any,
        snapshot_id: str,
        captured_at: datetime,
        suite: LabEvaluationSuite,
        food_key: str,
        judge_subscription_id: str,
        food_descriptor: Mapping[str, Any],
        judge_subscription_descriptor: Mapping[str, Any],
        purpose: str,
        batch_id: str,
        batch_role: Optional[Literal["A", "B"]],
        source: Tuple[str, bool, str],
        title: str = "",
        source_ref: str = "",
        judge_model: str = "",
    ) -> LabEvaluationRun:
        scenarios = scenarios_for_suite(suite, elfie_name=spec.name)
        source_revision, source_dirty, source_snapshot_sha256 = source
        candidate_food = _food_fingerprint(food_key, food_descriptor)
        judge_spec = _reviewer_fingerprint(
            judge_subscription_id,
            judge_subscription_descriptor,
            model_override=judge_model or None,
        )
        food_spec_sha256 = _sha256_json(candidate_food)
        fixture_sha256 = _sha256_json(fixture.model_dump(mode="json"))
        test_plan_sha256 = _test_plan_hash(suite, scenarios)
        candidate_spec_sha256 = _sha256_json(
            {
                "source_revision": source_revision,
                "source_dirty": source_dirty,
                "source_snapshot_sha256": source_snapshot_sha256,
                "food_spec_sha256": food_spec_sha256,
            }
        )
        state = fixture.initial_state
        warnings = [
            "这是开发阶段的探索性自动评测；正式晋级仍需重复样本、人工锚点校准和私有确认集。"
        ]
        if source_dirty:
            warnings.append(
                "当前源码包含未提交改动；报告保留了源码内容哈希，但不能用提交号单独复现。"
            )
        if judge_spec["model"] == candidate_food["model"]:
            warnings.append("评审模型与被测模型相同，软质量判断只作为开发观察证据。")
        rows = tuple(
            EvaluationScenarioResult(
                index=index,
                attempt_id=None,
                family_id=item.definition.scenario_family_id,
                title=item.title,
                purpose=item.purpose,
                dimension=item.dimension,
                status=LabEvaluationResultStatus.PENDING,
                input_messages=_scenario_inputs(item),
                execution_steps=_scenario_steps(item),
                assertions=_scenario_assertions(item),
            )
            for index, item in enumerate(scenarios)
        )
        return LabEvaluationRun(
            run_id=new_id("evaluation"),
            elfie_id=spec.elfie_id,
            elfie_name=spec.name,
            elfie_species_id=spec.species_id,
            batch_id=batch_id,
            batch_role=batch_role,
            title=title,
            purpose=purpose,
            suite=suite,
            status=LabEvaluationStatus.PENDING,
            verdict=LabEvaluationVerdict.INCOMPLETE,
            created_at=_utc_now(),
            source_revision=source_revision,
            source_ref=source_ref,
            source_dirty=source_dirty,
            source_snapshot_sha256=source_snapshot_sha256,
            candidate_label=(f"{source_ref or '当前分支'} · 最新代码"),
            candidate_spec_sha256=candidate_spec_sha256,
            food_spec_sha256=food_spec_sha256,
            fixture_sha256=fixture_sha256,
            fixture_snapshot_id=snapshot_id,
            fixture_captured_at=captured_at,
            fixture_memory_count=int(state.get("memory_count", 0)),
            fixture_activity_count=int(state.get("activity_count", 0)),
            fixture_journal_count=int(
                _mapping(state.get("journal")).get("entry_count", 0)
            ),
            test_plan_key=f"{suite.value}-v1",
            test_plan_title="快速检查 v1"
            if suite is LabEvaluationSuite.QUICK
            else "标准评测 v1",
            test_plan_sha256=test_plan_sha256,
            execution_rules=_EXECUTION_RULES,
            food_key=food_key,
            food_display_name=str(food_descriptor.get("display_name") or food_key),
            food_model=str(candidate_food["model"]),
            judge_subscription_id=judge_subscription_id,
            judge_model=str(judge_spec["model"]),
            judge_spec_sha256=_sha256_json(judge_spec),
            total_scenarios=len(rows),
            completed_scenarios=0,
            scenarios=rows,
            scenario_order=tuple(item.family_id for item in rows),
            warnings=tuple(warnings),
        )

    def _execute_single_batch(
        self,
        batch_id: str,
        run_id: str,
        fixture: Any,
        scenarios: Tuple[BuiltinEvaluationScenario, ...],
        snapshot_path: Path,
        source_ref: str,
    ) -> None:
        self._mark_batch_running(batch_id)
        self._execute_absolute_report(
            run_id, fixture, scenarios, snapshot_path, source_ref
        )
        batch = self.get_batch(batch_id)
        self._write_batch(batch)

    def _execute_food_pair_batch(
        self,
        batch_id: str,
        report_a_id: str,
        report_b_id: str,
        fixture: Any,
        scenarios: Tuple[BuiltinEvaluationScenario, ...],
        snapshot_path: Path,
        source_ref: str,
    ) -> None:
        self._mark_batch_running(batch_id)
        self._execute_absolute_report(
            report_a_id, fixture, scenarios, snapshot_path, source_ref
        )
        self._execute_absolute_report(
            report_b_id, fixture, scenarios, snapshot_path, source_ref
        )
        self._finish_pair_batch(batch_id, report_a_id, report_b_id)

    def _execute_code_pair_batch(
        self,
        batch_id: str,
        report_a_id: str,
        report_b_id: str,
        fixture: Any,
        scenarios: Tuple[BuiltinEvaluationScenario, ...],
        snapshot_path: Path,
        source_ref_a: str,
        source_ref_b: str,
    ) -> None:
        self._mark_batch_running(batch_id)
        self._execute_absolute_report(
            report_a_id, fixture, scenarios, snapshot_path, source_ref_a
        )
        self._execute_absolute_report(
            report_b_id, fixture, scenarios, snapshot_path, source_ref_b
        )
        self._finish_pair_batch(batch_id, report_a_id, report_b_id)

    @contextmanager
    def _source_checkout(self, source_ref: str):
        """Materialize a branch commit without changing the user's checkout."""

        resolved_ref = _resolve_source_ref(self._project_root, source_ref)
        with tempfile.TemporaryDirectory(
            prefix="elfienest-evaluation-worktree-"
        ) as parent:
            worktree = Path(parent) / "source"
            worktree.mkdir()
            result = subprocess.run(
                ("git", "archive", "--format=tar", resolved_ref),
                cwd=self._project_root,
                capture_output=True,
                check=False,
                timeout=30,
            )
            if result.returncode != 0:
                detail = (
                    result.stderr.decode("utf-8", "replace").strip()
                    or result.stdout.decode("utf-8", "replace").strip()
                    or "无法创建代码工作树"
                )
                raise RuntimeError(f"无法准备代码分支 {source_ref}: {detail}")
            with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
                archive.extractall(worktree)
            runner = worktree / "devtools" / "brain_eval" / "lab_runner.py"
            if not runner.is_file():
                raise RuntimeError(
                    f"代码分支 {source_ref} 缺少 devtools.brain_eval 评测运行器"
                )
            # Older refs eagerly import the web app from the package initializer.
            # The branch worker only needs the Brain scenario runner, so keep the
            # package boundary lazy while importing the candidate source snapshot.
            (worktree / "devtools" / "elfie_lab" / "__init__.py").write_text(
                '"""Evaluation source snapshot import shim."""\n',
                encoding="utf-8",
            )
            yield worktree

    def _capture_branch_episode(
        self,
        *,
        source_ref: str,
        candidate_id: str,
        candidate_spec_sha256: str,
        fixture: Any,
        scenario: BuiltinEvaluationScenario,
        food_key: str,
        runtime_root: Path,
        fixture_snapshot_root: Path,
    ) -> EpisodeEvidence:
        with self._source_checkout(source_ref) as source_root:
            return self._capture_branch_episode_in_checkout(
                source_root=source_root,
                candidate_id=candidate_id,
                candidate_spec_sha256=candidate_spec_sha256,
                fixture=fixture,
                scenario=scenario,
                food_key=food_key,
                runtime_root=runtime_root,
                fixture_snapshot_root=fixture_snapshot_root,
            )

    def _capture_branch_episode_in_checkout(
        self,
        *,
        source_root: Path,
        candidate_id: str,
        candidate_spec_sha256: str,
        fixture: Any,
        scenario: BuiltinEvaluationScenario,
        food_key: str,
        runtime_root: Path,
        fixture_snapshot_root: Path,
    ) -> EpisodeEvidence:
        # Older branch runners do not accept an explicit model-config directory
        # and default to ``runtime_root/runtime_config``. Copy the isolated Lab
        # model catalog there so those refs still use the selected test Food.
        legacy_config_root = runtime_root / "runtime_config"
        if Path(self.model_config_dir).is_dir():
            shutil.copytree(
                Path(self.model_config_dir),
                legacy_config_root,
                dirs_exist_ok=True,
            )
        input_path = runtime_root / "branch-worker-input.json"
        output_path = runtime_root / "branch-worker-output.json"
        input_path.write_text(
            json.dumps(
                {
                    "candidate_id": candidate_id,
                    "candidate_spec_sha256": candidate_spec_sha256,
                    "fixture": fixture.model_dump(mode="json"),
                    "scenario": scenario.definition.model_dump(mode="json"),
                    "food_key": food_key,
                    "runtime_root": str(runtime_root / "brain"),
                    "fixture_snapshot_root": str(fixture_snapshot_root),
                    "model_config_dir": self.model_config_dir,
                }
            ),
            encoding="utf-8",
        )
        environment = os.environ.copy()
        existing_python_path = environment.get("PYTHONPATH", "")
        environment["PYTHONPATH"] = str(source_root) + (
            os.pathsep + existing_python_path if existing_python_path else ""
        )
        result = subprocess.run(
            (
                sys.executable,
                "-c",
                _BRANCH_EPISODE_WORKER,
                str(input_path),
                str(output_path),
            ),
            cwd=source_root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        if result.returncode != 0 or not output_path.is_file():
            detail = (
                result.stderr.strip() or result.stdout.strip() or "代码分支场景执行失败"
            )
            raise RuntimeError(detail[-1200:])
        return EpisodeEvidence.model_validate_json(
            output_path.read_text(encoding="utf-8")
        )

    def _execute_absolute_report(
        self,
        run_id: str,
        fixture: Any,
        scenarios: Tuple[BuiltinEvaluationScenario, ...],
        snapshot_path: Path,
        source_ref: str,
    ) -> None:
        run = self.get_report(run_id).model_copy(
            update={"status": LabEvaluationStatus.RUNNING}
        )
        self._write_run(run)
        episodes = []
        rows = list(run.scenarios)
        violations: list[EvaluationViolation] = []
        for index, scenario in enumerate(scenarios):
            rows[index] = rows[index].model_copy(
                update={
                    "status": LabEvaluationResultStatus.RUNNING,
                    "attempt_id": f"{run.run_id}:{index}:1",
                }
            )
            self._write_run(run.model_copy(update={"scenarios": tuple(rows)}))
            try:
                with tempfile.TemporaryDirectory(
                    prefix="elfienest-lab-evaluation-"
                ) as temporary:
                    if self._is_current_source_ref(source_ref):
                        episode = self._episode_capturer(
                            candidate_id=run.run_id,
                            candidate_spec_sha256=run.candidate_spec_sha256,
                            fixture=fixture,
                            scenario=scenario.definition,
                            food_key=run.food_key,
                            runtime_root=Path(temporary),
                            model_config_dir=self.model_config_dir,
                        )
                    else:
                        episode = self._capture_branch_episode(
                            source_ref=source_ref,
                            candidate_id=run.run_id,
                            candidate_spec_sha256=run.candidate_spec_sha256,
                            fixture=fixture,
                            scenario=scenario,
                            food_key=run.food_key,
                            runtime_root=Path(temporary),
                            fixture_snapshot_root=snapshot_path,
                        )
                episode = _apply_deterministic_verdict(episode, scenario)
                episodes.append(episode)
                p0 = evaluate_p0_gates((episode,))
                violations.extend(
                    EvaluationViolation(
                        code=item.code,
                        title=item.message,
                        evidence=item.evidence_ids,
                    )
                    for item in p0
                )
                verdict_evidence = (
                    episode.scenario_verdict.evidence
                    if episode.scenario_verdict is not None
                    else ("场景已完成并保留原始证据，尚无绝对质量标尺。",)
                )
                rows[index] = rows[index].model_copy(
                    update={
                        "status": _captured_status(episode, p0),
                        "candidate_outputs": episode.public_outputs,
                        "evidence": tuple(
                            item for violation in p0 for item in violation.evidence_ids
                        )
                        or verdict_evidence,
                        "latency_ms": episode.resources.latency_ms,
                        "model_calls": episode.resources.model_calls,
                        "input_tokens": episode.resources.input_tokens,
                        "output_tokens": episode.resources.output_tokens,
                        "cost_microunits": episode.resources.cost_microunits,
                        "candidate_score": _episode_score(episode),
                        "assertion_results": _assertion_results(episode, scenario),
                    }
                )
            except Exception as error:
                rows[index] = rows[index].model_copy(
                    update={
                        "status": LabEvaluationResultStatus.INCOMPLETE,
                        "error": f"{type(error).__name__}: {str(error)[:420]}"[:500],
                        "evidence": ("场景执行失败，未生成可判断证据",),
                    }
                )
            run = run.model_copy(
                update={
                    "completed_scenarios": index + 1,
                    "scenarios": tuple(rows),
                    "episodes": tuple(episodes),
                    "p0_violations": tuple(violations),
                    "total_model_calls": sum(
                        item.resources.model_calls for item in episodes
                    ),
                    "total_latency_ms": sum(
                        item.resources.latency_ms for item in episodes
                    ),
                    "total_input_tokens": _sum_optional_metric(
                        item.resources.input_tokens for item in episodes
                    ),
                    "total_output_tokens": _sum_optional_metric(
                        item.resources.output_tokens for item in episodes
                    ),
                    "total_cost_microunits": _sum_optional_metric(
                        item.resources.cost_microunits for item in episodes
                    ),
                }
            )
            self._write_run(run)
        finished = _finish_absolute(run, scenarios)
        self._write_run(finished)

    def _is_current_source_ref(self, source_ref: str) -> bool:
        """Run the selected checkout in-process when it is the active worktree."""

        normalized = source_ref.strip()
        return normalized in {
            _current_source_ref(self._project_root),
            "HEAD",
        }

    def _finish_pair_batch(
        self,
        batch_id: str,
        report_a_id: str,
        report_b_id: str,
    ) -> None:
        batch = self.get_batch(batch_id)
        reports = (self.get_report(report_a_id), self.get_report(report_b_id))
        status = _batch_status_for_runs(reports)
        comparison_id = None
        error = None
        if status is LabEvaluationBatchStatus.COMPLETED:
            comparison_id = self.compare_reports(
                report_a_id,
                report_b_id,
                batch_id=batch_id,
            ).comparison_id
        elif status in {
            LabEvaluationBatchStatus.PARTIAL_FAILED,
            LabEvaluationBatchStatus.FAILED,
        }:
            error = "配对评测未完整完成，不生成胜负结论"
        self._write_batch(
            batch.model_copy(
                update={
                    "status": status,
                    "completed_at": _utc_now(),
                    "comparison_artifact_id": comparison_id,
                    "error": error,
                }
            )
        )

    def _build_comparison(
        self,
        *,
        comparison_id: str,
        batch_id: Optional[str],
        report_a: LabEvaluationRun,
        report_b: LabEvaluationRun,
        hash_a: str,
        hash_b: str,
    ) -> LabEvaluationComparison:
        differing = _candidate_differences(report_a, report_b)
        shared_fixture = report_a.fixture_sha256 == report_b.fixture_sha256
        shared_plan = report_a.test_plan_sha256 == report_b.test_plan_sha256
        shared_judge = report_a.judge_spec_sha256 == report_b.judge_spec_sha256
        if not shared_fixture or not shared_plan:
            grade = LabEvaluationComparisonGrade.INCOMPATIBLE
        elif shared_judge and len(differing) == 1:
            grade = LabEvaluationComparisonGrade.STRICT
        else:
            grade = LabEvaluationComparisonGrade.OBSERVATIONAL
        variable = (
            LabEvaluationComparisonVariable.FOOD
            if differing == ("food",)
            else LabEvaluationComparisonVariable.CODE
            if differing == ("code",)
            else None
        )
        warnings = []
        compatibility_reasons = []
        if grade is LabEvaluationComparisonGrade.INCOMPATIBLE:
            warnings.append(
                "两份报告的精灵快照或测试计划不同，只能并排查看，不能给出优劣结论。"
            )
            if not shared_fixture:
                compatibility_reasons.append("fixture_snapshot_mismatch")
            if not shared_plan:
                compatibility_reasons.append("test_plan_mismatch")
        elif grade is LabEvaluationComparisonGrade.OBSERVATIONAL:
            if not differing and shared_judge:
                warnings.append(
                    "两份报告的候选配置相同，本次用于观察重复运行的一致性，不能归因于代码或粮食变化。"
                )
            else:
                warnings.append(
                    "两份报告存在多个变量或评审配置差异，变化只能作为观察，不能归因。"
                )
            if not shared_judge:
                compatibility_reasons.append("judge_configuration_mismatch")
            if len(differing) != 1:
                compatibility_reasons.append("multiple_or_missing_candidate_variables")
        technical_failed = (
            report_a.status is LabEvaluationStatus.FAILED
            or report_b.status is LabEvaluationStatus.FAILED
        )
        if technical_failed:
            warnings.append("至少一份报告技术失败，本次比较不产生胜负结论。")
            compatibility_reasons.append("technical_failure")
        scenario_defs = scenarios_for_suite(
            report_b.suite, elfie_name=report_b.elfie_name or report_b.elfie_id
        )
        scenarios = []
        dimensions: Tuple[EvaluationDimensionResult, ...] = ()
        verdict = LabEvaluationVerdict.INCOMPLETE
        if (
            grade is not LabEvaluationComparisonGrade.INCOMPATIBLE
            and not technical_failed
        ):
            judge_agent = None
            try:
                if report_b.judge_subscription_id != "mock":
                    judge_agent = ReviewerModelExecutionAgent(
                        ReviewerSubscriptionStore(self.model_config_dir).descriptor(
                            report_b.judge_subscription_id,
                            report_b.judge_model,
                        )
                    )
            except Exception as error:
                warnings.append(f"自动评审模型不可用：{type(error).__name__}")
            a_by_family = {item.scenario_family_id: item for item in report_a.episodes}
            b_by_family = {item.scenario_family_id: item for item in report_b.episodes}
            compared_rows = []
            for source_row, definition in zip(report_b.scenarios, scenario_defs):
                episode_a = a_by_family.get(source_row.family_id)
                episode_b = b_by_family.get(source_row.family_id)
                if episode_a is None or episode_b is None:
                    row = source_row.model_copy(
                        update={
                            "status": LabEvaluationResultStatus.INCOMPLETE,
                            "evidence": ("A 或 B 缺少同一场景的原始证据",),
                        }
                    )
                else:
                    row = _compare_scenario(
                        row=source_row,
                        scenario=definition,
                        baseline=episode_a,
                        candidate=episode_b,
                        judge_agent=judge_agent,
                        judge_subscription_id=report_b.judge_subscription_id,
                    )
                compared_rows.append(row)
                scenarios.append(
                    EvaluationComparisonScenario(
                        family_id=row.family_id,
                        title=row.title,
                        purpose=row.purpose,
                        dimension=row.dimension,
                        status=row.status,
                        input_messages=row.input_messages,
                        execution_steps=row.execution_steps,
                        assertions=row.assertions,
                        report_a_outputs=row.baseline_outputs,
                        report_b_outputs=row.candidate_outputs,
                        evidence=row.evidence,
                    )
                )
            dimensions = _merge_dimension_scores(
                _summarize_dimensions(compared_rows, scenario_defs),
                report_a.dimensions,
                report_b.dimensions,
            )
            verdict = _overall_verdict(dimensions, report_b.p0_violations)
        else:
            for row_a, row_b in zip(report_a.scenarios, report_b.scenarios):
                scenarios.append(
                    EvaluationComparisonScenario(
                        family_id=row_b.family_id,
                        title=row_b.title,
                        purpose=row_b.purpose,
                        dimension=row_b.dimension,
                        status=LabEvaluationResultStatus.INCOMPLETE,
                        input_messages=row_b.input_messages,
                        execution_steps=row_b.execution_steps,
                        assertions=row_b.assertions,
                        report_a_outputs=row_a.candidate_outputs,
                        report_b_outputs=row_b.candidate_outputs,
                        evidence=("测试条件不兼容，未执行自动优劣判断",),
                    )
                )
        return LabEvaluationComparison(
            comparison_id=comparison_id,
            batch_id=batch_id,
            report_a_id=report_a.run_id,
            report_b_id=report_b.run_id,
            report_a_sha256=hash_a,
            report_b_sha256=hash_b,
            grade=grade,
            scoring_version=SCORING_VERSION,
            report_a_score=report_a.overall_score,
            report_b_score=report_b.overall_score,
            report_a_coverage=report_a.score_coverage,
            report_b_coverage=report_b.score_coverage,
            report_a_validity=report_a.validity,
            report_b_validity=report_b.validity,
            overall_delta=(
                round(report_b.overall_score - report_a.overall_score, 1)
                if report_a.overall_score is not None
                and report_b.overall_score is not None
                else None
            ),
            report_a_grade=report_a.grade,
            report_b_grade=report_b.grade,
            comparison_variable=variable,
            differing_fields=differing,
            compatibility_reasons=tuple(compatibility_reasons),
            verdict=verdict,
            created_at=_utc_now(),
            dimensions=dimensions,
            scenarios=tuple(scenarios),
            p0_report_a=report_a.p0_violations,
            p0_report_b=report_b.p0_violations,
            warnings=tuple(warnings),
        )

    def _all_reports(self) -> Tuple[LabEvaluationRun, ...]:
        reports = []
        for path in self.root.glob("*/evaluation_*.json"):
            try:
                reports.append(
                    LabEvaluationRun.model_validate_json(
                        path.read_text(encoding="utf-8")
                    )
                )
            except (OSError, ValueError):
                continue
        return tuple(reports)

    def _batch_payload(
        self,
        batch: LabEvaluationBatch,
        reports: Sequence[LabEvaluationRun],
    ) -> dict[str, object]:
        return {
            "batch": batch.model_dump(mode="json"),
            "reports": [item.public_payload() for item in reports],
        }

    def _refresh_batch(
        self,
        batch: LabEvaluationBatch,
        reports: Sequence[LabEvaluationRun],
    ) -> LabEvaluationBatch:
        status = _batch_status_for_runs(reports)
        if (
            batch.kind is LabEvaluationBatchKind.PAIRED
            and status is LabEvaluationBatchStatus.COMPLETED
            and batch.comparison_artifact_id is None
            and batch.status
            in {
                LabEvaluationBatchStatus.PENDING,
                LabEvaluationBatchStatus.RUNNING,
            }
        ):
            status = LabEvaluationBatchStatus.RUNNING
        terminal = status in {
            LabEvaluationBatchStatus.COMPLETED,
            LabEvaluationBatchStatus.PARTIAL_FAILED,
            LabEvaluationBatchStatus.FAILED,
        }
        if batch.status is status and terminal == (batch.completed_at is not None):
            return batch
        updated = batch.model_copy(
            update={
                "status": status,
                "completed_at": _utc_now() if terminal else None,
            }
        )
        if not batch.batch_id.startswith("legacy-"):
            self._write_batch(updated)
        return updated

    def _mark_batch_running(self, batch_id: str) -> None:
        batch = self.get_batch(batch_id)
        self._write_batch(
            batch.model_copy(
                update={
                    "status": LabEvaluationBatchStatus.RUNNING,
                    "completed_at": None,
                }
            )
        )

    def _recover_batches(self) -> None:
        for path in self._batch_root.glob("*.json"):
            batch = self._read_batch_path(path)
            if batch is None:
                continue
            try:
                reports = tuple(self.get_report(item) for item in batch.report_ids)
            except KeyError:
                continue
            if (
                batch.kind is LabEvaluationBatchKind.PAIRED
                and batch.comparison_artifact_id is None
                and _batch_status_for_runs(reports)
                is LabEvaluationBatchStatus.COMPLETED
            ):
                self._finish_pair_batch(
                    batch.batch_id,
                    batch.report_ids[0],
                    batch.report_ids[1],
                )
                continue
            self._refresh_batch(batch, reports)

    def _snapshot_path(self, snapshot_id: str) -> Path:
        _validate_id(snapshot_id)
        return self._snapshot_root / snapshot_id

    def _batch_path(self, batch_id: str) -> Path:
        _validate_id(batch_id)
        return self._batch_root / f"{batch_id}.json"

    def _comparison_path(self, comparison_id: str) -> Path:
        _validate_id(comparison_id)
        return self._comparison_root / f"{comparison_id}.json"

    def _write_batch(self, batch: LabEvaluationBatch) -> None:
        self._write_json(
            self._batch_path(batch.batch_id), batch.model_dump(mode="json")
        )

    @staticmethod
    def _read_batch_path(path: Path) -> Optional[LabEvaluationBatch]:
        try:
            return LabEvaluationBatch.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            return None


def _finish_absolute(
    run: LabEvaluationRun,
    scenarios: Sequence[BuiltinEvaluationScenario],
) -> LabEvaluationRun:
    if not run.episodes:
        return run.model_copy(
            update={
                "status": LabEvaluationStatus.FAILED,
                "verdict": LabEvaluationVerdict.INCOMPLETE,
                "completed_at": _utc_now(),
                "error": "所有场景均未生成证据",
            }
        )
    dimensions = _summarize_absolute_dimensions(run.scenarios, scenarios)
    scenario_statuses = {row.status for row in run.scenarios}
    if run.p0_violations or LabEvaluationResultStatus.FAILED in scenario_statuses:
        verdict = LabEvaluationVerdict.FAILED
    elif LabEvaluationResultStatus.INCOMPLETE in scenario_statuses:
        verdict = LabEvaluationVerdict.INCOMPLETE
    elif LabEvaluationResultStatus.EVIDENCE_READY in scenario_statuses:
        verdict = LabEvaluationVerdict.EVIDENCE_READY
    else:
        verdict = LabEvaluationVerdict.PASSED
    overall_score, score_coverage, score_grade = _score_dimensions(
        tuple(dimensions),
        p0_violations=run.p0_violations,
    )
    return run.model_copy(
        update={
            "status": LabEvaluationStatus.COMPLETED,
            "verdict": verdict,
            "completed_at": _utc_now(),
            "dimensions": tuple(dimensions),
            "scoring_version": SCORING_VERSION,
            "overall_score": overall_score,
            "grade": score_grade,
            "score_coverage": score_coverage,
            "p0_passed": not run.p0_violations,
            "validity": _run_validity(run.scenarios, run.p0_violations),
            "baseline_source": "absolute-report",
        }
    )


def _batch_status_for_runs(
    runs: Sequence[LabEvaluationRun],
) -> LabEvaluationBatchStatus:
    statuses = {item.status for item in runs}
    if statuses & {LabEvaluationStatus.PENDING, LabEvaluationStatus.RUNNING}:
        return (
            LabEvaluationBatchStatus.RUNNING
            if LabEvaluationStatus.RUNNING in statuses
            else LabEvaluationBatchStatus.PENDING
        )
    failures = sum(item.status is LabEvaluationStatus.FAILED for item in runs)
    if failures == len(runs):
        return LabEvaluationBatchStatus.FAILED
    if failures:
        return LabEvaluationBatchStatus.PARTIAL_FAILED
    return LabEvaluationBatchStatus.COMPLETED


def _candidate_differences(
    report_a: LabEvaluationRun,
    report_b: LabEvaluationRun,
) -> Tuple[str, ...]:
    result = []
    if report_a.source_snapshot_sha256 != report_b.source_snapshot_sha256:
        result.append("code")
    if report_a.food_spec_sha256 != report_b.food_spec_sha256:
        result.append("food")
    return tuple(result)


def _test_plan_hash(
    suite: LabEvaluationSuite,
    scenarios: Sequence[BuiltinEvaluationScenario],
) -> str:
    return _sha256_json(
        {
            "suite": suite.value,
            "execution_rules": _EXECUTION_RULES,
            "scenarios": [
                {
                    "title": item.title,
                    "purpose": item.purpose,
                    "dimension": item.dimension.value if item.dimension else None,
                    "definition": item.definition.model_dump(mode="json"),
                }
                for item in scenarios
            ],
        }
    )


def _report_hash(run: LabEvaluationRun) -> str:
    return _sha256_json(run.model_dump(mode="json"))


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("评测快照时间必须包含 UTC 时区")
    return parsed


__all__ = ("BatchEvaluationService",)
