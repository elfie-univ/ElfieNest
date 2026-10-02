from __future__ import annotations

import hashlib
import math
from collections import Counter
from dataclasses import replace

import pytest

from elfie.genesis import (
    GenesisBundle,
    GenesisCompileInput,
    GenesisCompiler,
    GenesisError,
    GenesisValidationError,
    genesis_content_hash,
)
from elfie.genesis.compiler import (
    _sample_conditioned_death_age,
    _sample_visit_count,
    _uniform_hash_subset,
    stage_for_age,
)
from elfie.genesis.contracts import validate_genesis_bundle
from elfie.genesis.world import GeographyAccessRule
from infrastructure.persistence.configuration.species import (
    load_and_configure_species_catalog,
)
from infrastructure.persistence.configuration.world import load_genesis_source_package
from infrastructure.persistence.memory.ontology_loader import load_core_memory_ontology


def _compilation(
    elfie_id: str = "genesis-check",
    *,
    species_id: str = "saevi",
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
    ontology = load_core_memory_ontology()
    for episode in bundle.episode_seeds:
        ontology.validate_episode_type(episode.event_kind)
    assert len(bundle.knowledge_seeds) >= 100
    facts = {fact.fact_id: fact.statement for fact in source.knowledge}
    assert all(seed.content == facts[seed.seed_id] for seed in bundle.knowledge_seeds)
    assert all(
        seed.summary_text
        and seed.summary_text.rstrip("…") in seed.content
        and len(seed.summary_text) <= 120
        for seed in bundle.knowledge_seeds
    )
    assert all(
        seed.acquired_age_years is not None
        and 1
        <= seed.acquired_age_years
        <= bundle.profile_draft.profile.identity.origin.age_years
        for seed in bundle.knowledge_seeds
    )
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
        len(bundle.place_seeds) == 51
    )  # Published places + Elfaria/private home + Earth/owner home/ElfieNest
    assert {place.place_id for place in source.places} <= {
        seed.place_id for seed in bundle.place_seeds
    }
    assert sum(seed.relation != "route_to" for seed in bundle.place_relation_seeds) == 7

    assert {
        (relation.subject_id, relation.relation, relation.object_id)
        for relation in bundle.place_relation_seeds
        if relation.relation != "route_to"
    } == {
        (relation.subject_id, relation.relation, relation.object_id)
        for relation in source.place_relations
    }
    assert "skyreach_square" not in compilation.life_context.mobility.visited_place_ids
    travel_paths = {
        path_id: (cells, days)
        for path_id, cells, days in compilation.life_context.mobility.travel_paths
    }
    station_path, station_days = travel_paths["birth_to_earthbound_station"]
    station_route = next(
        route for route in source.routes if route.route_id == "earthbound_road"
    )
    route_path = source.geography_network.shortest_land_path(
        source.geography_network.cell_for_place(station_route.from_place_id) or "",
        source.geography_network.cell_for_place(station_route.to_place_id) or "",
    )
    assert route_path is not None
    reverse_route_path = tuple(reversed(route_path))
    station_route_traversed = any(
        station_path[index : index + len(route_path)]
        in {route_path, reverse_route_path}
        for index in range(len(station_path) - len(route_path) + 1)
    )
    assert (
        "earthbound_road" in compilation.life_context.mobility.familiar_route_ids
    ) is station_route_traversed
    assert compilation.life_context.earth_transition.route_id == (
        "earthbound_road" if station_route_traversed else ""
    )
    assert station_path[0].startswith("R") and station_path[-1] == "R4C3"
    assert station_days == (len(station_path) - 1) * 2
    assert len(station_path) > 1
    place_importance = {seed.place_id: seed.importance for seed in bundle.place_seeds}
    assert place_importance["earthbound_station"] > place_importance["skyreach_square"]
    assert place_importance[f"private:{compilation.life_context.elfie_id}:home"] == 0.9
    departure_episode = next(
        episode
        for episode in bundle.episode_seeds
        if episode.theme_id == "departure-decision"
    )
    arrival_episode = next(
        episode
        for episode in bundle.episode_seeds
        if episode.theme_id == "arrival-nest"
    )
    assert departure_episode.route_ids == (
        GenesisCompiler(source)._registered_routes_on_path(station_path)
    )
    assert arrival_episode.route_ids == ()
    assert bundle.manifest.output_ids


