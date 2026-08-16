import base64
from pathlib import Path

import pytest

from app.features.adoption import AcceptedAdoptionReservation
from elfie import ElfieFactory
from elfie.factory import ElfieAssembly
from infrastructure.persistence.elfie_workspace.adoption_profiles import (
    FinalElfieWorkspaceAdapter,
)
from infrastructure.persistence.elfie_workspace.brain_state import (
    YamlEnergyLimitsAdapter,
    YamlSelfhoodSeedAdapter,
)
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter


@pytest.mark.parametrize(
    ("species_id", "species_name"),
    (("fox", "Saevi"), ("dog", "Tovren")),
)
def test_workspace_adapter_materializes_the_final_elfie_profile(
    tmp_path: Path,
    species_id: str,
    species_name: str,
) -> None:
    adapter = FinalElfieWorkspaceAdapter(tmp_path)
    reservation = AcceptedAdoptionReservation(
        elfie_id="00000001",
        owner_user_id=7,
        name="星砂",
        species_id=species_id,
        personality_style="好奇探索",
        height="tall",
        build="plump",
        appearance_seed=42,
        face="soft",
        signature="warm",
        gender="female",
        birth_date="2000-01-01",
    )

    workspace = adapter.materialize(reservation)
    workspace_path = Path(workspace)
    profile_store = YamlProfileStoreAdapter(Path(workspace) / "profile")
    with SQLiteMemoryStoreAdapter(
        Path(workspace) / "memory" / "knowledge.sqlite"
    ) as memory_store:
        elfie = ElfieFactory().restore(
            ElfieAssembly(
                profile=profile_store.load(),
                selfhood_seed=YamlSelfhoodSeedAdapter(workspace_path / "brain").load(),
                energy_limits=YamlEnergyLimitsAdapter(workspace_path / "brain").load(),
                memory_store=memory_store,
            )
        )

        assert elfie.profile.identity.display_name == "星砂"
        assert elfie.profile.identity.species_id == species_id
        assert elfie.profile.identity.origin.home_world_id == "elfaria"
        assert elfie.selfhood_snapshot().species_name == species_name
        assert elfie.selfhood_snapshot().sensory_biases
        assert elfie.selfhood_snapshot().species_knowledge
        assert any(
            "Elfaria" in fact for fact in elfie.selfhood_snapshot().identity_facts
        )
        assert any("尊重自愿选择" in norm for norm in elfie.selfhood_snapshot().norms)
        assert memory_store.count_nodes("episodic") == 5
        assert memory_store.get_node("genesis:self:00000001") is not None
        known_elfie = memory_store.conn.execute(
            "SELECT species, is_self FROM known_elfies"
        ).fetchone()
        assert (known_elfie["species"], known_elfie["is_self"]) == (species_name, 1)
        self_model = memory_store.get_node("genesis:self-model:00000001")
        assert self_model is not None
        assert self_model.metadata["species_knowledge"]
        person = memory_store.conn.execute(
            "SELECT relationship_label, is_owner FROM people"
        ).fetchone()
        assert (person["relationship_label"], person["is_owner"]) == (
            "earth_household",
            1,
        )

    first_profile = profile_store.load()
    first_selfhood = YamlSelfhoodSeedAdapter(workspace_path / "brain").load()
    first_energy = YamlEnergyLimitsAdapter(workspace_path / "brain").load()
    adapter.materialize(reservation)
    second_profile = profile_store.load()
    assert second_profile == first_profile
    assert YamlSelfhoodSeedAdapter(workspace_path / "brain").load() == first_selfhood
    assert YamlEnergyLimitsAdapter(workspace_path / "brain").load() == first_energy

    adapter.release(reservation.elfie_id)
    assert not Path(workspace).exists()


def test_workspace_adapter_uses_a_species_compatible_pattern_for_marked_signature(
    tmp_path: Path,
) -> None:
    adapter = FinalElfieWorkspaceAdapter(tmp_path)
    reservation = AcceptedAdoptionReservation(
        elfie_id="00000002",
        owner_user_id=7,
        name="星砂",
        species_id="dog",
        personality_style="好奇探索",
        height="standard",
        build="standard",
        appearance_seed=43,
        face="soft",
        signature="marked",
        gender="female",
        birth_date="2001-01-01",
    )

    workspace = adapter.materialize(reservation)
    profile = YamlProfileStoreAdapter(Path(workspace) / "profile").load()

    assert profile.identity.species_id == "dog"
    assert profile.appearance.coat.pattern_id == "face_mask"
    profile.validate()
    adapter.release(reservation.elfie_id)


def test_workspace_adapter_persists_both_accepted_portrait_views(
    tmp_path: Path,
) -> None:
    png = b"\x89PNG\r\n\x1a\nportrait"
    data_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    adapter = FinalElfieWorkspaceAdapter(tmp_path)
    reservation = AcceptedAdoptionReservation(
        elfie_id="00000003",
        owner_user_id=7,
        name="星砂",
        species_id="fox",
        personality_style="好奇探索",
        height="standard",
        build="standard",
        appearance_seed=42,
        face="soft",
        signature="warm",
        gender="female",
        birth_date="2000-01-01",
        full_body_image_url=data_url,
        headshot_image_url=data_url,
    )

    workspace = Path(adapter.materialize(reservation))

    assert (workspace / "assets" / "portrait-full.png").read_bytes() == png
    assert (workspace / "assets" / "portrait-head.png").read_bytes() == png
    adapter.release(reservation.elfie_id)
