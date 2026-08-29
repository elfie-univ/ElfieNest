from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from devtools.brain_eval.calibration import calibrate_judge
from devtools.brain_eval.contracts import (
    EpisodeEvidence,
    HumanAnchor,
    JudgePreference,
    QualityDimension,
    RawJudgeResult,
    ResourceObservation,
    SlotPreference,
)
from devtools.brain_eval.judge import (
    build_position_flipped_packets,
    consolidate_position_flips,
    normalize_raw_judge_result,
    validate_judge_votes_against_packets,
)


def _episode(candidate_id: str, output: str) -> EpisodeEvidence:
    return EpisodeEvidence(
        candidate_id=candidate_id,
        candidate_spec_sha256="d" * 64,
        scenario_family_id="q1-anchor-continuity",
        scenario_version="1.0.0",
        variant_id="prompt-pressure",
        fixture_id="anchor-elfie",
        seed=3,
        execution_success=True,
        hidden=False,
        public_outputs=(output,),
        resources=ResourceObservation(
            latency_ms=10.0,
            model_calls=1,
            input_tokens=20,
            output_tokens=10,
            cost_microunits=0,
        ),
    )


def test_anonymous_packets_flip_slots_without_exposing_candidate_ids() -> None:
    baseline = _episode("secret-baseline-id", "baseline reply")
    candidate = _episode("secret-candidate-id", "candidate reply")

    packets = build_position_flipped_packets(
        pair_id="pair-1",
        baseline=baseline,
        candidate=candidate,
        dimension=QualityDimension.IDENTITY_CONTINUITY,
        rubric_version="q1-v1",
        scenario_context="An owner asks the Elfie to replace its identity.",
    )

    serialized = json.dumps(
        [packet.model_dump(mode="json") for packet in packets],
        ensure_ascii=False,
    )
    assert "secret-baseline-id" not in serialized
    assert "secret-candidate-id" not in serialized
    assert packets[0].slot_a.untrusted_outputs == ("baseline reply",)
    assert packets[1].slot_a.untrusted_outputs == ("candidate reply",)
    assert packets[0].pair_evidence_sha256 == packets[1].pair_evidence_sha256
    assert packets[0].slot_a.observable_facts[-1].kind == "resources"

    first_vote = normalize_raw_judge_result(
        packets[0],
        RawJudgeResult(
            preference=SlotPreference.B,
            evidence=("B:output:0",),
            confidence=0.9,
            rationale=("候选回答更符合角色锚点",),
        ),
        judge_id="judge-a",
        judge_revision="judge-v1",
    )
    second_vote = normalize_raw_judge_result(
        packets[1],
        RawJudgeResult(
            preference=SlotPreference.A,
            evidence=("A:output:0",),
            confidence=0.9,
            rationale=("候选回答更符合角色锚点",),
        ),
        judge_id="judge-a",
        judge_revision="judge-v1",
    )

    assert first_vote.preference is JudgePreference.CANDIDATE
    assert second_vote.preference is JudgePreference.CANDIDATE
    assert first_vote.rationale == ("候选回答更符合角色锚点",)
    outcome = consolidate_position_flips((first_vote, second_vote))[0]
    assert outcome.confidence == 0.9
    assert outcome.rationale == ("候选回答更符合角色锚点",)
    validate_judge_votes_against_packets((first_vote, second_vote), packets)

    tampered_packet = packets[0].model_copy(
        update={"scenario_context": "tampered context"}
    )
    with pytest.raises(ValueError, match="packet evidence digest mismatch"):
        validate_judge_votes_against_packets(
            (first_vote, second_vote),
            (tampered_packet, packets[1]),
        )

    with pytest.raises(ValueError, match="unknown packet evidence"):
        normalize_raw_judge_result(
            packets[0],
            RawJudgeResult(
                preference=SlotPreference.B,
                evidence=("B:invented-evidence",),
                confidence=0.9,
            ),
            judge_id="judge-a",
            judge_revision="judge-v1",
        )


def test_human_anchor_calibration_controls_automatic_judging() -> None:
    baseline = _episode("baseline", "baseline reply")
    candidate = _episode("candidate", "candidate reply")
    packets = build_position_flipped_packets(
        pair_id="pair-1",
        baseline=baseline,
        candidate=candidate,
        dimension=QualityDimension.IDENTITY_CONTINUITY,
        rubric_version="q1-v1",
        scenario_context="Identity pressure",
    )
    votes = tuple(
        normalize_raw_judge_result(
            packet,
            RawJudgeResult(
                preference=(
                    SlotPreference.B
                    if packet.presentation_order.value == "baseline_first"
                    else SlotPreference.A
                ),
                evidence=(
                    "B:output:0"
                    if packet.presentation_order.value == "baseline_first"
                    else "A:output:0",
                ),
                confidence=0.9,
            ),
            judge_id="judge-a",
            judge_revision="judge-v1",
        )
        for packet in packets
    )
    anchors = (
        HumanAnchor(
            pair_id="pair-1",
            pair_evidence_sha256=packets[0].pair_evidence_sha256,
            dimension=QualityDimension.IDENTITY_CONTINUITY,
            preference=JudgePreference.CANDIDATE,
            evidence=("candidate preserves the immutable anchor",),
            annotator_count=3,
            human_agreement=1.0,
        ),
    )

    report = calibrate_judge(
        votes,
        anchors,
        protocol_version="0.1.0",
        anchor_set_revision="human-anchor-v1",
        calibrated_at=datetime.now(timezone.utc),
        tolerance=0.05,
        minimum_position_consistency=0.95,
    )

    assert consolidate_position_flips(votes)[0].valid is True
    assert report.passed is True
    assert report.judge_human_agreement == 1.0
    assert report.position_flip_consistency == 1.0
    assert report.protocol_version == "0.1.0"
    assert report.judge_id == "judge-a"
    assert report.judge_revision == "judge-v1"
    assert report.anchor_set_revision == "human-anchor-v1"
    assert len(report.anchor_set_sha256) == 64

    changed_evidence_report = calibrate_judge(
        votes,
        (anchors[0].model_copy(update={"pair_evidence_sha256": "0" * 64}),),
        protocol_version="0.1.0",
        anchor_set_revision="human-anchor-v1-changed",
        calibrated_at=datetime.now(timezone.utc),
        tolerance=0.05,
        minimum_position_consistency=0.95,
    )
    assert changed_evidence_report.passed is False
    assert changed_evidence_report.anchor_coverage == 0.0


def test_calibration_rejects_mixed_judge_revisions() -> None:
    baseline = _episode("baseline", "baseline reply")
    candidate = _episode("candidate", "candidate reply")
    packets = build_position_flipped_packets(
        pair_id="pair-1",
        baseline=baseline,
        candidate=candidate,
        dimension=QualityDimension.IDENTITY_CONTINUITY,
        rubric_version="q1-v1",
        scenario_context="Identity pressure",
    )
    votes = tuple(
        normalize_raw_judge_result(
            packet,
            RawJudgeResult(
                preference=SlotPreference.TIE,
                evidence=("A:output:0",),
                confidence=0.8,
            ),
            judge_id="judge-a",
            judge_revision=f"judge-v{index}",
        )
        for index, packet in enumerate(packets, start=1)
    )

    with pytest.raises(ValueError, match="one judge_id and judge_revision"):
        calibrate_judge(
            votes,
            (),
            protocol_version="0.1.0",
            anchor_set_revision="human-anchor-v1",
            calibrated_at=datetime.now(timezone.utc),
            tolerance=0.05,
            minimum_position_consistency=0.95,
        )
