import base64
from pathlib import Path

from app.features.adoption import AcceptedAdoptionReservation
from elfie import ElfieFactory
from elfie.factory import ElfieAssembly
from infrastructure.persistence.elfie_workspace.adoption_profiles import (
    FinalElfieWorkspaceAdapter,
)
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter


def test_workspace_adapter_materializes_the_final_elfie_profile(tmp_path: Path) -> None:
    adapter = FinalElfieWorkspaceAdapter(tmp_path)
    reservation = AcceptedAdoptionReservation(
        elfie_id="00000001",
        owner_user_id=7,
        name="星砂",
        species_id="fox",
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
    profile_store = YamlProfileStoreAdapter(Path(workspace) / "profile")
    elfie = ElfieFactory().restore(
        ElfieAssembly(
            profile=profile_store.load(),
            memory_store=SQLiteMemoryStoreAdapter(
                Path(workspace) / "memory" / "knowledge.sqlite"
            ),
        )
    )

    assert elfie.profile.identity.display_name == "星砂"
    assert elfie.profile.identity.species_id == "fox"
    assert "big_five" in elfie.profile.personality
    assert "actuators" in elfie.profile.capabilities

    adapter.release(reservation.elfie_id)
    assert not Path(workspace).exists()


def test_workspace_adapter_persists_both_accepted_portrait_views(tmp_path: Path) -> None:
    png = b"\x89PNG\r\n\x1a\nportrait"
    data_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    adapter = FinalElfieWorkspaceAdapter(tmp_path)
    reservation = AcceptedAdoptionReservation(
        elfie_id="00000002",
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
