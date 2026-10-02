"""Independent checks for the core-family slice, including anchored children."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from functools import lru_cache

import pytest

from elfie.genesis.family import FamilyGenerator, FamilyGroup, FamilyPerson, FamilyUnion
from elfie.genesis.family_config import PartnerAgeGapConfig
from elfie.genesis.world import GenerationPolicy
from elfie.profile import SpeciesGenesisProfile
from infrastructure.persistence.configuration.species import (
    load_and_configure_species_catalog,
)

# Published half-open stage boundaries; these are the biological family gates.
MATURE_START = {"dog": 6, "fox": 5}
ELDER_START = {"dog": 14, "fox": 10}


@lru_cache(maxsize=2)
def species_genesis(species: str) -> SpeciesGenesisProfile:
    genesis = load_and_configure_species_catalog().definition(species).genesis
    assert genesis is not None
    return genesis


def generator(
    species: str = "dog", seed: int = 1, **overrides: object
) -> FamilyGenerator:
    genesis = species_genesis(species)
    family = GenerationPolicy().family
    marriage = family.marriage
    children = family.children
    if "never_married_probability" in overrides:
        marriage = replace(
            marriage,
            never_married_probability=overrides.pop("never_married_probability"),
        )
    if "child_count_distribution" in overrides:
        children = replace(
            children,
            count_distribution=overrides.pop("child_count_distribution"),
        )
    family = replace(family, marriage=marriage, children=children)
    policy = replace(GenerationPolicy(), family=family, **overrides)

    def seed_for(label: str) -> int:
        return int.from_bytes(
            hashlib.blake2b(f"{seed}:{label}".encode(), digest_size=8).digest(), "big"
        )

    return FamilyGenerator(
        species_id=species, genesis=genesis, policy=policy, seed_for=seed_for
    )


def person(
    age: int, species: str = "dog", gender: str = "male", ident: str = "self"
) -> FamilyPerson:
    return FamilyPerson(
        person_id=ident, species_id=species, gender=gender, birth_year=-age
    )


def assert_group(group: FamilyGroup, species: str) -> None:
    union = group.union
    parents = (union.first, union.second)
    assert parents[0].person_id != parents[1].person_id
    assert {parent.species_id for parent in parents} == {species}
    assert {parent.gender for parent in parents} == {"male", "female"}
    for parent in parents:
        assert union.formed_year - parent.birth_year >= MATURE_START[species]
        assert parent.death_year is None or union.formed_year < parent.death_year
    assert len(group.children) <= 3
    assert len({child.person_id for child in group.children}) == len(group.children)
    assert len({child.birth_year for child in group.children}) == len(group.children)
    assert [child.birth_year for child in group.children] == sorted(
        child.birth_year for child in group.children
    )
    for child in group.children:
        assert child.species_id == species
        assert child.birth_year <= 0
        assert child.birth_year >= union.formed_year + 1
        assert child.person_id not in {parent.person_id for parent in parents}
        for parent in parents:
            age_at_birth = child.birth_year - parent.birth_year
            assert MATURE_START[species] <= age_at_birth < ELDER_START[species]
            assert parent.death_year is None or child.birth_year < parent.death_year
        assert child.death_year is None or child.death_year >= child.birth_year


@pytest.mark.parametrize(
    "species,ages", [("dog", (2, 6, 14, 16)), ("fox", (2, 5, 10, 11))]
)
@pytest.mark.parametrize("gender", ["female", "male"])
def test_core_family_preserves_anchor_and_all_time_invariants(
    species: str, ages: tuple, gender: str
) -> None:
    for age in ages:
        for seed in range(12):
            subject = person(age, species, gender)
            first = generator(species, seed).generate_core_family(subject)
            assert first.protagonist == subject
            assert [
                child for child in first.origin.children if child.person_id == "self"
            ] == [subject]
            assert_group(first.origin, species)
            if first.own is not None:
                assert subject in (first.own.union.first, first.own.union.second)
                assert_group(first.own, species)
                origin_ids = {
                    p.person_id
                    for p in (
                        *first.origin.children,
                        first.origin.union.first,
                        first.origin.union.second,
                    )
                }
                own_new_ids = {
                    p.person_id
                    for p in (
                        first.own.union.first,
                        first.own.union.second,
                        *first.own.children,
                    )
                } - {"self"}
                assert origin_ids.isdisjoint(own_new_ids)
            assert first == generator(species, seed).generate_core_family(subject)


def test_family_graph_wraps_core_and_bounded_ancestor_families() -> None:
    subject = person(8)
    first = generator(seed=7).generate_family_graph(subject)
    second = generator(seed=7).generate_family_graph(subject)

    assert first == second
    assert first.core.protagonist == subject
    parent_ids = {
        first.core.origin.union.first.person_id,
        first.core.origin.union.second.person_id,
    }
    assert len(first.ancestor_families) <= 2
    assert {branch.anchor.person_id for branch in first.ancestor_families} <= parent_ids
    for branch in first.ancestor_families:
        assert branch.anchor in branch.group.children
        assert_group(branch.group, "dog")


def test_family_graph_adds_one_terminal_partner_origin_only_when_married() -> None:
    married = generator(seed=3, never_married_probability=0.0).generate_family_graph(
        person(16)
    )
    assert married.core.own is not None
    assert married.partner_origin is not None
    partner = (
        married.core.own.union.second
        if married.core.own.union.first.person_id == married.core.protagonist.person_id
        else married.core.own.union.first
    )
    assert married.partner_origin.anchor == partner
    assert partner in married.partner_origin.group.children
    assert_group(married.partner_origin.group, "dog")

    unmarried = generator(seed=3, never_married_probability=1.0).generate_family_graph(
        person(16)
    )
    assert unmarried.core.own is None
    assert unmarried.partner_origin is None


def test_family_graph_expands_role_bounded_side_and_descendant_branches() -> None:
    base = generator(
        seed=0,
        never_married_probability=0.0,
        child_count_distribution=((3, 1.0),),
    )
    family = replace(
        base.policy.family,
        ancestor_expansion=replace(
            base.policy.family.ancestor_expansion,
            stop_at_elder=False,
        ),
    )
    graph = FamilyGenerator(
        species_id=base.species_id,
        genesis=base.genesis,
        policy=replace(base.policy, family=family),
        seed_for=base.seed_for,
    ).generate_family_graph(person(8))

    assert graph.ancestor_families
    assert graph.sibling_families
    assert graph.aunt_uncle_families
    assert not graph.child_families
    for branch in (*graph.sibling_families, *graph.aunt_uncle_families):
        assert branch.anchor in (
            branch.group.union.first,
            branch.group.union.second,
        )
        assert_group(branch.group, "dog")
    terminal_ids = {
        child.person_id
        for branch in (
            *graph.sibling_families,
            *graph.aunt_uncle_families,
        )
        for child in branch.group.children
    }
    assert not terminal_ids & {
        branch.anchor.person_id
        for branch in (
            *graph.sibling_families,
            *graph.aunt_uncle_families,
        )
    }


def test_family_graph_expands_children_only_after_mature_gate() -> None:
    base = generator(
        seed=3,
        never_married_probability=0.0,
        child_count_distribution=((3, 1.0),),
    )
    mature_graph = base.generate_family_graph(person(16))
    young_graph = base.generate_family_graph(person(2))

    assert mature_graph.child_families
    assert all(
        -branch.anchor.birth_year >= MATURE_START["dog"]
        for branch in mature_graph.child_families
    )
    assert not young_graph.child_families


def test_family_graph_keeps_descendant_branches_when_upward_expansion_is_disabled() -> (
    None
):
    base = generator(
        seed=4,
        never_married_probability=0.0,
        child_count_distribution=((3, 1.0),),
    )
    family = replace(
        base.policy.family,
        ancestor_expansion=replace(
            base.policy.family.ancestor_expansion,
            max_upward_generations=0,
        ),
    )
    graph = FamilyGenerator(
        species_id=base.species_id,
        genesis=base.genesis,
        policy=replace(base.policy, family=family),
        seed_for=base.seed_for,
    ).generate_family_graph(person(16))

    assert not graph.ancestor_families
    assert graph.sibling_families
    assert graph.child_families
    assert not graph.aunt_uncle_families


def test_lifetime_unmarried_does_not_remove_required_parents() -> None:
    gen = generator(never_married_probability=1.0)
    subject = person(10)
    assert gen.generate_partner(subject, union_id="own", partner_id="partner") is None
    union = gen.generate_parents(subject)
    group = gen.generate_children(union, existing=(subject,))
    assert subject in group.children
    assert_group(group, "dog")


def test_zero_never_married_probability_is_paired_by_species_maximum_age() -> None:
    gen = generator(never_married_probability=0.0)
    assert (
        gen.generate_partner(person(2), union_id="young", partner_id="partner") is None
    )
    adult = person(17)
    union = gen.generate_partner(adult, union_id="own", partner_id="partner")
    assert union is not None
    assert (
        MATURE_START["dog"] <= union.formed_year - adult.birth_year < ELDER_START["dog"]
    )
    assert_group(gen.generate_children(union), "dog")


def test_parent_and_partner_ages_are_not_fixed_offsets() -> None:
    parent_gaps = set()
    partner_formation_ages = set()
    for seed in range(32):
        subject = person(17)
        gen = generator(seed=seed, never_married_probability=0.0)
        parents = gen.generate_parents(subject)
        parent_gaps.add(
            tuple(
                subject.birth_year - p.birth_year
                for p in (parents.first, parents.second)
            )
        )
        own = gen.generate_partner(subject, union_id="own", partner_id="partner")
        assert own is not None
        mate = own.second if own.first.person_id == "self" else own.first
        partner_formation_ages.add(own.formed_year - mate.birth_year)
    assert len(parent_gaps) > 1
    assert len(partner_formation_ages) > 1


@pytest.mark.parametrize("species,ages", [("dog", (2, 8, 14)), ("fox", (2, 8, 9))])
def test_parents_are_reverse_generated_from_child_lag_and_marriage_age(
    species: str, ages: tuple[int, ...]
) -> None:
    for age in ages:
        child = person(age, species)
        for seed in range(12):
            gen = generator(species, seed)
            parents = gen.generate_parents(child)
            lag = child.birth_year - parents.formed_year
            assert lag >= 1
            assert parents.formed_year < child.birth_year
            assert abs(parents.first.birth_year - parents.second.birth_year) <= 2
            for parent in (parents.first, parents.second):
                marriage_age = parents.formed_year - parent.birth_year
                age_at_child = child.birth_year - parent.birth_year
                assert MATURE_START[species] <= marriage_age < ELDER_START[species]
                assert gen._fertile(parent, child.birth_year)
                assert age_at_child == marriage_age + lag


def test_parent_generation_does_not_draw_the_sibling_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_: object, **__: object) -> int:
        raise AssertionError("父母生成不应抽取子女总数")

    monkeypatch.setattr(FamilyGenerator, "_draw_child_count", fail)
    parents = generator().generate_parents(person(8))
    assert parents.formed_year < 0


def test_parent_marriage_year_is_anchored_to_the_known_child_lag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    child = person(8)

    def choose_first(_: FamilyGenerator, __: str, candidates: tuple[int, ...]) -> int:
        assert 1 in candidates
        return 1

    monkeypatch.setattr(FamilyGenerator, "_sample_parent_child_lag", choose_first)
    parents = generator().generate_parents(child)
    assert parents.formed_year == child.birth_year - 1


def test_existing_child_is_preserved_and_completed_group_is_idempotent() -> None:
    gen = generator()
    subject = person(8)
    union = gen.generate_parents(subject)
    first = gen.generate_children(union, existing=(subject,))
    assert (
        next(p for p in first.children if p.person_id == subject.person_id) == subject
    )
    assert gen.generate_children(union, existing=first.children) == first


def test_just_formed_union_has_no_birth_window() -> None:
    union = FamilyUnion("new", person(6), person(6, gender="female", ident="mate"), 0)
    assert generator().generate_children(union).children == ()


@pytest.mark.parametrize("species", ["dog", "fox"])
def test_elder_boundary_cannot_be_used_as_birth_year(species: str) -> None:
    age = ELDER_START[species]
    union = FamilyUnion(
        "elder", person(age, species), person(age, species, "female", "mate"), -1
    )
    assert generator(species).generate_children(union).children == ()


@pytest.mark.parametrize(
    "children",
    [
        (
            FamilyPerson("bad", "dog", "male", -8),
        ),  # Before marriage / too young parents.
        (
            FamilyPerson("one", "dog", "male", -2),
            FamilyPerson("two", "dog", "female", -2),
        ),
        tuple(FamilyPerson(str(i), "dog", "male", -4 + i) for i in range(4)),
    ],
)
def test_invalid_anchored_children_fail_instead_of_being_deleted(
    children: tuple,
) -> None:
    union = FamilyUnion(
        "fixed", person(10), person(10, gender="female", ident="mate"), -4
    )
    with pytest.raises(ValueError):
        generator().generate_children(union, existing=children)


def test_birth_after_parent_death_is_excluded() -> None:
    father = replace(person(10), death_year=-2)
    mother = person(10, gender="female", ident="mate")
    union = FamilyUnion("fixed", father, mother, -4)
    for seed in range(12):
        group = generator(seed=seed).generate_children(union)
        assert_group(group, "dog")
        assert all(child.birth_year < -2 for child in group.children)


def test_existing_children_override_smaller_target_without_replacement() -> None:
    gen = generator(child_count_distribution=((1, 1.0),))
    union = FamilyUnion(
        "fixed", person(10), person(10, gender="female", ident="mate"), -4
    )
    children = (
        FamilyPerson("older", "dog", "male", -3),
        FamilyPerson("younger", "dog", "female", -1),
    )
    group = gen.generate_children(union, existing=children)
    assert group.children == children


def test_zero_child_target_is_a_valid_family_outcome() -> None:
    union = FamilyUnion(
        "childless", person(10), person(10, gender="female", ident="mate"), -4
    )
    assert (
        generator(child_count_distribution=((0, 1.0),))
        .generate_children(union)
        .children
        == ()
    )


def test_effective_fertility_years_use_both_parents_and_current_year() -> None:
    gen = generator()
    union = FamilyUnion(
        "window", person(12), person(10, gender="female", ident="mate"), -4
    )
    # Dog mature ages are [6, 14); the older father reaches age 14 in year 1,
    # while the present (year zero) cuts the shared window off at four years.
    assert gen._effective_fertility_years(union) == 4


def test_planned_births_are_truncated_by_effective_window_without_redrawing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    union = FamilyUnion(
        "truncate", person(10), person(10, gender="female", ident="mate"), -2
    )
    monkeypatch.setattr(
        FamilyGenerator,
        "_sample_child_lags",
        lambda self, sampled_union, occupied, count: (1, 3, 8),
    )
    group = generator(child_count_distribution=((3, 1.0),)).generate_children(union)
    assert [child.birth_year for child in group.children] == [-1]


def test_known_child_occupies_a_birth_year_before_remaining_sampling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    union = FamilyUnion(
        "anchor-first", person(10), person(10, gender="female", ident="mate"), -4
    )
    known = FamilyPerson("known", "dog", "female", -3)

    def sample(
        self: FamilyGenerator,
        sampled_union: FamilyUnion,
        occupied: set[int],
        count: int,
    ) -> tuple[int, ...]:
        assert sampled_union == union
        assert occupied == {1}
        assert count == 2
        return (2, 8)

    monkeypatch.setattr(FamilyGenerator, "_sample_child_lags", sample)
    group = generator(child_count_distribution=((3, 1.0),)).generate_children(
        union, existing=(known,)
    )
    assert [child.birth_year for child in group.children] == [-3, -2]
    assert group.children[0] == known
    assert group.children[1].gender in {"male", "female"}


@pytest.mark.parametrize("window", [1, 2, 3])
def test_target_three_children_is_limited_by_legal_year_capacity(window: int) -> None:
    gen = generator(child_count_distribution=((3, 1.0),))
    union = FamilyUnion(
        "fixed", person(10), person(10, gender="female", ident="mate"), -window
    )
    group = gen.generate_children(union)
    assert len(group.children) == window
    assert_group(group, "dog")


def test_partner_must_accommodate_anchored_birth_even_when_lifetime_unmarried() -> None:
    father = person(10)
    child = FamilyPerson("anchor", "dog", "female", -3)
    gen = generator(never_married_probability=1.0)
    union = gen.generate_partner(
        father,
        union_id="anchored",
        partner_id="mother",
        anchored_children=(child,),
        required=True,
    )
    assert union is not None
    group = gen.generate_children(union, existing=(child,))
    assert child in group.children
    assert_group(group, "dog")


def test_impossible_anchored_birth_does_not_change_given_parent() -> None:
    father = person(3)
    child = FamilyPerson("anchor", "dog", "female", -2)
    with pytest.raises(ValueError):
        generator().generate_partner(
            father,
            union_id="impossible",
            partner_id="mother",
            anchored_children=(child,),
            required=True,
        )


def test_same_sex_union_cannot_enter_biological_child_generator() -> None:
    union = FamilyUnion("invalid", person(8), person(8, ident="other"), -2)
    with pytest.raises(ValueError):
        generator().generate_children(union)


def test_generated_child_identity_cannot_collide_with_parent() -> None:
    union = FamilyUnion(
        "fixed",
        person(8, ident="family-child-1"),
        person(8, gender="female", ident="mate"),
        -2,
    )
    group = generator(child_count_distribution=((3, 1.0),)).generate_children(union)
    assert_group(group, "dog")


@pytest.mark.parametrize(
    "mother_id,father_id",
    [("self", "father"), ("mother", "self"), ("same", "same"), ("", "father")],
)
def test_parent_identities_must_be_distinct_valid_people(
    mother_id: str, father_id: str
) -> None:
    with pytest.raises(ValueError):
        generator().generate_parents(
            person(8), mother_id=mother_id, father_id=father_id
        )


def test_generated_partner_requires_a_nonempty_identity() -> None:
    with pytest.raises(ValueError):
        generator(never_married_probability=0.0).generate_partner(
            person(8), union_id="own", partner_id=""
        )


def test_currently_living_person_cannot_exceed_species_terminal_age() -> None:
    with pytest.raises(ValueError):
        generator().generate_core_family(person(23))


def test_all_generated_unions_respect_two_year_partner_gap() -> None:
    for species, age in (("dog", 14), ("fox", 10)):
        for seed in range(32):
            core = generator(species, seed).generate_core_family(person(age, species))
            unions = [core.origin.union]
            if core.own is not None:
                unions.append(core.own.union)
            for union in unions:
                assert abs(union.first.birth_year - union.second.birth_year) <= 2


def test_external_union_exceeding_two_year_gap_is_rejected() -> None:
    union = FamilyUnion(
        "wide", person(14), person(10, gender="female", ident="mate"), -4
    )
    with pytest.raises(ValueError):
        generator().generate_children(union)


def test_partner_sampling_consumes_configured_age_gap_weights() -> None:
    base = generator(never_married_probability=0.0)
    same_age_family = replace(
        base.policy.family,
        partner_age_gap=PartnerAgeGapConfig(
            offsets=(-2, -1, 0, 1, 2), weights=(0.0, 0.0, 1.0, 0.0, 0.0)
        ),
    )
    for seed in range(12):
        seeded = generator(seed=seed, never_married_probability=0.0)
        configured = FamilyGenerator(
            species_id="dog",
            genesis=seeded.genesis,
            policy=replace(seeded.policy, family=same_age_family),
            seed_for=seeded.seed_for,
        )
        subject = person(17)
        union = configured.generate_partner(subject, union_id="own", partner_id="mate")
        assert union is not None
        assert union.first.birth_year == union.second.birth_year


def test_child_generation_validates_against_configured_age_gaps() -> None:
    base = generator(seed=7, never_married_probability=0.0)
    family = replace(
        base.policy.family,
        marriage=replace(
            base.policy.family.marriage,
            peak_fraction=0.0,
            stddev_fraction=0.01,
        ),
        partner_age_gap=PartnerAgeGapConfig(offsets=(3,), weights=(1.0,)),
    )
    configured = FamilyGenerator(
        species_id="dog",
        genesis=base.genesis,
        policy=replace(base.policy, family=family),
        seed_for=base.seed_for,
    )
    union = configured.generate_partner(
        person(13), union_id="configured-gap", partner_id="mate"
    )
    assert union is not None
    assert abs(union.first.birth_year - union.second.birth_year) == 3
    configured.generate_children(union)


def test_never_married_probability_one_keeps_required_parents() -> None:
    gen = generator(never_married_probability=1.0)
    subject = person(14)
    assert gen.generate_partner(subject, union_id="own", partner_id="mate") is None
    parents = gen.generate_parents(subject)
    assert subject in gen.generate_children(parents, existing=(subject,)).children


def test_no_lifetime_unmarried_does_not_force_young_people_to_marry_now() -> None:
    observed = []
    for seed in range(128):
        gen = generator(seed=seed, never_married_probability=0.0)
        observed.append(
            gen.generate_partner(person(6), union_id="own", partner_id="mate")
        )
    assert any(union is None for union in observed)
    assert any(union is not None for union in observed)


def test_marriage_age_draw_does_not_change_with_current_age() -> None:
    for seed in range(64):
        older_gen = generator(seed=seed, never_married_probability=0.0)
        older = older_gen.generate_partner(
            person(17), union_id="own", partner_id="mate"
        )
        assert older is not None
        marriage_age = older.formed_year + 17
        assert MATURE_START["dog"] <= marriage_age < ELDER_START["dog"]
        for current_age in (5, 6, 8):
            younger = generator(
                seed=seed, never_married_probability=0.0
            ).generate_partner(person(current_age), union_id="own", partner_id="mate")
            if marriage_age > current_age:
                assert younger is None
            else:
                assert younger is not None
                assert younger.formed_year + current_age == marriage_age
                assert (
                    younger.formed_year - younger.second.birth_year
                    == older.formed_year - older.second.birth_year
                )


@pytest.mark.parametrize("species,maximum", [("dog", 13), ("fox", 9)])
def test_both_marriage_ages_are_within_species_window(
    species: str, maximum: int
) -> None:
    for seed in range(128):
        union = generator(
            species, seed, never_married_probability=0.0
        ).generate_partner(person(maximum, species), union_id="own", partner_id="mate")
        assert union is not None
        for partner in (union.first, union.second):
            assert (
                MATURE_START[species]
                <= union.formed_year - partner.birth_year
                <= maximum
            )


def test_discrete_marriage_age_matches_independent_bell_weights() -> None:
    import math
    from collections import Counter

    # Fixed before sampling: familywise alpha .001 over eight mature age bins.
    samples = 2048
    tolerance = math.sqrt(math.log(2 * 8 / 0.001) / (2 * samples))
    base = generator(never_married_probability=0.0)
    mature_start, mature_end = base.genesis.stage_ranges["mature"]
    marriage = base.policy.family.marriage
    peak = mature_start + (mature_end - mature_start - 1) * marriage.peak_fraction
    stddev = max(0.5, (mature_end - mature_start) * marriage.stddev_fraction)
    weights = {
        age: math.exp(-0.5 * ((age - peak) / stddev) ** 2)
        for age in range(mature_start, mature_end)
    }
    observed = Counter()
    for seed in range(samples):
        union = generator(seed=seed, never_married_probability=0.0).generate_partner(
            person(17), union_id="own", partner_id="mate"
        )
        assert union is not None
        observed[union.formed_year + 17] += 1
    assert set(observed) <= set(weights)
    for age, weight in weights.items():
        assert (
            abs(observed[age] / samples - weight / sum(weights.values())) <= tolerance
        )


def test_marriage_age_sampling_consumes_configured_curve_shape() -> None:
    base = generator(never_married_probability=0.0)
    for peak_fraction in (0.0, 1.0):
        marriage = replace(
            base.policy.family.marriage,
            peak_fraction=peak_fraction,
            stddev_fraction=0.01,
        )
        configured = FamilyGenerator(
            species_id="dog",
            genesis=base.genesis,
            policy=replace(
                base.policy,
                family=replace(base.policy.family, marriage=marriage),
            ),
            seed_for=base.seed_for,
        )
        union = configured.generate_partner(
            person(17), union_id="own", partner_id="mate"
        )
        assert union is not None
        observed = union.formed_year + 17
        expected = 6 if peak_fraction == 0.0 else 13
        assert observed == expected
        assert (
            MATURE_START["dog"]
            <= union.formed_year - union.second.birth_year
            < ELDER_START["dog"]
        )
