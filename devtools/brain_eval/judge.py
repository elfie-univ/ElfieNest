"""Position-flipped anonymous judge consolidation."""

from __future__ import annotations

import json
from collections import defaultdict
from hashlib import sha256
from typing import DefaultDict, Iterable, List, Literal, Tuple

from devtools.brain_eval.contracts import (
    EpisodeEvidence,
    EvalContract,
    JudgeEvidencePacket,
    JudgeEvidenceSlot,
    JudgeObservableFact,
    JudgePreference,
    JudgeVote,
    PairwiseOutcome,
    PresentationOrder,
    QualityDimension,
    RawJudgeResult,
    SlotPreference,
)

_VALUE = {
    JudgePreference.CANDIDATE: 1,
    JudgePreference.TIE: 0,
    JudgePreference.BASELINE: -1,
}


def build_position_flipped_packets(
    *,
    pair_id: str,
    baseline: EpisodeEvidence,
    candidate: EpisodeEvidence,
    dimension: QualityDimension,
    rubric_version: str,
    scenario_context: str,
) -> tuple[JudgeEvidencePacket, JudgeEvidencePacket]:
    """Build two ID-free packets with candidate outputs treated as inert data."""

    if baseline.pair_key != candidate.pair_key:
        raise ValueError("anonymous judge packets require paired episode keys")
    if (
        baseline.scenario_version != candidate.scenario_version
        or baseline.hidden != candidate.hidden
    ):
        raise ValueError("anonymous judge packets require matching scenario protocol")
    baseline_slot = _slot("A", baseline)
    candidate_slot = _slot("B", candidate)
    pair_evidence_sha256 = _pair_evidence_sha256(
        baseline_slot=baseline_slot,
        candidate_slot=candidate_slot,
        scenario_family_id=baseline.scenario_family_id,
        scenario_version=baseline.scenario_version,
        variant_id=baseline.variant_id,
        fixture_id=baseline.fixture_id,
        seed=baseline.seed,
        dimension=dimension,
        rubric_version=rubric_version,
        scenario_context=scenario_context,
    )
    first = JudgeEvidencePacket(
        packet_id=f"{pair_id}:baseline-first",
        pair_id=pair_id,
        pair_evidence_sha256=pair_evidence_sha256,
        scenario_family_id=baseline.scenario_family_id,
        scenario_version=baseline.scenario_version,
        variant_id=baseline.variant_id,
        fixture_id=baseline.fixture_id,
        seed=baseline.seed,
        dimension=dimension,
        rubric_version=rubric_version,
        presentation_order=PresentationOrder.BASELINE_FIRST,
        scenario_context=scenario_context,
        slot_a=baseline_slot,
        slot_b=candidate_slot,
    )
    second = JudgeEvidencePacket(
        packet_id=f"{pair_id}:candidate-first",
        pair_id=pair_id,
        pair_evidence_sha256=pair_evidence_sha256,
        scenario_family_id=baseline.scenario_family_id,
        scenario_version=baseline.scenario_version,
        variant_id=baseline.variant_id,
        fixture_id=baseline.fixture_id,
        seed=baseline.seed,
        dimension=dimension,
        rubric_version=rubric_version,
        presentation_order=PresentationOrder.CANDIDATE_FIRST,
        scenario_context=scenario_context,
        slot_a=_slot("A", candidate),
        slot_b=_slot("B", baseline),
    )
    return first, second


def normalize_raw_judge_result(
    packet: JudgeEvidencePacket,
    result: RawJudgeResult,
    *,
    judge_id: str,
    judge_revision: str,
) -> JudgeVote:
    """Normalize an A/B answer into baseline/candidate semantics."""

    _validate_packet_digest(packet)
    known_evidence = set(packet.slot_a.evidence_refs) | set(packet.slot_b.evidence_refs)
    unknown_evidence = set(result.evidence) - known_evidence
    if unknown_evidence:
        raise ValueError(
            f"judge cited unknown packet evidence: {sorted(unknown_evidence)}"
        )
    preference = _normalize_slot_preference(
        result.preference,
        packet.presentation_order,
    )
    return JudgeVote(
        pair_id=packet.pair_id,
        pair_evidence_sha256=packet.pair_evidence_sha256,
        scenario_family_id=packet.scenario_family_id,
        scenario_version=packet.scenario_version,
        variant_id=packet.variant_id,
        fixture_id=packet.fixture_id,
        seed=packet.seed,
        dimension=packet.dimension,
        judge_id=judge_id,
        judge_revision=judge_revision,
        rubric_version=packet.rubric_version,
        presentation_order=packet.presentation_order,
        preference=preference,
        evidence=result.evidence,
        confidence=result.confidence,
    )


