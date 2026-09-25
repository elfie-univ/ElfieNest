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
    compilation = _compilation()
    bundle = compilation.bundle
    source = load_genesis_source_package()
    required_youth_themes = {
        theme.theme_id
        for theme in source.episode_themes
        if theme.required and "youth" in theme.life_stages and theme.min_age_years <= 2
    }

    assert bundle.validate() is None
    assert len(bundle.knowledge_seeds) >= 100
    facts = {fact.fact_id: fact.statement for fact in source.knowledge}
    assert all(seed.content == facts[seed.seed_id] for seed in bundle.knowledge_seeds)
    knowledge_ids = {seed.seed_id for seed in bundle.knowledge_seeds}
    assert {"E-08", "E-08-02", "E-08-03"} <= knowledge_ids
    assert {"B-03-02", "B-04-02"}.isdisjoint(knowledge_ids)
    assert required_youth_themes <= {
        episode.theme_id for episode in bundle.episode_seeds
    }
    assert bundle.relationship_seeds
    assert {seed.object_kind for seed in bundle.relationship_seeds[:-2]} == {"elfie"}
    assert bundle.relationship_seeds[-2].object_kind == "person"
    assert bundle.relationship_seeds[-2].role == "owner"
    assert bundle.relationship_seeds[-1].object_kind == "group"
    assert (
        len(bundle.place_seeds) == 49
    )  # 46 published places (including regions) + world/private home + Earth home
    assert {place.place_id for place in source.places} <= {
        seed.place_id for seed in bundle.place_seeds
    }
    assert len(bundle.place_relation_seeds) == 7

    assert {
        (relation.subject_id, relation.relation, relation.object_id)
        for relation in bundle.place_relation_seeds
    } == {
        (relation.subject_id, relation.relation, relation.object_id)
        for relation in source.place_relations
    }
    assert "skyreach_square" not in compilation.life_context.mobility.visited_place_ids
    assert "earthbound_road" in compilation.life_context.mobility.familiar_route_ids
    assert compilation.life_context.earth_transition.route_id == "earthbound_road"
    travel_paths = {
        path_id: (cells, days)
        for path_id, cells, days in compilation.life_context.mobility.travel_paths
    }
    station_path, station_days = travel_paths["birth_to_earthbound_station"]
    assert station_path[0].startswith("R") and station_path[-1] == "R4C3"
    assert station_days == (len(station_path) - 1) * 2
    assert len(station_path) > 1
    place_importance = {seed.place_id: seed.importance for seed in bundle.place_seeds}
    assert place_importance["earthbound_station"] > place_importance["skyreach_square"]
    assert place_importance[f"private:{compilation.life_context.elfie_id}:home"] == 0.9
    assert all(
        episode.route_ids
        for episode in bundle.episode_seeds
        if episode.theme_id in {"departure-decision", "arrival-nest"}
    )
    assert bundle.manifest.output_ids


def test_compiler_rejects_age_inside_terminal_reserve() -> None:
    with pytest.raises(GenesisError, match="生命终点"):
        _compilation(stage="elder", age_years=12)


def test_genesis_accepts_typed_elfie_and_group_relationship_objects() -> None:
    bundle = _bundle()

    assert all(
        relationship.object_kind in {"elfie", "person", "group"}
        for relationship in bundle.relationship_seeds
    )
    assert bundle.validate() is None


def test_compiler_emits_a_deduplicated_core_family_graph() -> None:
    compilation = _compilation("family-graph", stage="mature", age_years=6)
    relationships = compilation.bundle.relationship_seeds
    family = tuple(
        relationship
        for relationship in relationships
        if relationship.role in {"parent", "sibling", "partner", "child"}
    )
    parent_ids = {
        relationship.person_id
        for relationship in family
        if relationship.role == "parent"
    }

    assert len(parent_ids) == 2
    assert len({relationship.person_id for relationship in relationships}) == len(
        relationships
    )
    assert all(
        relationship.person_gender and relationship.life_status in {"alive", "deceased"}
        for relationship in family
    )
    for relationship in family:
        assert len(relationship.related_person_ids) == len(
            set(relationship.related_person_ids)
        )
    for relationship in family:
        if relationship.role == "parent":
            assert "self" in relationship.related_person_ids
            assert parent_ids - {relationship.person_id} <= set(
                relationship.related_person_ids
            )
        elif relationship.role == "sibling":
            assert {"self", *parent_ids} <= set(relationship.related_person_ids)
    assert compilation.bundle.validate() is None


