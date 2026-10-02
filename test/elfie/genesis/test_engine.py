from __future__ import annotations

import random

import pytest

from elfie.genesis import (
    CANDIDATE_ROLES,
    GenesisAppearanceIntent,
    GenesisEngine,
    GenesisError,
    legal_candidate_age_range,
    weighted_candidate_stage,
)
from elfie.genesis.appearance import generate_appearance
from elfie.genesis.world import GenerationPolicy
from infrastructure.persistence.configuration.species import (
    load_and_configure_species_catalog,
)
from infrastructure.persistence.configuration.world import load_genesis_source_package


def intent() -> GenesisAppearanceIntent:
    return GenesisAppearanceIntent(
        stature="any",
        build="any",
        face="balanced",
        signature="any",
        priority="face",
    )


def test_candidate_age_sampling_uses_program_weights_and_lifespan_reserve() -> None:
    policy = load_genesis_source_package().generation_policy
    legal_stages = ("youth", "young_adult", "mature", "elder")
    catalog = load_and_configure_species_catalog()
    tovren = catalog.definition("tovren", adoptable_only=True)

    assert weighted_candidate_stage(legal_stages, policy, 0.74) == "young_adult"
    assert weighted_candidate_stage(legal_stages, policy, 0.75) == "mature"
    assert weighted_candidate_stage(legal_stages, policy, 0.99) == "elder"
    assert legal_candidate_age_range(
        tovren.genesis,
        "elder",
        policy,
    ) == (15, 16)


def test_species_do_not_assign_personality_and_stage_is_a_small_prior() -> None:
    engine = GenesisEngine()
    tovren_mature = engine.core_personality(
        species_id="tovren",
        life_stage="mature",
        answers=("any",) * 5,
    )
    saevi_mature = engine.core_personality(
        species_id="saevi",
        life_stage="mature",
        answers=("any",) * 5,
    )
    tovren_youth = engine.core_personality(
        species_id="tovren",
        life_stage="youth",
        answers=("any",) * 5,
    )

    assert tovren_mature.latent == saevi_mature.latent
    assert tovren_youth.latent != tovren_mature.latent
    assert all(-2.0 <= value <= 2.0 for value in tovren_mature.latent)
    assert max(abs(value) for value in tovren_mature.latent) < 0.2


@pytest.mark.parametrize("species_id", ("tovren", "saevi"))
def test_batch_covers_five_roles_and_is_repeatable(species_id: str) -> None:
    engine = GenesisEngine()
    kwargs = {
        "master_seed": 12345,
        "batch_number": 1,
        "species_id": species_id,
        "life_stage": "any",
        "gender": "any",
        "appearance": intent(),
        "answers": ("quiet", "research", "plan", "discuss", "steady"),
    }

    first = engine.generate_batch(**kwargs)
    second = engine.generate_batch(**kwargs)

    assert [candidate.role for candidate in first.candidates] == [
        candidate.role for candidate in second.candidates
    ]
    assert [candidate.candidate_id for candidate in first.candidates] == [
        candidate.candidate_id for candidate in second.candidates
    ]
    assert {candidate.role for candidate in first.candidates} == set(CANDIDATE_ROLES)
    assert len({candidate.candidate_id for candidate in first.candidates}) == 5
    assert len({candidate.signature for candidate in first.candidates}) == 5
    assert len({candidate.signature.visual_key for candidate in first.candidates}) == 5
    assert (
        len(
            {
                candidate.appearance.coat.primary_color_id
                for candidate in first.candidates
            }
        )
        == 5
    )
    assert (
        len(
            {
                candidate.appearance.coat.region_recipe_id
                for candidate in first.candidates
            }
        )
        == 5
    )
    assert all(
        len(candidate.appearance.coat.region_accents) <= 2
        for candidate in first.candidates
    )
    assert all(candidate.personality.candidate.labels for candidate in first.candidates)


@pytest.mark.parametrize("species_id", ("tovren", "saevi"))
def test_batch_keeps_five_visible_variants_across_seed_sample(species_id: str) -> None:
    engine = GenesisEngine()
    for master_seed in range(10):
        batch = engine.generate_batch(
            master_seed=master_seed,
            batch_number=1,
            species_id=species_id,
            life_stage="young_adult",
            gender="female",
            appearance=intent(),
            answers=("quiet", "research", "plan", "discuss", "steady"),
        )

        assert len(batch.candidates) == 5
        assert (
            len({candidate.signature.visual_key for candidate in batch.candidates}) == 5
        )


def test_previous_batch_signatures_are_respected() -> None:
    engine = GenesisEngine()
    first = engine.generate_batch(
        master_seed=8,
        batch_number=1,
        species_id="tovren",
        life_stage="young_adult",
        gender="female",
        appearance=intent(),
        answers=("approach", "explore", "adapt", "discuss", "lively"),
    )

    second = engine.generate_batch(
        master_seed=8,
        batch_number=2,
        species_id="tovren",
        life_stage="young_adult",
        gender="female",
        appearance=intent(),
        answers=("approach", "explore", "adapt", "discuss", "lively"),
        previous_signatures=tuple(
            candidate.signature for candidate in first.candidates
        ),
    )

    assert not {candidate.candidate_id for candidate in first.candidates} & {
        candidate.candidate_id for candidate in second.candidates
    }
    assert not {candidate.signature.visual_key for candidate in first.candidates} & {
        candidate.signature.visual_key for candidate in second.candidates
    }


