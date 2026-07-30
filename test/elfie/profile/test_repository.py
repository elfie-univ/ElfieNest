from pathlib import Path

from elfie.profile import ElfieProfileRepository, create_visual_profile


def test_profile_yaml_round_trip(tmp_path: Path) -> None:
    profile = create_visual_profile(
        elfie_id="elfie-yaml",
        display_name="小栗",
        species_id="fox",
        seed=456,
    )
    repository = ElfieProfileRepository(tmp_path)
    path = repository.save(profile)

    assert path == tmp_path / "profile.yaml"
    assert repository.exists()
    assert repository.load() == profile
    assert not (tmp_path / "profile.yaml.tmp").exists()
