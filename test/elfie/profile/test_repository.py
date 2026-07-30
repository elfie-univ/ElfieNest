import stat
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


def test_profile_save_repairs_owner_only_permissions(tmp_path: Path) -> None:
    # Given: a profile directory inherited permissive default modes.
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir(mode=0o755)
    profile = create_visual_profile(
        elfie_id="elfie-private",
        display_name="小栗",
        species_id="fox",
        seed=789,
    )

    # When: the canonical profile is saved.
    path = ElfieProfileRepository(profile_dir).save(profile)

    # Then: both the directory and file are owner-only.
    assert stat.S_IMODE(profile_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