def test_genesis_episode_seed_rejects_process_names_as_experience_types() -> None:
    bundle = _bundle()
    invalid_seed = replace(bundle.episode_seeds[0], event_kind="reset")
    invalid_bundle = replace(
        bundle,
        episode_seeds=(invalid_seed, *bundle.episode_seeds[1:]),
    )
    invalid_bundle = replace(
        invalid_bundle,
        manifest=replace(
            invalid_bundle.manifest,
            content_hash=genesis_content_hash(invalid_bundle),
        ),
    )

    with pytest.raises(GenesisValidationError, match="EpisodeSeed.event_kind"):
        validate_genesis_bundle(invalid_bundle, load_core_memory_ontology())


def test_station_route_familiarity_depends_on_the_registered_path() -> None:
    source = load_genesis_source_package()
    compiler = GenesisCompiler(source)

    assert compiler._registered_routes_on_path(("R5C4",)) == ()

    route_flags = {
        "earthbound_road"
        in compiler._registered_routes_on_path(
            compiler._land_path_to_place(cell.cell_id, "earthbound_station")
        )
        for cell in source.spatial_population.cells
    }

    assert route_flags == {False, True}


def test_trip_budget_includes_the_ferry_round_trip_to_lakeheart_isle() -> None:
    source = load_genesis_source_package()
    compiler = GenesisCompiler(source)
    opportunity = next(
        item
        for item in source.generation_policy.visit_opportunities
        if item.opportunity_id == "lake_group"
    )
    birth_cell = next(
        cell.cell_id
        for cell in source.spatial_population.cells
        if cell.region_id == "C1"
    )

    metrics = compiler._opportunity_trip_metrics(
        birth_cell, opportunity.place_ids, opportunity.stay_days
    )

    assert metrics is not None
    travel_days, total_days, _ = metrics
    assert travel_days >= 2 * source.geography_network.water_days_per_grid_hop
    assert total_days == travel_days + opportunity.stay_days


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
    assert all(
        (relationship.life_status == "deceased")
        == (relationship.death_age_years_at_genesis is not None)
        for relationship in family
    )
    assert all(
        relationship.age_years_at_genesis is not None
        if relationship.life_status == "alive"
        else relationship.age_years_at_genesis is None
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
    parents = tuple(item for item in family if item.role == "parent")
    assert all("self" in item.care_recipient_person_ids for item in parents)
    children = tuple(item for item in family if item.role == "child")
    assert all("self" in item.caregiver_person_ids for item in children)
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
    parent_child_orders = dict(parents[0].child_birth_orders)
    assert dict(parents[1].child_birth_orders) == parent_child_orders
    assert len(parent_child_orders) == 3
    assert set(parent_child_orders) == {"self", *(item.person_id for item in siblings)}
    assert set(parent_child_orders.values()) == {1, 2, 3}
    assert all(
        parent_child_orders[item.person_id] == item.birth_order for item in siblings
    )
    self_order = parent_child_orders["self"]
    for sibling in siblings:
        if sibling.age_years_at_genesis is not None:
            assert (sibling.birth_order < self_order) == (
                sibling.age_years_at_genesis > 6
            )
        assert sibling.birth_event_age_years == (
            6 - sibling.age_years_at_genesis
            if sibling.age_years_at_genesis is not None
            and sibling.age_years_at_genesis < 6
            else None
        )

    shared_children = {"self", "family-sibling-1", "family-sibling-2"}
    assert all(shared_children <= set(item.related_person_ids) for item in parents)
    assert all(
        {"self", "family-parent-1", "family-parent-2"} <= set(item.related_person_ids)
        for item in siblings
    )
    assert compilation.bundle.validate() is None


def test_genesis_contract_requires_parent_rank_in_shared_child_set() -> None:
    bundle = _compilation("missing-self-rank", stage="mature", age_years=6).bundle
    relationships = list(bundle.relationship_seeds)
    parent_index = next(
        index
        for index, relationship in enumerate(relationships)
        if relationship.role == "parent"
    )
    relationships[parent_index] = replace(
        relationships[parent_index], child_birth_orders=()
    )

    with pytest.raises(GenesisValidationError, match="共享子女集合与主角排行"):
        replace(bundle, relationship_seeds=tuple(relationships)).validate()


def test_child_birth_year_subsets_are_sampled_without_replacement_and_uniformly() -> (
    None
):
    counts: Counter[tuple[int, ...]] = Counter()
    values = (0, 1, 2, 3, 4)
    for seed in range(5000):
        counts[
            _uniform_hash_subset(
                values,
                2,
                lambda value, seed=seed: int.from_bytes(
                    hashlib.sha256(f"{seed}:{value}".encode()).digest()[:8],
                    "big",
                ),
            )
        ] += 1

    assert len(counts) == math.comb(len(values), 2)
    assert max(counts.values()) - min(counts.values()) < 100


def test_each_parent_union_draws_its_own_child_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_domain_seed = GenesisCompiler._domain_seed

    def controlled_family_seed(self, seed: int, label: str) -> int:
        if label == "family-child-count:parents":
            return 0  # Uniformly selects three children.
        if label == "family-child-count:partner":
            return 1  # Uniformly selects one child.
        return original_domain_seed(self, seed, label)

    monkeypatch.setattr(GenesisCompiler, "_domain_seed", controlled_family_seed)
    source = load_genesis_source_package()
    source = replace(
        source,
        generation_policy=replace(
            source.generation_policy,
            family_child_count_distribution=((1, 1 / 3), (2, 1 / 3), (3, 1 / 3)),
            family_partner_annual_probability=1.0,
        ),
    )
    compilation = _compilation(
        "family-independent-child-draws",
        source=source,
        stage="mature",
        age_years=8,
        seed=0,
    )

    sibling_count = sum(
        relationship.role == "sibling"
        for relationship in compilation.bundle.relationship_seeds
    )
    child_count = sum(
        relationship.role == "child"
        for relationship in compilation.bundle.relationship_seeds
    )

    assert sibling_count == 2
    assert child_count == 1


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
        species_id="tovren",
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


def test_elder_parents_do_not_force_grandparent_expansion() -> None:
    compilation = _compilation(
        "elder-parent-boundary",
        species_id="saevi",
        stage="mature",
        age_years=8,
        seed=7,
    )
    assert not any(
        relationship.role in {"grandparent", "aunt_uncle"}
        for relationship in compilation.bundle.relationship_seeds
    )


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
        episode.place_ids
        == (
            ()
            if episode.theme_id == "family-event:death"
            else (compilation.life_context.origin.childhood_home_place_id,)
        )
        for episode in family_episodes
    )
    assert all(
        not episode.predecessor_ids and not episode.causal_links
        for episode in family_episodes
    )
    for episode in family_episodes:
        if episode.theme_id != "family-event:death":
            continue
        person = relationships[episode.person_ids[0]]
        assert person.life_status == "deceased"
        assert episode.age_years_at_event == person.death_event_age_years
        assert "死因" in episode.content
    partnership_ages = [
        episode.age_years_at_event
        for episode in family_episodes
        if episode.theme_id == "family-event:partnership"
    ]
    child_birth_ages = [
        episode.age_years_at_event
        for episode in family_episodes
        if episode.theme_id == "family-event:child_birth"
    ]
    assert partnership_ages and child_birth_ages
    assert min(child_birth_ages) > max(partnership_ages)
    partner = next(item for item in relationships.values() if item.role == "partner")
    assert partner.relationship_start_age == partnership_ages[0]
    assert partner.age_years_at_genesis is not None
    assert (
        partner.age_years_at_genesis - (6 - partner.relationship_start_age)
        >= source.generation_policy.family_partner_min_age_years
    )
    assert len({episode.seed_id for episode in family_episodes}) == len(family_episodes)
    assert compilation.bundle.validate() is None


