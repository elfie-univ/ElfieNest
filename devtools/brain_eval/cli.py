"""Unified ``developer.sh brain-eval`` command."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Type, TypeVar, cast

from pydantic import BaseModel

from devtools.brain_eval.artifacts import BrainEvalArtifactStore, load_jsonl
from devtools.brain_eval.calibration import calibrate_judge
from devtools.brain_eval.catalog import scenario_catalog
from devtools.brain_eval.contracts import (
    CandidateSpec,
    DecisionStatus,
    EpisodeEvidence,
    EvaluationConfirmation,
    HumanAnchor,
    JudgeCalibrationReport,
    JudgeEvidencePacket,
    JudgeVote,
    PromotionPolicy,
    contract_sha256,
)
from devtools.brain_eval.evaluation import build_comparison_report
from devtools.brain_eval.gates import evaluate_p0_gates
from devtools.brain_eval.judge import validate_judge_votes_against_packets
from devtools.brain_eval.lab_runner import (
    LabFixtureDefinition,
    LabScenarioDefinition,
    capture_lab_episode,
)

_Model = TypeVar("_Model", bound=BaseModel)


def configure_parser(parser: argparse.ArgumentParser) -> None:
    """Attach versioned Brain evaluation actions to the unified CLI."""

    actions = parser.add_subparsers(dest="brain_eval_action", required=True)
    catalog_parser = actions.add_parser(
        "catalog",
        help="List the frozen v0.1 scenario-family catalog",
    )
    catalog_parser.add_argument("--json", action="store_true", dest="as_json")

    capture = actions.add_parser(
        "capture",
        help="Capture one current-checkout episode through real Elfie Lab Brain wiring",
    )
    capture.add_argument("--candidate", required=True, type=Path)
    capture.add_argument("--fixture", required=True, type=Path)
    capture.add_argument("--scenario", required=True, type=Path)
    capture.add_argument("--food-key", default="mock")
    capture.add_argument("--run-id", required=True)
    capture.add_argument("--output-root", type=Path, default=None)

    compare = actions.add_parser(
        "compare",
        help="Compare paired baseline/candidate artifacts under a frozen policy",
    )
    compare.add_argument("--baseline-candidate", required=True, type=Path)
    compare.add_argument("--candidate", required=True, type=Path)
    compare.add_argument("--baseline-episodes", required=True, type=Path)
    compare.add_argument("--candidate-episodes", required=True, type=Path)
    compare.add_argument("--judge-packets", required=True, type=Path)
    compare.add_argument("--judge-votes", required=True, type=Path)
    compare.add_argument("--judge-calibration", type=Path, default=None)
    compare.add_argument("--policy", required=True, type=Path)
    compare.add_argument("--holdout-confirmation", type=Path, default=None)
    compare.add_argument(
        "--constitutional-anchor-confirmation",
        type=Path,
        default=None,
    )
    compare.add_argument("--run-id", required=True)
    compare.add_argument("--output-root", type=Path, default=None)
    compare.add_argument("--bootstrap-samples", type=int, default=2000)
    compare.add_argument("--random-seed", type=int, default=0)

    calibrate = actions.add_parser(
        "calibrate",
        help="Calibrate a judge against versioned human pairwise anchors",
    )
    calibrate.add_argument("--judge-votes", required=True, type=Path)
    calibrate.add_argument("--judge-packets", required=True, type=Path)
    calibrate.add_argument("--human-anchors", required=True, type=Path)
    calibrate.add_argument("--protocol-version", required=True)
    calibrate.add_argument("--anchor-set-revision", required=True)
    calibrate.add_argument("--tolerance", required=True, type=float)
    calibrate.add_argument(
        "--minimum-position-consistency",
        required=True,
        type=float,
    )
    calibrate.add_argument("--run-id", required=True)
    calibrate.add_argument("--output-root", type=Path, default=None)


def run(args: argparse.Namespace) -> int:
    action = args.brain_eval_action
    if action == "catalog":
        return _catalog(args)
    if action == "capture":
        return _capture(args)
    if action == "compare":
        return _compare(args)
    if action == "calibrate":
        return _calibrate(args)
    raise ValueError(f"unknown brain-eval action: {action}")


def _catalog(args: argparse.Namespace) -> int:
    catalog = scenario_catalog()
    if args.as_json:
        print(
            json.dumps(
                [item.model_dump(mode="json") for item in catalog],
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for item in catalog:
            print(f"{item.suite.value:10} {item.family_id:36} {item.title}")
    return 0


def _capture(args: argparse.Namespace) -> int:
    project_root = _project_root()
    candidate = _load_model(args.candidate, CandidateSpec)
    checkout_sha = _verify_checkout(project_root, candidate)
    fixture = _load_model(args.fixture, LabFixtureDefinition)
    scenario = _load_model(args.scenario, LabScenarioDefinition)
    with tempfile.TemporaryDirectory(prefix="elfienest-brain-eval-") as temporary:
        episode = capture_lab_episode(
            candidate_id=candidate.candidate_id,
            candidate_spec_sha256=contract_sha256(candidate),
            fixture=fixture,
            scenario=scenario,
            food_key=args.food_key,
            runtime_root=Path(temporary),
        )
    _verify_episode_candidate((episode,), candidate)
    violations = evaluate_p0_gates((episode,))
    store = BrainEvalArtifactStore(
        project_root,
        args.run_id,
        output_root=args.output_root,
    )
    store.write_json(
        "manifest.json",
        {
            "run_id": args.run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "protocol_version": "0.1.0",
            "checkout_sha": checkout_sha,
            "source_clean": True,
            "food_key": args.food_key,
            "candidate": candidate.model_dump(mode="json"),
            "fixture": fixture.model_dump(mode="json"),
            "scenario": scenario.model_dump(mode="json"),
        },
    )
    store.write_jsonl("episodes.jsonl", (episode,))
    store.write_jsonl("p0-gates.jsonl", violations)
    print(f"captured={store.run_dir} p0_violations={len(violations)}")
    return 1 if violations else 0


def _compare(args: argparse.Namespace) -> int:
    baseline_spec = _load_model(args.baseline_candidate, CandidateSpec)
    candidate_spec = _load_model(args.candidate, CandidateSpec)
    policy = _load_model(args.policy, PromotionPolicy)
    baseline_episodes = cast(
        tuple[EpisodeEvidence, ...],
        load_jsonl(args.baseline_episodes, EpisodeEvidence),
    )
    candidate_episodes = cast(
        tuple[EpisodeEvidence, ...],
        load_jsonl(args.candidate_episodes, EpisodeEvidence),
    )
    votes = cast(
        tuple[JudgeVote, ...],
        load_jsonl(args.judge_votes, JudgeVote),
    )
    packets = cast(
        tuple[JudgeEvidencePacket, ...],
        load_jsonl(args.judge_packets, JudgeEvidencePacket),
    )
    validate_judge_votes_against_packets(votes, packets)
    judge_calibration = (
        _load_model(args.judge_calibration, JudgeCalibrationReport)
        if args.judge_calibration is not None
        else None
    )
    holdout_confirmation = (
        _load_model(args.holdout_confirmation, EvaluationConfirmation)
        if args.holdout_confirmation is not None
        else None
    )
    constitutional_anchor_confirmation = (
        _load_model(
            args.constitutional_anchor_confirmation,
            EvaluationConfirmation,
        )
        if args.constitutional_anchor_confirmation is not None
        else None
    )
    _verify_episode_candidate(baseline_episodes, baseline_spec)
    _verify_episode_candidate(candidate_episodes, candidate_spec)
    report = build_comparison_report(
        policy=policy,
        baseline_episodes=baseline_episodes,
        candidate_episodes=candidate_episodes,
        judge_votes=votes,
        judge_calibration=judge_calibration,
        holdout_confirmation=holdout_confirmation,
        constitutional_anchor_confirmation=constitutional_anchor_confirmation,
        bootstrap_samples=args.bootstrap_samples,
        random_seed=args.random_seed,
    )
    store = BrainEvalArtifactStore(
        _project_root(),
        args.run_id,
        output_root=args.output_root,
    )
    store.write_json(
        "manifest.json",
        {
            "run_id": args.run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "protocol_version": policy.protocol_version,
            "baseline": baseline_spec.model_dump(mode="json"),
            "candidate": candidate_spec.model_dump(mode="json"),
        },
    )
    store.write_json("comparison.json", report)
    store.write_json("decision.json", report.decision)
    store.write_json("policy.json", policy)
    store.write_jsonl("baseline-episodes.jsonl", baseline_episodes)
    store.write_jsonl("candidate-episodes.jsonl", candidate_episodes)
    store.write_jsonl("judge-packets.jsonl", packets)
    store.write_jsonl("judge-votes.jsonl", votes)
    print(
        f"decision={report.decision.status.value} "
        f"epi={report.decision.epi} artifacts={store.run_dir}"
    )
    if report.decision.status is DecisionStatus.PROMOTE:
        return 0
    if report.decision.status is DecisionStatus.INVALID:
        return 2
    return 1


def _calibrate(args: argparse.Namespace) -> int:
    votes = cast(
        tuple[JudgeVote, ...],
        load_jsonl(args.judge_votes, JudgeVote),
    )
    packets = cast(
        tuple[JudgeEvidencePacket, ...],
        load_jsonl(args.judge_packets, JudgeEvidencePacket),
    )
    validate_judge_votes_against_packets(votes, packets)
    anchors = cast(
        tuple[HumanAnchor, ...],
        load_jsonl(args.human_anchors, HumanAnchor),
    )
    report = calibrate_judge(
        votes,
        anchors,
        protocol_version=args.protocol_version,
        anchor_set_revision=args.anchor_set_revision,
        calibrated_at=datetime.now(timezone.utc),
        tolerance=args.tolerance,
        minimum_position_consistency=args.minimum_position_consistency,
    )
    store = BrainEvalArtifactStore(
        _project_root(),
        args.run_id,
        output_root=args.output_root,
    )
    store.write_json("judge-calibration.json", report)
    store.write_jsonl("judge-packets.jsonl", packets)
    store.write_jsonl("judge-votes.jsonl", votes)
    store.write_jsonl("human-anchors.jsonl", anchors)
    print(
        f"judge_calibration={'pass' if report.passed else 'fail'} "
        f"artifacts={store.run_dir}"
    )
    return 0 if report.passed else 1


def _load_model(path: Path, model: Type[_Model]) -> _Model:
    try:
        return model.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"invalid {model.__name__} file {path}: {error}") from error


def _verify_episode_candidate(
    episodes: tuple[EpisodeEvidence, ...],
    candidate: CandidateSpec,
) -> None:
    if not episodes or {episode.candidate_id for episode in episodes} != {
        candidate.candidate_id
    }:
        raise ValueError(
            f"episode candidate_id does not match CandidateSpec {candidate.candidate_id}"
        )
    candidate_digest = contract_sha256(candidate)
    episode_digests = {episode.candidate_spec_sha256 for episode in episodes}
    if episode_digests != {candidate_digest}:
        raise ValueError(
            "episode CandidateSpec digest does not match input: "
            f"expected={candidate_digest}, actual={episode_digests}"
        )
    executions = tuple(
        execution
        for episode in episodes
        for execution in episode.model_executions
        if not execution.skipped
    )
    if not executions:
        raise ValueError(
            f"episodes for {candidate.candidate_id} contain no executed model identity"
        )
    identities = {(execution.provider, execution.model_id) for execution in executions}
    expected = {(candidate.model_provider, candidate.model_id)}
    if identities != expected:
        raise ValueError(
            "episode model identity does not match CandidateSpec: "
            f"expected={expected}, actual={identities}"
        )


def _verify_checkout(project_root: Path, candidate: CandidateSpec) -> str:
    try:
        checkout_sha = subprocess.run(
            ("git", "rev-parse", "HEAD"),
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ("git", "status", "--porcelain", "--untracked-files=all"),
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError(f"cannot verify evaluation checkout: {error}") from error
    if not checkout_sha.startswith(candidate.code_sha):
        raise ValueError(
            "CandidateSpec code_sha does not match checkout: "
            f"candidate={candidate.code_sha}, checkout={checkout_sha}"
        )
    if status:
        raise ValueError(
            "formal Brain capture requires a clean checkout; commit or remove local changes"
        )
    return checkout_sha


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


__all__ = ("configure_parser", "run")
