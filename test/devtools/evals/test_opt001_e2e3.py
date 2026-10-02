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
    saevi_cases = _query_cases_for_species(world.knowledge, "saevi")
    tovren_cases = _query_cases_for_species(world.knowledge, "tovren")

    assert len(saevi_cases) == 96
    assert len(tovren_cases) == 96
    assert all(_eligible_for_species(fact, "saevi") for fact, _ in saevi_cases)
    assert all(_eligible_for_species(fact, "tovren") for fact, _ in tovren_cases)
    assert not any(fact.fact_id == "species.tovren_group" for fact, _ in saevi_cases)
    assert not any(fact.fact_id == "species.saevi_paths" for fact, _ in tovren_cases)
    eligible_saevi_ids = {
        fact.fact_id
        for fact in world.knowledge
        if fact.status == "active"
        and (
            not fact.eligibility
            or "all" in fact.eligibility
            or "saevi" in fact.eligibility
        )
    }
    eligible_tovren_ids = {
        fact.fact_id
        for fact in world.knowledge
        if fact.status == "active"
        and (
            not fact.eligibility
            or "all" in fact.eligibility
            or "tovren" in fact.eligibility
        )
    }
    saevi_ids = {fact.fact_id for fact, _ in saevi_cases}
    tovren_ids = {fact.fact_id for fact, _ in tovren_cases}
    assert saevi_ids <= eligible_saevi_ids
    assert tovren_ids <= eligible_tovren_ids
    assert len(saevi_ids) == min(96, len(eligible_saevi_ids))
    assert len(tovren_ids) == min(96, len(eligible_tovren_ids))


def test_opt001_compilation_retries_a_rejected_genesis_seed() -> None:
    world = load_genesis_source_package()
    catalog = load_and_configure_species_catalog()
    compilation = _compilation(
        GenesisCompiler(world, catalog=catalog),
        catalog,
        "opt001-retry-saevi-mature-47",
        "saevi",
        47,
        "mature",
    )

    assert compilation.bundle.profile_draft.profile.identity.species_id == "saevi"
    assert compilation.bundle.manifest.status == "validated"


def test_opt001_e2_queries_are_scoped_to_the_compiled_knowledge() -> None:
    world = load_genesis_source_package()
    catalog = load_and_configure_species_catalog()
    compilation = _compilation(
        GenesisCompiler(world, catalog=catalog),
        catalog,
        "99010011",
        "saevi",
        11,
        "adolescent",
    )

    cases = _query_cases_for_bundle(world.knowledge, compilation.bundle, "saevi")
    seeded_ids = {seed.seed_id for seed in compilation.bundle.knowledge_seeds}

    assert len(cases) == 96
    assert all(fact.fact_id in seeded_ids for fact, _ in cases)