def consolidate_position_flips(
    votes: Iterable[JudgeVote],
) -> tuple[PairwiseOutcome, ...]:
    """Require both A/B orders and agreement across independent judges."""

    per_judge: DefaultDict[Tuple[str, QualityDimension, str], List[JudgeVote]] = (
        defaultdict(list)
    )
    for vote in votes:
        per_judge[(vote.pair_id, vote.dimension, vote.judge_id)].append(vote)

    judged: DefaultDict[
        Tuple[str, QualityDimension], List[tuple[JudgeVote, int | None, str | None]]
    ] = defaultdict(list)
    for (pair_id, dimension, _judge_id), group in sorted(
        per_judge.items(), key=lambda item: tuple(str(part) for part in item[0])
    ):
        first = group[0]
        if len({_position_metadata(vote) for vote in group}) != 1:
            judged[(pair_id, dimension)].append(
                (first, None, "position_flip_metadata_mismatch")
            )
            continue
        orders = {vote.presentation_order for vote in group}
        if len(group) != 2 or orders != set(PresentationOrder):
            judged[(pair_id, dimension)].append(
                (first, None, "position_flip_incomplete")
            )
            continue
        if any(vote.preference is JudgePreference.INVALID for vote in group):
            judged[(pair_id, dimension)].append((first, None, "judge_invalid"))
            continue
        values = {_VALUE[vote.preference] for vote in group}
        if len(values) != 1:
            judged[(pair_id, dimension)].append(
                (first, None, "position_flip_disagreement")
            )
            continue
        judged[(pair_id, dimension)].append((first, values.pop(), None))

    outcomes: List[PairwiseOutcome] = []
    for (_pair_id, dimension), results in sorted(
        judged.items(), key=lambda item: (item[0][0], item[0][1].value)
    ):
        first = results[0][0]
        if len({_pair_metadata(vote) for vote, _, _ in results}) != 1:
            outcomes.append(
                _outcome(
                    first,
                    dimension,
                    None,
                    "judge_pair_metadata_mismatch",
                    results,
                )
            )
            continue
        invalid_reasons = [reason for _, _, reason in results if reason is not None]
        values = {value for _, value, _ in results if value is not None}
        if invalid_reasons:
            outcomes.append(
                _outcome(first, dimension, None, invalid_reasons[0], results)
            )
        elif len(values) != 1:
            outcomes.append(
                _outcome(first, dimension, None, "judge_disagreement", results)
            )
        else:
            outcomes.append(_outcome(first, dimension, values.pop(), None, results))
    return tuple(outcomes)


