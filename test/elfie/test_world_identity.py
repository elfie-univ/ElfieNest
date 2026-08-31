from elfie import ElfieFactory
from elfie.factory import ElfieAssembly
from elfie.profile import create_visual_profile, list_species_definitions
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter


def test_supported_species_carry_canon_into_selfhood_and_memory_identity() -> None:
    for definition in list_species_definitions():
        species_id = definition.species_id
        canon_id = definition.canon_id
        species_name = definition.display_name
        elfie = ElfieFactory().assemble(
            ElfieAssembly(
                profile=create_visual_profile(
                    elfie_id=f"world-identity-{species_id}",
                    display_name="Lumi",
                    species_id=species_id,
                    seed=5,
                ),
                selfhood_seed={
                    "state_schema_version": 1,
                    "revision": 1,
                    "identity_core": {
                        "elfie_id": f"world-identity-{species_id}",
                        "display_name": "Lumi",
                        "species_id": species_id,
                        "species_name": species_name,
                        "home_world_id": "elfaria",
                        "home_world_name": "Elfaria",
                        "home_region_id": "north",
                        "home_region_name": "北境",
                        "earth_arrival_statement": "我被领养来到地球。",
                        "resident_role": "居民",
                    },
                    "adaptive_self": {
                        "big_five": {},
                    },
                },
                memory_store=SQLiteMemoryStoreAdapter.in_memory(),
            )
        )

        anchor = elfie.profile_anchor_snapshot()
        selfhood = elfie.selfhood_snapshot()
        assert (anchor.species_canon_id, anchor.species_name) == (
            canon_id,
            species_name,
        )
        assert (anchor.home_world_name, anchor.earth_home_name) == (
            "Elfaria",
            "ElfieNest",
        )
        assert species_name in selfhood.self_description
        assert "Elfaria" in selfhood.self_description
        assert selfhood.identity_facts
