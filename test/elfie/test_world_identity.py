from elfie import ElfieFactory
from elfie.diagnostics import ElfieDiagnostics
from elfie.factory import ElfieAssembly
from elfie.profile import create_visual_profile
from test.elfie.brain.memory.fake_store import FakeMemoryStore


def test_all_three_species_carry_canon_into_selfhood_and_memory_identity() -> None:
    expected = {"fox": ("saevi", "Saevi"), "dog": ("tovren", "Tovren"), "cat": ("myelle", "Myelle")}
    for species_id, (canon_id, species_name) in expected.items():
        elfie = ElfieFactory().assemble(
            ElfieAssembly(
                profile=create_visual_profile(
                    elfie_id=f"world-identity-{species_id}",
                    display_name="Lumi",
                    species_id=species_id,
                    seed=5,
                ),
                memory_store=FakeMemoryStore.in_memory(),
            )
        )

        anchor = elfie.profile_anchor_snapshot()
        selfhood = elfie.selfhood_snapshot()
        identity_text = ElfieDiagnostics(elfie).memory.get_self_narrative()["identity"]

        assert (anchor.species_canon_id, anchor.species_name) == (canon_id, species_name)
        assert (anchor.home_world_name, anchor.earth_home_name) == ("Elfaria", "ElfieNest")
        assert species_name in selfhood.self_description
        assert "Elfaria" in selfhood.self_description
        assert selfhood.identity_facts
        assert species_name in identity_text