def test_compiler_uses_one_ordered_parent_children_set() -> None:
    source = load_genesis_source_package()
    source = replace(
        source,
        generation_policy=replace(
            source.generation_policy,
            family_child_count_distribution=((3, 1.0),),
            family_partner_annual_probability=0.0,
        ),
    )
    compilation = _compilation(
        "family-shared-children",
        stage="mature",
        age_years=6,
        seed=7,
        source=source,
    )
    relationships = compilation.bundle.relationship_seeds
    parents = tuple(item for item in relationships if item.role == "parent")
    siblings = tuple(item for item in relationships if item.role == "sibling")

    assert len(parents) == 2
    assert len(siblings) == 2
    assert [item.age_years_at_genesis for item in siblings] == [7, 5]
    assert [item.birth_order for item in siblings] == [1, 3]
    assert len({item.age_years_at_genesis for item in siblings} | {6}) == 3

    shared_children = {"self", "family-sibling-1", "family-sibling-2"}
    assert all(shared_children <= set(item.related_person_ids) for item in parents)
    assert all(
        {"self", "family-parent-1", "family-parent-2"} <= set(item.related_person_ids)
        for item in siblings
    )
    assert compilation.bundle.validate() is None


def test_compiler_expands_only_bounded_parent_ancestor_branches() -> None:
    source = load_genesis_source_package()
    source = replace(
        source,
        generation_policy=replace(
            source.generation_policy,
            family_child_count_distribution=((3, 1.0),),
            family_partner_annual_probability=0.0,
        ),
    )
    compilation = _compilation(
        "family-bounded-ancestors",
        species_id="dog",
        stage="mature",
        age_years=7,
        seed=7,
        source=source,
    )
    relationships = compilation.bundle.relationship_seeds
    grandparents = tuple(item for item in relationships if item.role == "grandparent")
    aunts_uncles = tuple(item for item in relationships if item.role == "aunt_uncle")

    assert len(grandparents) == 4
    assert len(aunts_uncles) == 4
    assert not any(
        item.role in {"great_grandparent", "cousin", "grandchild"}
        for item in relationships
    )
    assert all("self" in item.related_person_ids for item in grandparents)
    assert all("self" in item.related_person_ids for item in aunts_uncles)
    parent_ids = {item.person_id for item in relationships if item.role == "parent"}
    assert all(
        parent_ids & set(item.related_person_ids)
        for item in grandparents + aunts_uncles
    )
    assert compilation.bundle.validate() is None


def test_compiler_emits_lived_family_timeline_events_only_after_birth() -> None:
    source = load_genesis_source_package()
    source = replace(
        source,
        generation_policy=replace(
            source.generation_policy,
            family_child_count_distribution=((3, 1.0),),
            family_partner_annual_probability=1.0,
        ),
    )
    compilation = _compilation(
        "family-timeline",
        stage="mature",
        age_years=6,
        seed=7,
        source=source,
    )
    relationships = {
        item.person_id: item for item in compilation.bundle.relationship_seeds
    }
    family_episodes = tuple(
        episode
        for episode in compilation.bundle.episode_seeds
        if episode.theme_id.startswith("family-event:")
    )

    assert family_episodes
    assert all(1 <= episode.age_years_at_event <= 6 for episode in family_episodes)
    assert all(
        episode.person_ids and episode.person_ids[0] in relationships
        for episode in family_episodes
    )
    assert all(
        episode.place_ids == (compilation.life_context.origin.childhood_home_place_id,)
        for episode in family_episodes
    )
    assert len({episode.seed_id for episode in family_episodes}) == len(family_episodes)
    assert compilation.bundle.validate() is None


def test_compiler_turns_sampled_visit_opportunities_into_episodes() -> None:
    compilation = _compilation("visit-opportunity", seed=7, stage="mature", age_years=8)
    records = compilation.life_context.mobility.opportunity_records
    episodes = {
        episode.seed_id: episode
        for episode in compilation.bundle.episode_seeds
        if episode.seed_id.startswith("visit:")
    }

    assert any(record[0] == "town_center" for record in records)
    assert set(episodes) == {f"visit:{record[0]}" for record in records}
    assert all(episode.visit_count >= 1 for episode in episodes.values())
    assert all(episode.stay_days >= 1 for episode in episodes.values())
    assert all(episode.purposes for episode in episodes.values())
    assert "earthbound_station" in compilation.life_context.mobility.visited_place_ids
    station_only = _compilation("station-only")
    assert "earthbound_station" in station_only.life_context.mobility.visited_place_ids
    assert (
        "mistyville_center" not in station_only.life_context.mobility.visited_place_ids
    )


def test_visit_distance_uses_round_trip_legal_route_cost() -> None:
    source = load_genesis_source_package()
    compiler = GenesisCompiler(source, catalog=load_and_configure_species_catalog())

    assert (
        compiler._opportunity_distance_days("u-r04-c09", ("mistyville_center",)) == 24
    )
    assert compiler._opportunity_distance_days("u-r04-c09", ("firstroot_tree",)) == 8
    assert compiler._opportunity_distance_days("u-r04-c09", ("lakeheart_isle",)) == 54
    assert (
        compiler._opportunity_distance_days(
            "u-r04-c09", ("clearheart_lake", "lake_shore", "lakeheart_isle")
        )
        == 32
    )


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