def validate_judge_votes_against_packets(
    votes: Iterable[JudgeVote],
    packets: Iterable[JudgeEvidencePacket],
) -> None:
    """Rebind persisted votes to complete, untampered dual-order packets."""

    selected_votes = tuple(votes)
    selected_packets = tuple(packets)
    packet_by_key: dict[
        tuple[str, QualityDimension, PresentationOrder], JudgeEvidencePacket
    ] = {}
    packet_ids = set()
    per_pair: DefaultDict[tuple[str, QualityDimension], List[JudgeEvidencePacket]] = (
        defaultdict(list)
    )
    for packet in selected_packets:
        _validate_packet_digest(packet)
        if packet.packet_id in packet_ids:
            raise ValueError(f"duplicate judge packet_id: {packet.packet_id}")
        packet_ids.add(packet.packet_id)
        key = (packet.pair_id, packet.dimension, packet.presentation_order)
        if key in packet_by_key:
            raise ValueError(f"duplicate judge packet key: {key}")
        packet_by_key[key] = packet
        per_pair[(packet.pair_id, packet.dimension)].append(packet)

    for pair_key, group in per_pair.items():
        if len(group) != 2 or {item.presentation_order for item in group} != set(
            PresentationOrder
        ):
            raise ValueError(f"judge packet position flip incomplete: {pair_key}")
        if len({_packet_pair_metadata(item) for item in group}) != 1:
            raise ValueError(f"judge packet position metadata mismatch: {pair_key}")

    vote_keys = {
        (vote.pair_id, vote.dimension, vote.presentation_order)
        for vote in selected_votes
    }
    if vote_keys != set(packet_by_key):
        raise ValueError(
            "judge votes and packets do not cover the same position keys: "
            f"votes={vote_keys}, packets={set(packet_by_key)}"
        )
    for vote in selected_votes:
        key = (vote.pair_id, vote.dimension, vote.presentation_order)
        packet = packet_by_key[key]
        if _vote_packet_metadata(vote) != _packet_vote_metadata(packet):
            raise ValueError(f"judge vote does not match packet metadata: {key}")
        known_evidence = set(packet.slot_a.evidence_refs) | set(
            packet.slot_b.evidence_refs
        )
        unknown_evidence = set(vote.evidence) - known_evidence
        if unknown_evidence:
            raise ValueError(
                "judge vote cites unknown packet evidence: "
                f"key={key}, evidence={sorted(unknown_evidence)}"
            )


def _outcome(
    first: JudgeVote,
    dimension: QualityDimension,
    value: int | None,
    invalid_reason: str | None,
    results: List[tuple[JudgeVote, int | None, str | None]],
) -> PairwiseOutcome:
    evidence = tuple(
        dict.fromkeys(item for vote, _, _ in results for item in vote.evidence)
    )
    return PairwiseOutcome(
        pair_id=first.pair_id,
        pair_evidence_sha256=first.pair_evidence_sha256,
        scenario_family_id=first.scenario_family_id,
        scenario_version=first.scenario_version,
        variant_id=first.variant_id,
        fixture_id=first.fixture_id,
        seed=first.seed,
        dimension=dimension,
        valid=value is not None,
        value=value,
        invalid_reason=invalid_reason,
        evidence=evidence,
    )


def _slot(label: Literal["A", "B"], episode: EpisodeEvidence) -> JudgeEvidenceSlot:
    facts = (
        tuple(_fact(label, "turn", turn.turn_id, turn) for turn in episode.turns)
        + tuple(
            _fact(label, "effect", effect.effect_id, effect)
            for effect in episode.effects
        )
        + tuple(
            _fact(label, "completion_claim", claim.claim_id, claim)
            for claim in episode.completion_claims
        )
        + tuple(
            _fact(label, "identity_change", change.change_id, change)
            for change in episode.identity_changes
        )
        + tuple(
            _fact(label, "disclosure", disclosure.disclosure_id, disclosure)
            for disclosure in episode.disclosures
        )
        + tuple(
            _fact(label, "capability_use", use.use_id, use)
            for use in episode.capability_uses
        )
    )
    facts = (*facts, _fact(label, "resources", "episode", episode.resources))
    output_refs = tuple(
        f"{label}:output:{index}" for index, _ in enumerate(episode.public_outputs)
    )
    return JudgeEvidenceSlot(
        slot=label,
        untrusted_outputs=episode.public_outputs,
        evidence_refs=(*(fact.evidence_ref for fact in facts), *output_refs),
        observable_facts=facts,
    )


def _fact(
    label: str,
    kind: str,
    identity: str,
    value: EvalContract,
) -> JudgeObservableFact:
    payload = value.model_dump(mode="json")
    return JudgeObservableFact(
        evidence_ref=f"{label}:{kind}:{identity}",
        kind=kind,
        value_json=json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
    )


