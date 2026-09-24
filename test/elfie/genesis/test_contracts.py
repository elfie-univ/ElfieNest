from __future__ import annotations

from dataclasses import replace

import pytest

from elfie.genesis import (
    GenesisBundle,
    GenesisCompileInput,
    GenesisCompiler,
    GenesisError,
    GenesisValidationError,
)
from elfie.genesis.compiler import stage_for_age
from infrastructure.persistence.configuration.species import (
    load_and_configure_species_catalog,
)
from infrastructure.persistence.configuration.world import load_genesis_source_package


def _compilation(
    elfie_id: str = "genesis-check",
    *,
    species_id: str = "fox",
    stage: str = "youth",
    age_years: int | None = None,
    seed: int = 23,
    source=None,
):
    catalog = load_and_configure_species_catalog()
    source = source or load_genesis_source_package()
    definition = catalog.definition(species_id, adoptable_only=True)
    assert definition.genesis is not None
    if age_years is None:
        minimum, maximum = definition.genesis.stage_ranges[stage]
        age_years = next(
            age
            for age in range(max(2, minimum), maximum + 1)
            if stage_for_age(species_id, age, catalog) == stage
        )
    return GenesisCompiler(source, catalog=catalog).compile(
        GenesisCompileInput(
            elfie_id=elfie_id,
            owner_reference="genesis-owner",
            display_name="Lumi",
            species_id=species_id,
            gender="female",
            life_stage=stage,
            age_years_at_adoption=age_years,
            appearance_seed=seed,
            height="standard",
            build="standard",
            face="soft",
            signature="warm",
            personality_style="好奇探索",
            original_name="Lumi-origin",
            adoption_anchor_at="2026-08-12T00:00:00+00:00",
            reservation_id=f"manifest:{elfie_id}",
            idempotency_key=f"submit:{elfie_id}",
            arrival_base_id="elfie_nest",
        )
    )


def _bundle() -> GenesisBundle:
    return _compilation().bundle


def test_genesis_bundle_validates_age_feasible_creation_outputs() -> None:
    bundle = _bundle()
    source = load_genesis_source_package()
    required_youth_themes = {
        theme.theme_id
        for theme in source.episode_themes
        if theme.required and "youth" in theme.life_stages and theme.min_age_years <= 2
    }

    assert bundle.validate() is None
    assert len(bundle.knowledge_seeds) == 124
    facts = {fact.fact_id: fact.statement for fact in source.knowledge}
    assert all(seed.content == facts[seed.seed_id] for seed in bundle.knowledge_seeds)
    knowledge_ids = {seed.seed_id for seed in bundle.knowledge_seeds}
    assert {"E-08", "E-08-02", "E-08-03"} <= knowledge_ids
    assert "B-04-02" not in knowledge_ids
    assert {
        episode.theme_id for episode in bundle.episode_seeds
    } == required_youth_themes
    assert bundle.relationship_seeds
    assert {seed.object_kind for seed in bundle.relationship_seeds[:-2]} == {"elfie"}
    assert bundle.relationship_seeds[-2].object_kind == "person"
    assert bundle.relationship_seeds[-2].role == "owner"
    assert bundle.relationship_seeds[-1].object_kind == "group"
    assert bundle.manifest.output_ids


def test_genesis_accepts_typed_elfie_and_group_relationship_objects() -> None:
    bundle = _bundle()

    assert all(
        relationship.object_kind in {"elfie", "person", "group"}
        for relationship in bundle.relationship_seeds
    )
    assert bundle.validate() is None


def test_genesis_rejects_adoption_before_age_two() -> None:
    with pytest.raises(GenesisError, match="至少 2 岁"):
        _compilation(stage="youth", age_years=1)


def test_genesis_allows_more_than_five_source_grounded_events() -> None:
    bundle = _compilation(stage="mature").bundle
    last = bundle.episode_seeds[-1]
    extra = replace(
        last,
        seed_id="extra-episode",
        predecessor_ids=(last.seed_id,),
        causal_links=(f"{last.seed_id} -> extra-episode",),
    )
    expanded = replace(bundle, episode_seeds=(*bundle.episode_seeds, extra))

    assert expanded.validate() is None