def test_candidate_selection_backtracks_only_unfrozen_role_slots(monkeypatch) -> None:
    engine = GenesisEngine(
        generation_policy=GenerationPolicy(
            candidate_options_per_choice=2,
            candidate_total_backtracks=4,
        )
    )
    appearance = intent()
    core = engine.core_personality(
        species_id="tovren", life_stage="young_adult", answers=("any",) * 5
    )
    proposals = {}
    for role_index, role in enumerate(CANDIDATE_ROLES):
        proposals[role] = [
            engine._build_candidate(
                seed=100 + role_index * 10 + proposal_index,
                role=role,
                species_id="tovren",
                life_stage="young_adult",
                gender="female",
                appearance=appearance,
                core=core,
                variant_index=role_index,
            )
            for proposal_index in (0, 1)
        ]

    first_role, second_role = CANDIDATE_ROLES[:2]
    blocked = proposals[first_role][0].candidate_id

    monkeypatch.setattr("elfie.genesis.engine.role_fit", lambda *args, **kwargs: 1.0)
    monkeypatch.setattr(
        engine,
        "_selection_score",
        lambda candidate, **kwargs: 1.0 if candidate.seed % 10 == 0 else 0.0,
    )

    def constrained_distance(candidate, selected, history):
        return not (
            selected
            and selected[0].candidate_id == blocked
            and candidate.role == second_role
        )

    monkeypatch.setattr(engine, "_is_far_enough", constrained_distance)

    selected = engine._select_candidates_with_backtracking(
        proposals=proposals,
        roles=CANDIDATE_ROLES,
        appearance=appearance,
        core_by_stage={"young_adult": core},
        history=(),
        batch_number=1,
    )

    assert selected[0].candidate_id == proposals[first_role][1].candidate_id
    assert len(selected) == len(CANDIDATE_ROLES)


def test_species_stage_ranges_can_differ() -> None:
    engine = GenesisEngine()
    saevi = engine.generate_batch(
        master_seed=1,
        batch_number=1,
        species_id="saevi",
        life_stage="elder",
        gender="female",
        appearance=intent(),
        answers=("any",) * 5,
    )
    tovren = engine.generate_batch(
        master_seed=1,
        batch_number=1,
        species_id="tovren",
        life_stage="elder",
        gender="female",
        appearance=intent(),
        answers=("any",) * 5,
    )

    assert all(10 <= candidate.age_years <= 11 for candidate in saevi.candidates)
    assert all(14 <= candidate.age_years <= 16 for candidate in tovren.candidates)


def test_unspecified_stage_uses_configured_young_adult_prior() -> None:
    batch = GenesisEngine().generate_batch(
        master_seed=41,
        batch_number=1,
        species_id="saevi",
        life_stage="any",
        gender="female",
        appearance=intent(),
        answers=("any",) * 5,
    )

    assert all(candidate.life_stage != "elder" for candidate in batch.candidates)


@pytest.mark.parametrize("species_id", ("saevi", "tovren"))
def test_youth_candidates_are_older_than_one_local_year(species_id: str) -> None:
    batch = GenesisEngine().generate_batch(
        master_seed=19,
        batch_number=1,
        species_id=species_id,
        life_stage="youth",
        gender="female",
        appearance=intent(),
        answers=("any",) * 5,
    )

    assert all(candidate.age_years >= 2 for candidate in batch.candidates)


def test_exact_age_continuously_changes_youth_height_and_allometry() -> None:
    common = {
        "seed": 73,
        "species_id": "tovren",
        "intent": intent(),
        "role": "appearance_anchor",
        "variant_index": 0,
        "life_stage": "youth",
        "gender": "female",
    }

    youngest = generate_appearance(
        **common,
        age_years=1,
        rng=random.Random(73),
    )
    oldest = generate_appearance(
        **common,
        age_years=2,
        rng=random.Random(73),
    )

    assert youngest.macro.stature_z < oldest.macro.stature_z
    assert youngest.proportions.head_torso_bias > oldest.proportions.head_torso_bias
    assert youngest.proportions.arm_torso_bias < oldest.proportions.arm_torso_bias
    assert youngest.proportions.leg_torso_bias < oldest.proportions.leg_torso_bias


def test_sex_is_only_a_weak_adult_height_prior() -> None:
    common = {
        "seed": 91,
        "species_id": "saevi",
        "intent": intent(),
        "role": "appearance_anchor",
        "variant_index": 0,
        "life_stage": "mature",
        "age_years": 8,
    }

    female = generate_appearance(
        **common,
        gender="female",
        rng=random.Random(91),
    )
    male = generate_appearance(
        **common,
        gender="male",
        rng=random.Random(91),
    )

    assert 0.0 < male.macro.stature_z - female.macro.stature_z <= 0.65
    assert male.coat == female.coat


def test_invalid_answers_are_rejected_before_generation() -> None:
    with pytest.raises(GenesisError):
        GenesisEngine().generate_batch(
            master_seed=1,
            batch_number=1,
            species_id="saevi",
            life_stage="any",
            gender="any",
            appearance=intent(),
            answers=("unknown",) * 5,
        )