def _pair_evidence_sha256(
    *,
    baseline_slot: JudgeEvidenceSlot,
    candidate_slot: JudgeEvidenceSlot,
    scenario_family_id: str,
    scenario_version: str,
    variant_id: str,
    fixture_id: str,
    seed: int,
    dimension: QualityDimension,
    rubric_version: str,
    scenario_context: str,
) -> str:
    payload = {
        "scenario_family_id": scenario_family_id,
        "scenario_version": scenario_version,
        "variant_id": variant_id,
        "fixture_id": fixture_id,
        "seed": seed,
        "dimension": dimension.value,
        "rubric_version": rubric_version,
        "scenario_context": scenario_context,
        "baseline": _slot_content(baseline_slot),
        "candidate": _slot_content(candidate_slot),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _slot_content(slot: JudgeEvidenceSlot) -> dict[str, object]:
    return {
        "untrusted_outputs": slot.untrusted_outputs,
        "observable_facts": tuple(
            {"kind": fact.kind, "value_json": fact.value_json}
            for fact in slot.observable_facts
        ),
    }


def _validate_packet_digest(packet: JudgeEvidencePacket) -> None:
    baseline_slot = (
        packet.slot_a
        if packet.presentation_order is PresentationOrder.BASELINE_FIRST
        else packet.slot_b
    )
    candidate_slot = (
        packet.slot_b
        if packet.presentation_order is PresentationOrder.BASELINE_FIRST
        else packet.slot_a
    )
    expected = _pair_evidence_sha256(
        baseline_slot=baseline_slot,
        candidate_slot=candidate_slot,
        scenario_family_id=packet.scenario_family_id,
        scenario_version=packet.scenario_version,
        variant_id=packet.variant_id,
        fixture_id=packet.fixture_id,
        seed=packet.seed,
        dimension=packet.dimension,
        rubric_version=packet.rubric_version,
        scenario_context=packet.scenario_context,
    )
    if packet.pair_evidence_sha256 != expected:
        raise ValueError(
            "judge packet evidence digest mismatch: "
            f"packet={packet.packet_id}, expected={expected}, "
            f"actual={packet.pair_evidence_sha256}"
        )


def _packet_pair_metadata(packet: JudgeEvidencePacket) -> tuple[object, ...]:
    return (
        packet.scenario_family_id,
        packet.scenario_version,
        packet.variant_id,
        packet.fixture_id,
        packet.seed,
        packet.rubric_version,
        packet.pair_evidence_sha256,
        packet.scenario_context,
    )


def _vote_packet_metadata(vote: JudgeVote) -> tuple[object, ...]:
    return (
        vote.scenario_family_id,
        vote.scenario_version,
        vote.variant_id,
        vote.fixture_id,
        vote.seed,
        vote.rubric_version,
        vote.pair_evidence_sha256,
    )


def _packet_vote_metadata(packet: JudgeEvidencePacket) -> tuple[object, ...]:
    return (
        packet.scenario_family_id,
        packet.scenario_version,
        packet.variant_id,
        packet.fixture_id,
        packet.seed,
        packet.rubric_version,
        packet.pair_evidence_sha256,
    )


def _normalize_slot_preference(
    preference: SlotPreference,
    order: PresentationOrder,
) -> JudgePreference:
    if preference is SlotPreference.TIE:
        return JudgePreference.TIE
    if preference is SlotPreference.INVALID:
        return JudgePreference.INVALID
    candidate_slot = (
        SlotPreference.B
        if order is PresentationOrder.BASELINE_FIRST
        else SlotPreference.A
    )
    return (
        JudgePreference.CANDIDATE
        if preference is candidate_slot
        else JudgePreference.BASELINE
    )


def _position_metadata(
    vote: JudgeVote,
) -> tuple[str, str, str, str, int, str, str, str]:
    return (
        vote.scenario_family_id,
        vote.scenario_version,
        vote.variant_id,
        vote.fixture_id,
        vote.seed,
        vote.judge_revision,
        vote.rubric_version,
        vote.pair_evidence_sha256,
    )


def _pair_metadata(vote: JudgeVote) -> tuple[str, str, str, str, int, str, str]:
    return (
        vote.scenario_family_id,
        vote.scenario_version,
        vote.variant_id,
        vote.fixture_id,
        vote.seed,
        vote.rubric_version,
        vote.pair_evidence_sha256,
    )


__all__ = (
    "build_position_flipped_packets",
    "consolidate_position_flips",
    "normalize_raw_judge_result",
    "validate_judge_votes_against_packets",
)