def test_elder_candidate_has_conditioned_death_records_and_lived_events() -> None:
    compilation = _compilation(
        "family-death-timeline",
        stage="elder",
        age_years=11,
        seed=7,
    )
    relationships = {
        item.person_id: item for item in compilation.bundle.relationship_seeds
    }
    parents = tuple(item for item in relationships.values() if item.role == "parent")
    death_episodes = tuple(
        episode
        for episode in compilation.bundle.episode_seeds
        if episode.theme_id == "family-event:death"
    )

    assert len(parents) == 2
    assert all(item.life_status == "deceased" for item in parents)
    assert all(item.age_years_at_genesis is None for item in parents)
    assert all(item.death_age_years_at_genesis is not None for item in parents)
    assert {episode.person_ids[0] for episode in death_episodes} == {
        item.person_id
        for item in relationships.values()
        if item.life_status == "deceased" and item.death_event_age_years is not None
    }
    assert all(1 <= episode.age_years_at_event <= 11 for episode in death_episodes)
    assert all(not episode.place_ids for episode in death_episodes)
    assert all("死因" in episode.content for episode in death_episodes)
    assert compilation.bundle.validate() is None


def test_compiler_turns_sampled_visit_opportunities_into_episodes(monkeypatch) -> None:
    # Fix the two sampling draws while retaining the real probability/count sampler.
    # Distance, age and personality still determine eligibility; a renamed species
    # must not turn this compilation test into a lucky-seed test.
    def controlled_visit_count(probability, maximum, power, **_draws):
        return _sample_visit_count(
            probability, maximum, power, visit_uniform=0.0, count_uniform=0.0625
        )

    monkeypatch.setattr(
        "elfie.genesis.compiler._sample_visit_count", controlled_visit_count
    )
    source = load_genesis_source_package()
    visit_opportunities = tuple(
        replace(
            opportunity,
            base_visit_probability=1.0
            if opportunity.opportunity_id == "town_center"
            else 0.0,
            base_visit_probabilities_by_region=(),
            home_regions=(),
            max_repeat_count=64,
            member_probability=1.0,
            member_probabilities=tuple(
                (place_id, 1.0) for place_id in opportunity.place_ids
            )
            if opportunity.opportunity_id == "town_center"
            else opportunity.member_probabilities,
        )
        for opportunity in source.generation_policy.visit_opportunities
    )
    source = replace(
        source,
        generation_policy=replace(
            source.generation_policy,
            visit_repeat_count_power=1.0,
            visit_opportunities=visit_opportunities,
        ),
    )
    compilation = _compilation(
        "visit-opportunity", seed=7, stage="mature", age_years=8, source=source
    )
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
    assert all(episode.travel_days >= 0 for episode in episodes.values())
    assert all(
        len(episode.visit_age_years) == episode.visit_count
        for episode in episodes.values()
    )
    assert all(
        all(1 <= age <= 8 for age in episode.visit_age_years)
        for episode in episodes.values()
    )
    assert all(
        episode.age_years_at_event == min(episode.visit_age_years)
        for episode in episodes.values()
    )
    compiler = GenesisCompiler(source, catalog=load_and_configure_species_catalog())
    visit_ages = dict(compilation.life_context.mobility.visit_age_years)
    remaining_by_age: dict[int, int] = {}
    cross_region_days = 0
    for opportunity_id, place_ids, count, _, stay_days in records:
        trip_days = compiler._opportunity_trip_days(
            compilation.life_context.origin.birth_cell_id, place_ids, stay_days
        )
        assert trip_days is not None
        episode = episodes[f"visit:{opportunity_id}"]
        metrics = compiler._opportunity_trip_metrics(
            compilation.life_context.origin.birth_cell_id, place_ids, stay_days
        )
        assert metrics is not None
        assert episode.travel_days == metrics[0]
        assert set(episode.route_ids) == set(metrics[2])
        ages = visit_ages[opportunity_id]
        assert len(ages) == count
        for age in ages:
            remaining_by_age[age] = remaining_by_age.get(age, 0) + trip_days
        if compiler._visit_crosses_macro_region(
            compilation.life_context.origin.birth_cell_id, place_ids
        ):
            cross_region_days += count * trip_days
    assert all(
        used <= source.geography_network.days_per_local_year
        for used in remaining_by_age.values()
    )
    assert cross_region_days <= (
        source.geography_network.days_per_local_year
        * (8 - 1)
        * source.generation_policy.visit_cross_region_lifetime_fraction
    )
    assert all(episode.purposes for episode in episodes.values())
    town_episode = episodes.get("visit:town_center")
    assert town_episode is not None
    assert town_episode.purposes[0] in {"探亲交往", "观光", "赶集交换"}
    town_record = next(record for record in records if record[0] == "town_center")
    town_place_ids = town_record[1]
    visit_counts = dict(compilation.life_context.mobility.visit_counts)
    assert town_record[2] > 1
    assert town_episode.visit_count == town_record[2]
    assert f"累计访问{town_record[2]}次" in town_episode.content
    assert "其中一次行程" in town_episode.content
    assert visit_counts[town_place_ids[0]] == town_record[2]
    assert all(visit_counts[place_id] == 1 for place_id in town_place_ids[1:])
    repeat = _compilation(
        "visit-opportunity-repeat",
        seed=7,
        stage="mature",
        age_years=8,
        source=source,
    )
    repeat_town = next(
        episode
        for episode in repeat.bundle.episode_seeds
        if episode.seed_id == "visit:town_center"
    )
    assert repeat_town.purposes == town_episode.purposes
    assert all(
        episode.source_version == "genesis-visit:visits-zero-heavy-power-count.v1"
        for episode in episodes.values()
    )
    assert "earthbound_station" in compilation.life_context.mobility.visited_place_ids
    station_only_source = replace(
        source,
        generation_policy=replace(
            source.generation_policy,
            visit_opportunities=tuple(
                replace(
                    opportunity,
                    base_visit_probability=0.0,
                    base_visit_probabilities_by_region=(),
                )
                for opportunity in source.generation_policy.visit_opportunities
            ),
        ),
    )
    station_only = _compilation("station-only", source=station_only_source)
    assert "earthbound_station" in station_only.life_context.mobility.visited_place_ids
    assert (
        "mistyville_center" not in station_only.life_context.mobility.visited_place_ids
    )

    town_trip_days = compiler._opportunity_trip_days(
        compilation.life_context.origin.birth_cell_id,
        town_place_ids,
        town_episode.stay_days,
    )
    assert town_trip_days is not None
    constrained_source = replace(
        source,
        geography_network=replace(
            source.geography_network,
            days_per_local_year=town_trip_days,
        ),
    )
    constrained = _compilation(
        "visit-opportunity-constrained",
        seed=7,
        stage="mature",
        age_years=8,
        source=constrained_source,
    )
    assert constrained.life_context.mobility.unmade_opportunity_records
    town_requested_count = sum(
        record[2]
        for record in constrained.life_context.mobility.opportunity_records
        if record[0] == "town_center"
    ) + sum(
        count
        for opportunity_id, count, _ in constrained.life_context.mobility.unmade_opportunity_records
        if opportunity_id == "town_center"
    )
    town_actual_count = sum(
        record[2]
        for record in constrained.life_context.mobility.opportunity_records
        if record[0] == "town_center"
    )
    assert 0 < town_actual_count < town_requested_count
    assert any(
        opportunity_id == "town_center" and "历法上限" in reason
        for opportunity_id, _, reason in constrained.life_context.mobility.unmade_opportunity_records
    )
    constrained_visit_ages = dict(constrained.life_context.mobility.visit_age_years)
    town_ages = constrained_visit_ages.get("town_center", ())
    assert all(town_ages.count(age) <= 1 for age in set(town_ages))


