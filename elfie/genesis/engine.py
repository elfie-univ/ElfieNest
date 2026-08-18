"""Deterministic, structured Genesis candidate generation."""

from __future__ import annotations

import random
from typing import Sequence

from elfie.profile import SpeciesCatalog, get_species_definition

from .appearance import (
    appearance_fit,
    distance,
    generate_appearance,
    signature,
    visible_key,
)
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


class GenesisEngine:
    """Build five intentionally different, deterministic candidate cores."""

    # Keep enough proposals for role-fit, body-shape distance and the visible
    # appearance uniqueness gate to coexist for both dog and fox packages.
    proposal_count = 96
    # The visual key below is the hard uniqueness gate.  Keep the continuous
    # latent-distance gate slightly looser so constrained intents (for example
    # tall/round/soft/warm) can still produce all five candidates across three
    # adoption batches without weakening visible diversity.
    target_distance = 0.12

    def __init__(self, catalog: SpeciesCatalog | None = None) -> None:
        self._catalog = catalog

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
        self._validate_request(
            batch_number, species_id, life_stage, gender, appearance, answers
        )
        stages = _STAGES if life_stage == "any" else (life_stage,)
        core_by_stage = {
            stage: core_profile(
                species_id=species_id,
                life_stage=stage,
                answers=answers,
                catalog=self._catalog,
            )
            for stage in stages
        }
        proposals: dict[str, list[GenesisCandidate]] = {
            role: [] for role in CANDIDATE_ROLES
        }
        for role_index, role in enumerate(CANDIDATE_ROLES):
            for proposal_index in range(self.proposal_count):
                seed = derive_seed(
                    master_seed, batch_number, role_index, proposal_index
                )
                stage = self._choose_stage(seed, batch_number, role_index, life_stage)
                candidate = self._build_candidate(
                    seed=seed,
                    role=role,
                    species_id=species_id,
                    life_stage=stage,
                    gender=self._choose_gender(seed, role_index, gender),
                    appearance=appearance,
                    core=core_by_stage[stage],
                    variant_index=(batch_number - 1) * len(CANDIDATE_ROLES)
                    + role_index,
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
                    if role_fit(item, role, appearance, core_by_stage[item.life_stage])
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
        return core_profile(
            species_id=species_id,
            life_stage=stage,
            answers=answers,
            catalog=self._catalog,
        )

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
        variant_index: int,
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
            variant_index=variant_index,
            catalog=self._catalog,
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
                visual_key=visible_key(genome),
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
        personality = personality_fit(
            candidate.personality.candidate.latent, core.latent
        )
        visual = appearance_fit(candidate.appearance, appearance)
        weight_p, weight_a = ROLE_FIT_WEIGHTS[role]
        existing = tuple(item.signature for item in selected) + history
        novelty = min(
            (distance(candidate.signature, item) for item in existing), default=0.5
        )
        phase_bonus = min(0.20, max(0, batch_number - 1) * 0.08)
        return (
            weight_p * personality + weight_a * visual + (0.45 + phase_bonus) * novelty
        )

    def _is_far_enough(
        self,
        candidate: GenesisCandidate,
        selected: Sequence[GenesisCandidate],
        history: Sequence[CandidateSignature],
    ) -> bool:
        candidate_key = candidate.signature.visual_key
        if candidate_key and any(
            candidate_key == item.signature.visual_key for item in selected
        ):
            return False
        if candidate_key and any(
            candidate_key == item.visual_key for item in history if item.visual_key
        ):
            return False
        if any(
            distance(candidate.signature, item.signature) < self.target_distance
            for item in selected
        ):
            return False
        # Across batches the exact visual key is the product-level uniqueness
        # contract.  Requiring a second continuous-distance threshold here can
        # reject valid combinations merely because one categorical color/recipe
        # hash happens to sit near a previous candidate, even though the
        # rendered region recipe is visibly different.
        return True

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

    def _age_months(self, species_id: str, stage: str, rng: random.Random) -> int:
        definition = (
            self._catalog.definition(species_id, adoptable_only=True)
            if self._catalog is not None
            else get_species_definition(species_id, adoptable_only=True)
        )
        if definition.genesis is None:
            raise GenesisError(f"物种 {species_id!r} 缺少 Genesis 配置")
        ranges = definition.genesis.stage_ranges
        minimum, maximum = ranges[stage]
        return rng.randint(minimum, maximum)

    def _validate_request(
        self,
        batch: int,
        species: str,
        stage: str,
        gender: str,
        appearance: GenesisAppearanceIntent,
        answers: Sequence[str],
    ) -> None:
        if batch not in (1, 2, 3):
            raise GenesisError("Genesis候选批次必须是1、2或3")
        try:
            if self._catalog is not None:
                self._catalog.definition(species, adoptable_only=True)
            else:
                get_species_definition(species, adoptable_only=True)
        except ValueError as error:
            raise GenesisError(f"不支持的物种: {species}") from error
        if stage not in _STAGES + ("any",):
            raise GenesisError(f"不支持的生命阶段: {stage}")
        if gender not in _GENDERS + ("any",):
            raise GenesisError(f"不支持的性别: {gender}")
        if appearance.priority not in ("stature", "build", "face", "signature"):
            raise GenesisError("appearance.priority无效")
        validate_answers(answers)


__all__ = ("GenesisEngine",)
