"""Deterministic, structured Genesis candidate generation."""

from __future__ import annotations

import hashlib
import json
import math
import random
import unicodedata
from typing import Sequence

from elfie.profile import (
    SpeciesCatalog,
    SpeciesGenesisProfile,
    get_species_definition,
)

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
from .world import GenerationPolicy

_STAGES = ("youth", "young_adult", "mature", "elder")
_GENDERS = ("male", "female")


def legal_candidate_age_range(
    genesis: SpeciesGenesisProfile,
    stage: str,
    generation_policy: GenerationPolicy,
) -> tuple[int, int]:
    """Return one stage's legal ages after applying candidate and lifespan limits."""

    if stage not in _STAGES:
        raise GenesisError(f"不支持的候选生命阶段: {stage}")
    minimum, maximum = genesis.stage_ranges[stage]
    minimum = max(minimum, generation_policy.candidate_minimum_age_years)
    stage_index = _STAGES.index(stage)
    if stage_index:
        previous_maximum = genesis.stage_ranges[_STAGES[stage_index - 1]][1]
        minimum = max(minimum, previous_maximum + 1)
    maximum = min(
        maximum,
        genesis.terminal_age_years - generation_policy.candidate_age_reserve_years,
    )
    return minimum, maximum


def weighted_candidate_stage(
    legal_stages: Sequence[str],
    generation_policy: GenerationPolicy,
    draw: float,
) -> str:
    """Choose a legal stage with the published prior using a unit interval draw."""

    if not legal_stages:
        raise GenesisError("没有符合赴地年龄规则的候选生命阶段")
    if (
        isinstance(draw, bool)
        or not isinstance(draw, (int, float))
        or not math.isfinite(float(draw))
        or not 0 <= draw < 1
    ):
        raise GenesisError("候选年龄阶段抽样值必须位于 [0, 1)")
    choices = tuple(
        (stage, generation_policy.candidate_stage_weight(stage))
        for stage in legal_stages
        if generation_policy.candidate_stage_weight(stage) > 0.0
    )
    if not choices:
        choices = tuple((stage, 1.0) for stage in legal_stages)
    remaining = float(draw) * sum(weight for _, weight in choices)
    for stage, weight in choices:
        remaining -= weight
        if remaining < 0.0:
            return stage
    return choices[-1][0]


