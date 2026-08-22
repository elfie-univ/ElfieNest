"""Human-anchor calibration for any model judge used in promotion."""

from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256
from statistics import fmean
from typing import Iterable

from devtools.brain_eval.contracts import (
    HumanAnchor,
    JudgeCalibrationReport,
    JudgePreference,
    JudgeVote,
    QualityDimension,
)
from devtools.brain_eval.judge import consolidate_position_flips

_VALUE = {
    JudgePreference.CANDIDATE: 1,
    JudgePreference.TIE: 0,
    JudgePreference.BASELINE: -1,
}


def calibrate_judge(
    votes: Iterable[JudgeVote],
    anchors: Iterable[HumanAnchor],
    *,
    protocol_version: str,
    anchor_set_revision: str,
    calibrated_at: datetime,
    tolerance: float,
    minimum_position_consistency: float,
) -> JudgeCalibrationReport:
    """Require judge-human agreement near the human-human agreement ceiling."""

    selected_votes = tuple(votes)
    selected_anchors = tuple(anchors)
    judge_identities = {(vote.judge_id, vote.judge_revision) for vote in selected_votes}
    if len(judge_identities) != 1:
        raise ValueError("calibration requires one judge_id and judge_revision")
    anchor_keys = {(anchor.pair_id, anchor.dimension) for anchor in selected_anchors}
    if len(anchor_keys) != len(selected_anchors):
        raise ValueError("calibration anchors must have unique pair/dimension keys")
    if not 0.0 <= tolerance <= 1.0:
        raise ValueError("tolerance must be between zero and one")
    if not 0.0 <= minimum_position_consistency <= 1.0:
        raise ValueError("minimum_position_consistency must be between zero and one")
    outcomes = consolidate_position_flips(selected_votes)
    outcome_by_key = {
        (outcome.pair_id, outcome.dimension): outcome for outcome in outcomes
    }
    matches = []
    matched_count = 0
    for anchor in selected_anchors:
        outcome = outcome_by_key.get((anchor.pair_id, anchor.dimension))
        if (
            outcome is None
            or outcome.pair_evidence_sha256 != anchor.pair_evidence_sha256
            or not outcome.valid
            or outcome.value is None
        ):
            continue
        matched_count += 1
        matches.append(outcome.value == _VALUE[anchor.preference])
    anchor_count = len(selected_anchors)
    coverage = matched_count / anchor_count if anchor_count else 0.0
    judge_human = float(fmean(matches)) if matches else 0.0
    human_human = (
        float(fmean(anchor.human_agreement for anchor in selected_anchors))
        if selected_anchors
        else 0.0
    )
    position_consistency = (
        sum(outcome.valid for outcome in outcomes) / len(outcomes) if outcomes else 0.0
    )
    passed = (
        anchor_count > 0
        and coverage == 1.0
        and judge_human >= human_human - tolerance
        and position_consistency >= minimum_position_consistency
    )
    judge_id, judge_revision = judge_identities.pop()
    rubric_versions = tuple(sorted({vote.rubric_version for vote in selected_votes}))
    anchor_digest = _anchor_digest(selected_anchors)
    calibration_id = sha256(
        "|".join(
            (
                protocol_version,
                judge_id,
                judge_revision,
                ",".join(rubric_versions),
                anchor_set_revision,
                anchor_digest,
            )
        ).encode("utf-8")
    ).hexdigest()[:32]
    return JudgeCalibrationReport(
        calibration_id=calibration_id,
        protocol_version=protocol_version,
        judge_id=judge_id,
        judge_revision=judge_revision,
        rubric_versions=rubric_versions,
        anchor_set_revision=anchor_set_revision,
        anchor_set_sha256=anchor_digest,
        calibrated_at=calibrated_at,
        dimensions_covered=tuple(
            dimension
            for dimension in QualityDimension
            if dimension in {anchor.dimension for anchor in selected_anchors}
        ),
        passed=passed,
        judge_human_agreement=judge_human,
        human_human_agreement=human_human,
        position_flip_consistency=position_consistency,
        anchor_coverage=coverage,
        anchor_count=anchor_count,
        matched_anchor_count=matched_count,
        tolerance=tolerance,
        minimum_position_consistency=minimum_position_consistency,
    )


def _anchor_digest(anchors: tuple[HumanAnchor, ...]) -> str:
    payload = [
        anchor.model_dump(mode="json")
        for anchor in sorted(
            anchors,
            key=lambda item: (item.pair_id, item.dimension.value),
        )
    ]
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


__all__ = ("calibrate_judge",)
