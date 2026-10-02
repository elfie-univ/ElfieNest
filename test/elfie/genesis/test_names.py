"""Whole-case names remain lexical, unique, and deterministically allocated."""

from dataclasses import replace

import pytest

from elfie.genesis.compiler import _domain_seed
from elfie.genesis.names import allocate_person_names
from elfie.genesis.world import NameRules
from infrastructure.persistence.configuration.world import load_genesis_source_package


@pytest.fixture(scope="module")
def source():
    return load_genesis_source_package()


def test_sixty_people_receive_distinct_configured_names_without_suffixes(source):
    persons = tuple((f"person:{index}", "saevi") for index in range(60))
    allocated = allocate_person_names(source, 23, persons, seed_for=_domain_seed)
    assert len(allocated) == len(set(allocated.values())) == 60
    configured = set(source.name_rules.default_names + source.name_rules.pool("saevi"))
    assert set(allocated.values()) <= configured
    assert all(not any(char.isdigit() for char in name) for name in allocated.values())


def test_replay_does_not_depend_on_traversal_order(source):
    persons = tuple((f"person:{index}", "saevi") for index in range(60))
    first = allocate_person_names(source, 23, persons, seed_for=_domain_seed)
    replay = allocate_person_names(source, 23, reversed(persons), seed_for=_domain_seed)
    assert first == replay
    assert first != allocate_person_names(source, 7, persons, seed_for=_domain_seed)


def test_mixed_species_share_one_global_name_namespace(source):
    species = ("saevi", "Tovren", "myelle", "Saevi", "tovren", "Myelle")
    persons = tuple(
        (f"person:{index}", species[index % len(species)]) for index in range(60)
    )
    allocated = allocate_person_names(source, 23, persons, seed_for=_domain_seed)
    assert len(set(allocated.values())) == 60


@pytest.mark.parametrize(
    "technical,formal", [("saevi", "Saevi"), ("tovren", "Tovren"), ("myelle", "Myelle")]
)
def test_formal_and_technical_species_keys_share_name_allocation(
    source, technical, formal
):
    technical_names = allocate_person_names(
        source, 23, (("person:one", technical),), seed_for=_domain_seed
    )
    formal_names = allocate_person_names(
        source, 23, (("person:one", formal),), seed_for=_domain_seed
    )
    assert technical_names == formal_names


def test_reserved_name_is_never_given_to_a_contact(source):
    persons = (("person:one", "saevi"), ("person:two", "tovren"))
    original = allocate_person_names(source, 23, persons, seed_for=_domain_seed)
    reserved = tuple(original.values())
    actual = allocate_person_names(source, 23, persons, reserved, seed_for=_domain_seed)
    assert set(actual.values()).isdisjoint(reserved)
    assert len(set(actual.values())) == 2


def test_repeated_identity_uses_one_name_and_rejects_conflicting_species(source):
    actual = allocate_person_names(
        source,
        23,
        (("person:one", "saevi"), ("person:one", "Saevi")),
        seed_for=_domain_seed,
    )
    assert len(actual) == 1
    with pytest.raises(ValueError, match="物种不一致"):
        allocate_person_names(
            source,
            23,
            (("person:one", "saevi"), ("person:one", "tovren")),
            seed_for=_domain_seed,
        )


def test_exhausted_lexicon_fails_without_manufacturing_a_name(source):
    small = replace(source, name_rules=NameRules(default_names=("Nemi",)))
    with pytest.raises(ValueError, match="姓名词库不足"):
        allocate_person_names(
            small, 23, (("one", "saevi"), ("two", "saevi")), seed_for=_domain_seed
        )
