from devtools.evals.opt001_e2e3 import (
    _compilation,
    _eligible_for_species,
    _query_cases_for_bundle,
    _query_cases_for_species,
)
from elfie.genesis import GenesisCompiler
from infrastructure.persistence.configuration.species import (
    load_and_configure_species_catalog,
)
from infrastructure.persistence.configuration.world import load_genesis_source_package


def test_opt001_e2_queries_are_scoped_to_species_and_cover_the_gate() -> None:
    world = load_genesis_source_package()
    fox_cases = _query_cases_for_species(world.knowledge, "fox")
    dog_cases = _query_cases_for_species(world.knowledge, "dog")

    assert len(fox_cases) == 96
    assert len(dog_cases) == 96
    assert all(_eligible_for_species(fact, "fox") for fact, _ in fox_cases)
    assert all(_eligible_for_species(fact, "dog") for fact, _ in dog_cases)
    assert not any(fact.fact_id == "species.tovren_group" for fact, _ in fox_cases)
    assert not any(fact.fact_id == "species.saevi_paths" for fact, _ in dog_cases)
    eligible_fox_ids = {
        fact.fact_id
        for fact in world.knowledge
        if fact.status == "active"
        and ("all" in fact.eligibility or "fox" in fact.eligibility)
    }
    eligible_dog_ids = {
        fact.fact_id
        for fact in world.knowledge
        if fact.status == "active"
        and ("all" in fact.eligibility or "dog" in fact.eligibility)
    }
    fox_ids = {fact.fact_id for fact, _ in fox_cases}
    dog_ids = {fact.fact_id for fact, _ in dog_cases}
    assert fox_ids <= eligible_fox_ids
    assert dog_ids <= eligible_dog_ids
    assert len(fox_ids) == min(96, len(eligible_fox_ids))
    assert len(dog_ids) == min(96, len(eligible_dog_ids))


def test_opt001_compilation_retries_a_rejected_genesis_seed() -> None:
    world = load_genesis_source_package()
    catalog = load_and_configure_species_catalog()
    compilation = _compilation(
        GenesisCompiler(world, catalog=catalog),
        catalog,
        "opt001-retry-fox-mature-47",
        "fox",
        47,
        "mature",
    )

    assert compilation.bundle.profile_draft.profile.identity.species_id == "fox"
    assert compilation.bundle.manifest.status == "validated"


def test_opt001_e2_queries_are_scoped_to_the_compiled_knowledge() -> None:
    world = load_genesis_source_package()
    catalog = load_and_configure_species_catalog()
    compilation = _compilation(
        GenesisCompiler(world, catalog=catalog),
        catalog,
        "99010011",
        "fox",
        11,
        "youth",
    )

    cases = _query_cases_for_bundle(world.knowledge, compilation.bundle, "fox")
    seeded_ids = {seed.seed_id for seed in compilation.bundle.knowledge_seeds}

    assert len(cases) == 96
    assert all(fact.fact_id in seeded_ids for fact, _ in cases)
