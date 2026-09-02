from elfie import ElfieFactory
from elfie.factory import ElfieAssembly
from elfie.profile import create_visual_profile, list_species_definitions
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter


def test_supported_species_identity_is_scoped_to_profile_and_selfhood() -> None:
    for definition in list_species_definitions():
        species_id = definition.species_id
        elfie_id = f"world-identity-{species_id}"
        profile = create_visual_profile(
            elfie_id=elfie_id,
            display_name="Lumi",
            species_id=species_id,
            seed=5,
        )
        elfie = ElfieFactory().assemble(
            ElfieAssembly(
                profile=profile,
                selfhood_seed={
                    "state_schema_version": 1,
                    "revision": 1,
                    "identity_core": {
                        "elfie_id": elfie_id,
                        "display_name": "Lumi",
                        "species_id": species_id,
                        "species_name": definition.display_name,
                        "resident_role": "居民",
                    },
                    "adaptive_self": {"big_five": {}},
                },
                memory_store=SQLiteMemoryStoreAdapter.in_memory(elfie_id=elfie_id),
            )
        )

        assert elfie.profile.identity.species_id == species_id
        assert (
            elfie.selfhood_snapshot().identity_core.species_name
            == definition.display_name
        )
        assert elfie.profile.identity.origin.origin_place_id == "unknown-origin"
