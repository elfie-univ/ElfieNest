from pathlib import Path

from app.features.adoption.service import AdoptionRequest, _register_with_engine
from elfie import Elfie
from elfie.profile import ElfieProfileRepository, create_visual_profile


class FakeSession:
    def __init__(self) -> None:
        self.registered = []

    def register_elfie(self, elfie_id, elfie) -> None:
        self.registered.append((elfie_id, elfie))


class FakeEngine:
    def __init__(self) -> None:
        self.api_server = None
        self.session = FakeSession()


def test_adoption_engine_registration_uses_canonical_factory(tmp_path: Path) -> None:
    elfie_id = "elfie-adopted"
    profile = create_visual_profile(
        elfie_id=elfie_id,
        display_name="新伙伴",
        species_id="dog",
        seed=123,
    )
    ElfieProfileRepository(tmp_path / "profile").save(profile)
    engine = FakeEngine()

    _register_with_engine(
        engine,
        elfie_id,
        AdoptionRequest(
            name="新伙伴",
            species_id="dog",
            personality_style="好奇探索",
            height="standard",
            build="standard",
        ),
        str(tmp_path),
        str(tmp_path / "nest.db"),
    )

    registered_id, registered = engine.session.registered[0]
    assert registered_id == elfie_id
    assert isinstance(registered, Elfie)
    assert registered.profile.to_dict() == profile.to_dict()
