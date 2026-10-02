"""Resident catalog coverage for real Elfie profile projection."""

from app.orchestration.nest_session.residents import actor_catalog
from elfie import ElfieFactory
from elfie.factory import ElfieAssembly
from elfie.profile import create_visual_profile
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter


def test_actor_catalog_resolves_real_elfie_profiles_for_each_species() -> None:
    with (
        SQLiteMemoryStoreAdapter.in_memory() as saevi_memory,
        SQLiteMemoryStoreAdapter.in_memory() as tovren_memory,
    ):
        saevi = ElfieFactory().create(
            ElfieAssembly(
                profile=create_visual_profile(
                    elfie_id="saevi-catalog",
                    display_name="小狐",
                    species_id="saevi",
                    seed=101,
                ),
                memory_store=saevi_memory,
            )
        )
        tovren = ElfieFactory().create(
            ElfieAssembly(
                profile=create_visual_profile(
                    elfie_id="tovren-catalog",
                    display_name="托伦",
                    species_id="tovren",
                    seed=202,
                ),
                memory_store=tovren_memory,
            )
        )

        descriptors = {
            descriptor.actor_id: descriptor
            for descriptor in actor_catalog(
                {"saevi-catalog": saevi, "tovren-catalog": tovren}
            )
        }

    assert descriptors["saevi-catalog"].species == "saevi"
    assert descriptors["tovren-catalog"].species == "tovren"
    assert descriptors["saevi-catalog"].appearance["species_id"] == "saevi"
    assert descriptors["tovren-catalog"].appearance["species_id"] == "tovren"
    assert descriptors["saevi-catalog"].appearance["height_scale"] > 0
    assert descriptors["tovren-catalog"].appearance["height_scale"] > 0
