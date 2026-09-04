from devtools.evals.opt001_e2e3 import (
    _eligible_for_species,
    _query_cases_for_species,
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
    assert {fact.fact_id for fact, _ in fox_cases} <= {
        fact.fact_id
        for fact in world.knowledge
        if fact.status == "active"
        and ("all" in fact.eligibility or "fox" in fact.eligibility)
    }
