"""Resident catalog coverage for real Elfie profile projection."""

from app.orchestration.nest_session.residents import actor_catalog
from elfie import ElfieFactory
from elfie.factory import ElfieAssembly
from elfie.profile import create_visual_profile
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter


def test_actor_catalog_resolves_real_elfie_profiles_for_each_species() -> None:
    with (
        SQLiteMemoryStoreAdapter.in_memory() as fox_memory,
        SQLiteMemoryStoreAdapter.in_memory() as dog_memory,
    ):
        fox = ElfieFactory().create(
            ElfieAssembly(
                profile=create_visual_profile(
                    elfie_id="fox-catalog",
                    display_name="小狐",
                    species_id="fox",
                    seed=101,
                ),
                memory_store=fox_memory,
            )
        )
        dog = ElfieFactory().create(
            ElfieAssembly(
                profile=create_visual_profile(
                    elfie_id="dog-catalog",
                    display_name="小狗",
                    species_id="dog",
                    seed=202,
                ),
                memory_store=dog_memory,
            )
        )

        descriptors = {
            descriptor.actor_id: descriptor
            for descriptor in actor_catalog({"fox-catalog": fox, "dog-catalog": dog})
        }

    assert descriptors["fox-catalog"].species == "fox"
    assert descriptors["dog-catalog"].species == "dog"
    assert descriptors["fox-catalog"].appearance["species_id"] == "fox"
    assert descriptors["dog-catalog"].appearance["species_id"] == "dog"
    assert descriptors["fox-catalog"].appearance["height_scale"] > 0
    assert descriptors["dog-catalog"].appearance["height_scale"] > 0
