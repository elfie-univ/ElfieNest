import stat
from pathlib import Path

from elfie.brain.energy import load_packaged_energy_limits
from elfie.brain.selfhood import load_packaged_selfhood_seed
from elfie.profile import create_visual_profile
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter


def test_profile_yaml_round_trip(tmp_path: Path) -> None:
    profile = create_visual_profile(
        elfie_id="elfie-yaml",
        display_name="小栗",
        species_id="fox",
        seed=456,
    )
    repository = YamlProfileStoreAdapter(tmp_path)
    repository.save(profile)
    path = repository.path

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
    repository = YamlProfileStoreAdapter(profile_dir)
    repository.save(profile)
    path = repository.path

    # Then: both the directory and file are owner-only.
    assert stat.S_IMODE(profile_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_default_owner_seeds_are_loaded_without_a_profile_file(
    tmp_path: Path,
) -> None:
    # When: the profile domain reads its immutable bundled defaults.
    selfhood = load_packaged_selfhood_seed()
    energy = load_packaged_energy_limits()

    # Then: the section is available without requiring a user profile file.
    assert "big_five" in selfhood
    assert "limits" in energy
