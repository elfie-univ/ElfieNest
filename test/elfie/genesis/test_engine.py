from __future__ import annotations

import random

import pytest

from elfie.genesis import (
    CANDIDATE_ROLES,
    GenesisAppearanceIntent,
    GenesisEngine,
    GenesisError,
)
from elfie.genesis.appearance import generate_appearance


def intent() -> GenesisAppearanceIntent:
    return GenesisAppearanceIntent(
        stature="any",
        build="any",
        face="balanced",
        signature="any",
        priority="face",
    )


def test_species_and_stage_are_small_priors_not_global_multipliers() -> None:
    engine = GenesisEngine()
    dog = engine.core_personality(
        species_id="dog",
        life_stage="mature",
        answers=("any",) * 5,
    )
    fox = engine.core_personality(
        species_id="fox",
        life_stage="mature",
        answers=("any",) * 5,
    )

    assert dog.latent != fox.latent
    assert all(-2.0 <= value <= 2.0 for value in dog.latent)
    assert max(abs(value) for value in dog.latent) < 0.2


@pytest.mark.parametrize("species_id", ("dog", "fox"))
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


@pytest.mark.parametrize("species_id", ("dog", "fox"))
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
        species_id="dog",
        life_stage="young_adult",
        gender="female",
        appearance=intent(),
        answers=("approach", "explore", "adapt", "discuss", "lively"),
    )

    second = engine.generate_batch(
        master_seed=8,
        batch_number=2,
        species_id="dog",
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


def test_species_stage_ranges_can_differ() -> None:
    engine = GenesisEngine()
    fox = engine.generate_batch(
        master_seed=1,
        batch_number=1,
        species_id="fox",
        life_stage="elder",
        gender="female",
        appearance=intent(),
        answers=("any",) * 5,
    )
    dog = engine.generate_batch(
        master_seed=1,
        batch_number=1,
        species_id="dog",
        life_stage="elder",
        gender="female",
        appearance=intent(),
        answers=("any",) * 5,
    )

    assert all(10 <= candidate.age_years <= 15 for candidate in fox.candidates)
    assert all(14 <= candidate.age_years <= 20 for candidate in dog.candidates)


def test_exact_age_continuously_changes_youth_height_and_allometry() -> None:
    common = {
        "seed": 73,
        "species_id": "dog",
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
        "species_id": "fox",
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
            species_id="fox",
            life_stage="any",
            gender="any",
            appearance=intent(),
            answers=("unknown",) * 5,
        )