def test_visit_count_has_a_large_zero_mass_and_a_steep_repeat_tail() -> None:
    samples = 20_000
    counts = tuple(
        _sample_visit_count(
            probability=0.1,
            maximum=100,
            power=23.0,
            visit_uniform=(index + 0.5) / samples,
            count_uniform=((index * 7_919) % samples + 0.5) / samples,
        )
        for index in range(samples)
    )

    assert counts.count(0) / samples == pytest.approx(0.9, abs=0.001)
    assert sum(count >= 10 for count in counts) / samples == pytest.approx(
        0.01, abs=0.002
    )
    assert max(counts) == 100
    assert all(0 <= count <= 100 for count in counts)


def test_visit_presence_and_repeat_count_use_independent_random_domains() -> None:
    compiler = GenesisCompiler(load_genesis_source_package())

    presence = compiler._domain_uniform(17, "visit-presence:town_center")
    repeat_count = compiler._domain_uniform(17, "visit-repeat-count:town_center")

    assert presence != repeat_count


def test_conditioned_lifespan_sample_obeys_survival_anchor_and_source_curve() -> None:
    samples = 10_000
    death_ages = tuple(
        _sample_conditioned_death_age(
            terminal_age=20,
            minimum_survival_age=10,
            cdf_power=6,
            uniform=(index + 0.5) / samples,
        )
        for index in range(samples)
    )
    expected_by_15 = ((15 / 20) ** 6 - (10 / 20) ** 6) / (1.0 - (10 / 20) ** 6)

    assert min(death_ages) >= 11
    assert max(death_ages) <= 20
    assert sum(age <= 15 for age in death_ages) / samples == pytest.approx(
        expected_by_15, abs=0.001
    )


