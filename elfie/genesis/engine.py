"""Deterministic, structured Genesis candidate generation."""

from __future__ import annotations

import random
from typing import Mapping, Sequence

from .appearance import appearance_fit, distance, generate_appearance, signature
from .contracts import (
    CANDIDATE_ROLES,
    STAGE_PLASTICITY,
    BigFiveProfile,
    CandidateSignature,
    GenesisAppearanceIntent,
    GenesisBatch,
    GenesisCandidate,
    GenesisError,
    GenesisPersonality,
)
from .personality import core_profile, profile, role_delta, validate_answers
from .selection import (
    ROLE_FIT_FLOORS,
    ROLE_FIT_WEIGHTS,
    derive_seed,
    personality_fit,
    role_fit,
)

_STAGES = ("youth", "young_adult", "mature", "elder")
_GENDERS = ("male", "female")
_STAGE_RANGES: Mapping[str, Mapping[str, tuple[int, int]]] = {
    "fox": {
        "youth": (6, 23),
        "young_adult": (24, 59),
        "mature": (60, 119),
        "elder": (120, 180),
    },
    "dog": {
        "youth": (6, 23),
        "young_adult": (24, 71),
        "mature": (72, 167),
        "elder": (168, 240),
    },
}
class GenesisEngine:
    """Build five intentionally different, deterministic candidate cores."""

    proposal_count = 64
    target_distance = 0.16
    history_distance = 0.14

    def generate_batch(
        self,
        *,
        master_seed: int,
        batch_number: int,
        species_id: str,
        life_stage: str,
        gender: str,
        appearance: GenesisAppearanceIntent,
        answers: Sequence[str],
        previous_signatures: Sequence[CandidateSignature] = (),
    ) -> GenesisBatch:
        self._validate_request(batch_number, species_id, life_stage, gender, appearance, answers)
        stages = _STAGES if life_stage == "any" else (life_stage,)
        core_by_stage = {
            stage: core_profile(species_id=species_id, life_stage=stage, answers=answers)
            for stage in stages
        }
        proposals = {role: [] for role in CANDIDATE_ROLES}
        for role_index, role in enumerate(CANDIDATE_ROLES):
            for proposal_index in range(self.proposal_count):
                seed = derive_seed(master_seed, batch_number, role_index, proposal_index)
                stage = self._choose_stage(seed, batch_number, role_index, life_stage)
                candidate = self._build_candidate(
                    seed=seed,
                    role=role,
                    species_id=species_id,
                    life_stage=stage,
                    gender=self._choose_gender(seed, role_index, gender),
                    appearance=appearance,
                    core=core_by_stage[stage],
                )
                proposals[role].append(candidate)

        selected: list[GenesisCandidate] = []
        history = tuple(previous_signatures)
        for role in CANDIDATE_ROLES:
            ranked = sorted(
                proposals[role],
                key=lambda candidate: self._selection_score(
                    candidate,
                    role=role,
                    appearance=appearance,
                    core=core_by_stage[candidate.life_stage],
                    selected=tuple(selected),
                    history=history,
                    batch_number=batch_number,
                ),
                reverse=True,
            )
            choice = next(
                (
                    item
                    for item in ranked
                    if role_fit(
                        item, role, appearance, core_by_stage[item.life_stage]
                    )
                    >= ROLE_FIT_FLOORS[role]
                    and self._is_far_enough(item, selected, history)
                ),
                None,
            )
            if choice is None:
                raise GenesisError("无法同时满足候选匹配下限和差异度门槛，请重试本批次")
            selected.append(choice)
        random.Random(derive_seed(master_seed, batch_number, 91, 0)).shuffle(selected)
        core_stage = "young_adult" if life_stage == "any" else stages[0]
        return GenesisBatch(batch_number, tuple(selected), core_by_stage[core_stage])

    def core_personality(
        self, *, species_id: str, life_stage: str, answers: Sequence[str]
    ) -> BigFiveProfile:
        stage = "young_adult" if life_stage == "any" else life_stage
        return core_profile(species_id=species_id, life_stage=stage, answers=answers)

    def _build_candidate(
        self,
        *,
        seed: int,
        role: str,
        species_id: str,
        life_stage: str,
        gender: str,
        appearance: GenesisAppearanceIntent,
        core: BigFiveProfile,
    ) -> GenesisCandidate:
        rng = random.Random(seed)
        latent = tuple(
            max(-2.0, min(2.0, base + STAGE_PLASTICITY[life_stage] * delta + noise))
            for base, delta, noise in zip(
                core.latent,
                role_delta(role, core.latent, rng),
                (rng.uniform(-0.045, 0.045) for _ in core.latent),
            )
        )
        genome = generate_appearance(
            seed=seed,
            species_id=species_id,
            intent=appearance,
            role=role,
            rng=rng,
        )
        return GenesisCandidate(
            candidate_id=f"{derive_seed(seed, 7, 0, 0):016x}",
            role=role,
            seed=seed,
            species_id=species_id,
            life_stage=life_stage,
            age_months=self._age_months(species_id, life_stage, rng),
            gender=gender,
            appearance=genome,
            personality=GenesisPersonality(core, profile(latent)),
            signature=CandidateSignature(
                personality=tuple(value / 2.0 for value in latent),
                appearance=signature(genome),
            ),
        )

    def _selection_score(
        self,
        candidate: GenesisCandidate,
        *,
        role: str,
        appearance: GenesisAppearanceIntent,
        core: BigFiveProfile,
        selected: tuple[GenesisCandidate, ...],
        history: tuple[CandidateSignature, ...],
        batch_number: int,
    ) -> float:
        personality = personality_fit(candidate.personality.candidate.latent, core.latent)
        visual = appearance_fit(candidate.appearance, appearance)
        weight_p, weight_a = ROLE_FIT_WEIGHTS[role]
        existing = tuple(item.signature for item in selected) + history
        novelty = min((distance(candidate.signature, item) for item in existing), default=0.5)
        phase_bonus = min(0.20, max(0, batch_number - 1) * 0.08)
        return weight_p * personality + weight_a * visual + (0.45 + phase_bonus) * novelty

    def _is_far_enough(
        self,
        candidate: GenesisCandidate,
        selected: Sequence[GenesisCandidate],
        history: Sequence[CandidateSignature],
    ) -> bool:
        if any(distance(candidate.signature, item.signature) < self.target_distance for item in selected):
            return False
        return all(distance(candidate.signature, item) >= self.history_distance for item in history)

    @staticmethod
    def _choose_stage(seed: int, batch: int, role: int, requested: str) -> str:
        if requested != "any":
            return requested
        offset = batch % len(_STAGES)
        order = _STAGES[offset:] + _STAGES[:offset]
        return order[(role + seed) % len(order)]

    @staticmethod
    def _choose_gender(seed: int, role: int, requested: str) -> str:
        if requested != "any":
            return requested
        return _GENDERS[(role + seed) % len(_GENDERS)]

    @staticmethod
    def _age_months(species_id: str, stage: str, rng: random.Random) -> int:
        minimum, maximum = _STAGE_RANGES[species_id][stage]
        return rng.randint(minimum, maximum)

    @staticmethod
    def _validate_request(
        batch: int,
        species: str,
        stage: str,
        gender: str,
        appearance: GenesisAppearanceIntent,
        answers: Sequence[str],
    ) -> None:
        if batch not in (1, 2, 3):
            raise GenesisError("Genesis候选批次必须是1、2或3")
        if species not in ("dog", "fox"):
            raise GenesisError(f"不支持的物种: {species}")
        if stage not in _STAGES + ("any",):
            raise GenesisError(f"不支持的生命阶段: {stage}")
        if gender not in _GENDERS + ("any",):
            raise GenesisError(f"不支持的性别: {gender}")
        if appearance.priority not in ("stature", "build", "face", "signature"):
            raise GenesisError("appearance.priority无效")
        validate_answers(answers)


__all__ = ("GenesisEngine",)
