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


def test_default_profile_sections_are_loaded_without_a_profile_file(
    tmp_path: Path,
) -> None:
    # Given: bundled default sections without a canonical profile.yaml.
    (tmp_path / "personality.yaml").write_text(
        "big_five:\n  openness: 0.8\n", encoding="utf-8"
    )

    # When: the profile repository reads the default sections.
    sections = ElfieProfileRepository(tmp_path).load_default_sections()

    # Then: the section is available without requiring a user profile file.
    assert sections["personality"] == {"big_five": {"openness": 0.8}}
    assert sections["capabilities"] == {}