def test_genesis_rejects_duplicate_relationship_objects() -> None:
    bundle = _bundle()
    duplicate_target = replace(
        bundle.relationship_seeds[1],
        object_id=bundle.relationship_seeds[0].object_id,
    )
    invalid = replace(
        bundle,
        relationship_seeds=(
            bundle.relationship_seeds[0],
            duplicate_target,
            *bundle.relationship_seeds[2:],
        ),
    )

    with pytest.raises(GenesisValidationError, match="relationship object_id 必须唯一"):
        invalid.validate()


def test_genesis_relationship_object_must_be_its_person() -> None:
    bundle = _bundle()
    invalid = replace(
        bundle,
        relationship_seeds=(
            replace(bundle.relationship_seeds[0], object_id="another-person"),
            *bundle.relationship_seeds[1:],
        ),
    )

    with pytest.raises(GenesisValidationError, match="object_id 必须与 person_id 一致"):
        invalid.validate()


def test_profile_output_is_not_a_genesis_replay_record() -> None:
    profile = _bundle().profile_draft.profile
    serialized = profile.to_dict()

    assert set(serialized) == {"schema_version", "identity", "appearance"}
    assert set(serialized["identity"]) == {
        "elfie_id",
        "display_name",
        "species_id",
        "gender",
        "origin",
    }
    assert not any(
        key in str(serialized)
        for key in ("canon", "seed", "questionnaire", "personality", "world_knowledge")
    )


def test_same_compilation_input_has_the_same_structural_digest_and_ids() -> None:
    first = _compilation("deterministic-elfie")
    second = _compilation("deterministic-elfie")

    assert first.life_context == second.life_context
    assert first.bundle.manifest.content_hash == second.bundle.manifest.content_hash
    assert first.bundle.manifest.output_ids == second.bundle.manifest.output_ids


def test_generation_catalogs_change_life_social_and_episode_outputs() -> None:
    compilations = tuple(
        _compilation(f"catalog-{seed:04d}", seed=seed, stage="mature")
        for seed in (*range(1, 17), *range(18, 25))
    )

    assert (
        len({item.life_context.origin.birth_settlement_id for item in compilations}) > 1
    )
    # A vocation is not sampled from a catalog; the source requires actual
    # teacher-backed apprenticeship evidence before assigning one.
    assert all(
        relationship.person_species_id
        for compilation in compilations
        for relationship in compilation.bundle.relationship_seeds
        if relationship.role not in {"owner", "earth_household"}
    )
    assert all(compilation.bundle.validate() is None for compilation in compilations)
    assert (
        len(
            {
                episode.theme_id
                for compilation in compilations
                for episode in compilation.bundle.episode_seeds
            }
        )
        > 5
    )


def test_age_is_directly_mapped_to_the_requested_earth_year() -> None:
    compilation = _compilation("age-elfie", stage="mature")

    assert compilation.life_context.identity.age_years_at_adoption == 6
    assert compilation.profile.identity.origin.age_years == 6
    assert all(
        episode.age_years_at_event is not None and episode.age_years_at_event <= 6
        for episode in compilation.bundle.episode_seeds
    )


def test_genesis_requires_the_confirmed_simple_preparation_duration() -> None:
    source = load_genesis_source_package()
    invalid_source = replace(
        source,
        earth_arrival_rules=replace(
            source.earth_arrival_rules,
            preparation_duration_local_days=2,
        ),
    )

    with pytest.raises(GenesisError, match="固定为一次 3 个本地日"):
        _compilation("wrong-preparation-duration", source=invalid_source)


def test_genesis_rejects_an_unavailable_required_arrival_fact() -> None:
    source = load_genesis_source_package()
    required_id = source.earth_arrival_rules.required_knowledge_ids[0]
    invalid_facts = tuple(
        replace(fact, eligibility=("dog",)) if fact.fact_id == required_id else fact
        for fact in source.knowledge
    )
    invalid_source = replace(source, knowledge=invalid_facts)

    with pytest.raises(GenesisError, match="赴地必修知识"):
        _compilation("unavailable-arrival-fact", source=invalid_source)