class GenesisEngine:
    """Build five intentionally different, deterministic candidate cores."""

    # The visual key below is the hard uniqueness gate.  Keep the continuous
    # latent-distance gate slightly looser so constrained intents (for example
    # tall/round/soft/warm) can still produce all five candidates across three
    # adoption batches without weakening visible diversity.
    target_distance = 0.12

    def __init__(
        self,
        catalog: SpeciesCatalog | None = None,
        generation_policy: GenerationPolicy | None = None,
    ) -> None:
        self._catalog = catalog
        self._generation_policy = generation_policy or GenerationPolicy()

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
        stages = self._legal_stages(species_id, life_stage)
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
            for proposal_index in range(
                self._generation_policy.candidate_proposal_count
            ):
                seed = self._labeled_seed(
                    master_seed,
                    "candidate",
                    f"batch:{batch_number}:role:{role_index}:proposal:{proposal_index}",
                    legacy_parts=(
                        master_seed,
                        batch_number,
                        role_index,
                        proposal_index,
                    ),
                )
                stage = self._choose_stage(
                    seed,
                    batch_number,
                    role_index,
                    life_stage,
                    stages,
                )
                candidate = self._build_candidate(
                    seed=seed,
                    role=role,
                    species_id=species_id,
                    life_stage=stage,
                    gender=self._choose_gender(seed, batch_number, role_index, gender),
                    appearance=appearance,
                    core=core_by_stage[stage],
                    variant_index=(batch_number - 1) * len(CANDIDATE_ROLES)
                    + role_index,
                )
                proposals[role].append(candidate)

        history = tuple(previous_signatures)
        selected = self._select_candidates_with_backtracking(
            proposals=proposals,
            roles=CANDIDATE_ROLES,
            appearance=appearance,
            core_by_stage=core_by_stage,
            history=history,
            batch_number=batch_number,
        )
        random.Random(
            self._labeled_seed(
                master_seed,
                "candidate",
                f"batch:{batch_number}:shuffle",
                legacy_parts=(master_seed, batch_number, 91, 0),
            )
        ).shuffle(selected)
        core_stage = "young_adult" if life_stage == "any" else stages[0]
        return GenesisBatch(batch_number, tuple(selected), core_by_stage[core_stage])

    def _select_candidates_with_backtracking(
        self,
        *,
        proposals: dict[str, list[GenesisCandidate]],
        roles: Sequence[str],
        appearance: GenesisAppearanceIntent,
        core_by_stage: dict[str, BigFiveProfile],
        history: tuple[CandidateSignature, ...],
        batch_number: int,
    ) -> list[GenesisCandidate]:
        """Choose one candidate per role within the published search budget.

        Role and user inputs are frozen before this method.  Only an earlier
        candidate slot may be reconsidered when a later slot has no legal
        candidate.  Ranking and traversal are stable, so retries with the
        same source inputs produce the same result.
        """

        options_per_choice = self._generation_policy.candidate_options_per_choice
        max_backtracks = self._generation_policy.candidate_total_backtracks
        backtracks = 0

        def search(
            index: int, selected: tuple[GenesisCandidate, ...]
        ) -> tuple[GenesisCandidate, ...] | None:
            nonlocal backtracks
            if index == len(roles):
                return selected
            role = roles[index]
            ranked = self._ranked_candidates(
                proposals[role],
                role=role,
                appearance=appearance,
                core_by_stage=core_by_stage,
                selected=selected,
                history=history,
                batch_number=batch_number,
            )
            if not ranked:
                return None
            for option_index, choice in enumerate(ranked[:options_per_choice]):
                result = search(index + 1, selected + (choice,))
                if result is not None:
                    return result
                if option_index + 1 < len(ranked[:options_per_choice]):
                    backtracks += 1
                    if backtracks > max_backtracks:
                        return None
            return None

        result = search(0, ())
        if result is None:
            raise GenesisError("无法在候选匹配、差异度和有限回溯预算内组成完整候选批次")
        return list(result)

    def _ranked_candidates(
        self,
        candidates: Sequence[GenesisCandidate],
        *,
        role: str,
        appearance: GenesisAppearanceIntent,
        core_by_stage: dict[str, BigFiveProfile],
        selected: tuple[GenesisCandidate, ...],
        history: tuple[CandidateSignature, ...],
        batch_number: int,
    ) -> list[GenesisCandidate]:
        ranked = sorted(
            candidates,
            key=lambda candidate: self._selection_score(
                candidate,
                role=role,
                appearance=appearance,
                core=core_by_stage[candidate.life_stage],
                selected=selected,
                history=history,
                batch_number=batch_number,
            ),
            reverse=True,
        )
        return [
            candidate
            for candidate in ranked
            if role_fit(
                candidate,
                role,
                appearance,
                core_by_stage[candidate.life_stage],
            )
            >= ROLE_FIT_FLOORS[role]
            and self._is_far_enough(candidate, selected, history)
        ]

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
        age_years = self._age_years(
            species_id,
            life_stage,
            random.Random(
                self._labeled_seed(
                    seed,
                    "age",
                    f"candidate:{seed}",
                    legacy_parts=(seed, 8, 0, 0),
                )
            ),
        )
        genome = generate_appearance(
            seed=seed,
            species_id=species_id,
            intent=appearance,
            role=role,
            rng=rng,
            life_stage=life_stage,
            age_years=age_years,
            gender=gender,
            variant_index=variant_index,
            catalog=self._catalog,
        )
        return GenesisCandidate(
            candidate_id=f"{self._labeled_seed(seed, 'candidate', f'id:{seed}', legacy_parts=(seed, 7, 0, 0)):016x}",
            role=role,
            seed=seed,
            species_id=species_id,
            life_stage=life_stage,
            age_years=age_years,
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

    def _choose_stage(
        self,
        seed: int,
        batch: int,
        role: int,
        requested: str,
        legal_stages: Sequence[str],
    ) -> str:
        if requested != "any":
            return requested
        draw = random.Random(
            self._labeled_seed(
                seed,
                "age",
                f"batch:{batch}:role:{role}:stage",
                legacy_parts=(seed, batch, role, 92),
            )
        ).random()
        return weighted_candidate_stage(legal_stages, self._generation_policy, draw)

    def _choose_gender(self, seed: int, batch: int, role: int, requested: str) -> str:
        if requested != "any":
            return requested
        draw = self._labeled_seed(
            seed,
            "candidate",
            f"batch:{batch}:role:{role}:gender",
            legacy_parts=(seed, role),
        )
        return _GENDERS[draw % len(_GENDERS)]

    def _labeled_seed(
        self,
        seed: int,
        domain: str,
        stable_id: str,
        *,
        legacy_parts: tuple[int, ...],
    ) -> int:
        """Derive candidate randomness from the published Genesis policy."""

        algorithm = self._generation_policy.seed_algorithm
        if algorithm == "blake2b-labeled-v1":
            return derive_seed(*legacy_parts)
        if algorithm != "sha256-domain-v1":
            raise GenesisError(f"不支持的 Genesis seed 算法: {algorithm}")
        if (
            isinstance(seed, bool)
            or not isinstance(seed, int)
            or not 0 <= seed < 2**256
        ):
            raise GenesisError("SHA-256 Genesis master_seed 必须是 32 字节非负整数")
        canonical = {
            "algorithm_version": algorithm,
            "attempt_id": 0,
            "domain": unicodedata.normalize("NFC", domain),
            "domain_policy_version": self._generation_policy.policy_version,
            "draw_counter": 0,
            "master_seed": f"{seed:064x}",
            "stable_object_or_slot_id": unicodedata.normalize("NFC", stable_id),
        }
        encoded = json.dumps(
            canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return int.from_bytes(hashlib.sha256(encoded).digest(), "big")

    def _age_years(self, species_id: str, stage: str, rng: random.Random) -> int:
        definition = (
            self._catalog.definition(species_id, adoptable_only=True)
            if self._catalog is not None
            else get_species_definition(species_id, adoptable_only=True)
        )
        if definition.genesis is None:
            raise GenesisError(f"物种 {species_id!r} 缺少 Genesis 配置")
        minimum, maximum = self._legal_age_range(definition, stage)
        if minimum > maximum:
            raise GenesisError(
                f"物种 {species_id!r} 的 {stage} 阶段没有符合赴地年龄规则的候选"
            )
        return rng.randint(minimum, maximum)

    def _legal_stages(self, species_id: str, requested: str) -> tuple[str, ...]:
        definition = (
            self._catalog.definition(species_id, adoptable_only=True)
            if self._catalog is not None
            else get_species_definition(species_id, adoptable_only=True)
        )
        if definition.genesis is None:
            raise GenesisError(f"物种 {species_id!r} 缺少 Genesis 配置")
        stages = _STAGES if requested == "any" else (requested,)
        for stage in stages:
            minimum, maximum = self._legal_age_range(definition, stage)
            if minimum > maximum:
                raise GenesisError(
                    f"物种 {species_id!r} 的 {stage} 阶段没有符合赴地年龄规则的候选"
                )
        return tuple(stages)

    def _legal_age_range(self, definition, stage: str) -> tuple[int, int]:
        if definition.genesis is None:
            raise GenesisError(f"物种 {definition.species_id!r} 缺少 Genesis 配置")
        return legal_candidate_age_range(
            definition.genesis,
            stage,
            self._generation_policy,
        )

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
        self._legal_stages(species, stage)


__all__ = ("GenesisEngine",)