def test_residence_and_planned_learning_places_are_not_recorded_as_visits() -> None:
    source = load_genesis_source_package()
    opportunities = tuple(
        replace(item, base_visit_probability=0.0, base_visit_probabilities_by_region=())
        for item in source.generation_policy.visit_opportunities
    )
    source = replace(
        source,
        generation_policy=replace(
            source.generation_policy,
            visit_opportunities=opportunities,
        ),
    )
    compilation = _compilation("residence-is-not-visit", source=source)

    assert compilation.life_context.mobility.visited_place_ids == (
        "earthbound_station",
    )
    assert (
        "learning_healing_hall"
        not in compilation.life_context.mobility.visited_place_ids
    )
    birth_cell = next(
        cell
        for cell in source.spatial_population.cells
        if cell.cell_id == compilation.life_context.origin.birth_cell_id
    )
    assert compilation.life_context.origin.birth_region_id == birth_cell.region_id
    assert compilation.life_context.origin.birth_settlement_id == birth_cell.place_id


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


def test_observation_only_landmarks_do_not_become_entered_visits() -> None:
    source = load_genesis_source_package()
    catalog = load_and_configure_species_catalog()
    compiler = GenesisCompiler(source, catalog=catalog)
    base = _compilation("observation-only", seed=7, stage="mature", age_years=8)
    mobility = replace(
        base.life_context.mobility,
        opportunity_records=(
            ("mountain_attraction", ("cloudcrown_city",), 1, "mountain_sightseeing", 1),
        ),
        visit_age_years=(("mountain_attraction", (4,)),),
    )
    episode = compiler._visit_episodes(replace(base.life_context, mobility=mobility))[0]

    assert episode.place_ids == ()
    assert episode.observed_place_ids == ("cloudcrown_city",)


def test_restricted_places_are_not_silently_sampled_as_ordinary_visits() -> None:
    source = load_genesis_source_package()
    source = replace(
        source,
        access_rules=(
            *source.access_rules,
            GeographyAccessRule(
                rule_id="review-only-square",
                place_id="skyreach_square",
                ordinary_travel_allowed=False,
            ),
        ),
    )

    compilation = _compilation(
        "restricted-place",
        seed=7,
        stage="mature",
        age_years=8,
        source=source,
    )

    assert "skyreach_square" not in compilation.life_context.mobility.visited_place_ids
    assert all(
        "skyreach_square" not in place_ids
        for _, place_ids, *_ in compilation.life_context.mobility.opportunity_records
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


def test_learning_theme_requires_actual_vocation_evidence() -> None:
    source = load_genesis_source_package()
    compiler = GenesisCompiler(source, catalog=load_and_configure_species_catalog())
    compilation = _compilation(
        "ordinary-household-learning", stage="mature", age_years=8
    )

    ordinary_themes = compiler._eligible_episode_themes(compilation.life_context)
    assert compilation.life_context.vocation.vocation_id == ""
    assert "learning-path" not in {theme.theme_id for theme in ordinary_themes}
    assert "learning-path" not in {
        episode.theme_id for episode in compilation.bundle.episode_seeds
    }
    assert all(
        relationship.role != "teacher"
        for relationship in compilation.bundle.relationship_seeds
    )

    qualified_context = replace(
        compilation.life_context,
        vocation=replace(
            compilation.life_context.vocation,
            vocation_id="craftsperson",
            workplace_place_id="hundred_trades_street",
        ),
    )
    qualified_themes = compiler._eligible_episode_themes(qualified_context)
    assert "learning-path" in {theme.theme_id for theme in qualified_themes}


def test_age_is_directly_mapped_to_the_requested_earth_year() -> None:
    compilation = _compilation("age-elfie", stage="mature")

    assert compilation.life_context.identity.age_years_at_adoption == 6
    assert compilation.profile.identity.origin.age_years == 6
    assert all(
        episode.age_years_at_event is None or 1 <= episode.age_years_at_event <= 6
        for episode in compilation.bundle.episode_seeds
    )
    assert (
        next(
            episode
            for episode in compilation.bundle.episode_seeds
            if episode.theme_id == "departure-decision"
        ).age_years_at_event
        is None
    )
    assert (
        next(
            episode
            for episode in compilation.bundle.episode_seeds
            if episode.theme_id == "arrival-nest"
        ).age_years_at_event
        == 6
    )


def test_transition_episodes_use_actual_facts_without_template_events() -> None:
    compilation = _compilation("transition-episodes", stage="mature", age_years=6)
    source = load_genesis_source_package()
    episodes = compilation.bundle.episode_seeds
    departure = next(item for item in episodes if item.theme_id == "departure-decision")
    training = next(
        item for item in episodes if item.theme_id == "predeparture-training"
    )
    arrival = next(item for item in episodes if item.theme_id == "arrival-nest")
    travel_paths = {
        path_id: (cells, days)
        for path_id, cells, days in compilation.life_context.mobility.travel_paths
    }

    assert departure.age_years_at_event is None
    assert departure.temporal_label.startswith("赴地准备后、抵达新家前")
    assert training.stay_days == 3
    assert "earthbound_station" in departure.place_ids
    assert departure.travel_days == travel_paths["birth_to_earthbound_station"][1]
    assert arrival.age_years_at_event == 6
    assert arrival.place_ids == ("elfie_nest",)
    assert arrival.person_ids
    assert all(
        not any(
            prompt in episode.content
            for theme in source.episode_themes
            for prompt in (theme.goal, theme.obstacle, theme.outcome)
            if prompt
        )
        for episode in episodes
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
        replace(fact, eligibility=("tovren",)) if fact.fact_id == required_id else fact
        for fact in source.knowledge
    )
    invalid_source = replace(source, knowledge=invalid_facts)

    with pytest.raises(GenesisError, match="赴地必修知识"):
        _compilation("unavailable-arrival-fact", source=invalid_source)


def test_relationship_importance_policy_is_consumed_by_family_compiler() -> None:
    source = load_genesis_source_package()
    policy = replace(
        source.generation_policy,
        relationship_importance_baselines=(
            ("core", 0.61),
            ("direct_acquaintance", 0.21),
            ("friend", 0.31),
            ("sibling", 0.52),
            ("teacher", 0.41),
        ),
        relationship_layer_decay_lambda=0.7,
    )
    compilation = _compilation(
        "configured-importance",
        source=replace(source, generation_policy=policy),
        stage="mature",
        age_years=6,
    )
    relationships = compilation.bundle.relationship_seeds
    parents = [item for item in relationships if item.role == "parent"]
    siblings = [item for item in relationships if item.role == "sibling"]
    grandparents = [item for item in relationships if item.role == "grandparent"]

    assert parents and all(item.importance == pytest.approx(0.61) for item in parents)
    assert siblings and all(item.importance == pytest.approx(0.52) for item in siblings)
    assert grandparents and all(
        item.importance == pytest.approx(0.61 * math.exp(-0.7)) for item in grandparents
    )
