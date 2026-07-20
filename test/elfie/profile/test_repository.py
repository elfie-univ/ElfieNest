from pathlib import Path

import yaml

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


def test_old_profile_is_hydrated_from_legacy_yaml_once(tmp_path: Path) -> None:
    profile = create_visual_profile(
        elfie_id="elfie-migrate",
        display_name="迁移测试",
        species_id="dog",
        seed=789,
    )
    repository = ElfieProfileRepository(tmp_path)
    repository.save(profile)
    personality = {"metadata": {"name": "迁移测试"}, "big_five": {"openness": 0.8}}
    (tmp_path / "personality.yaml").write_text(
        yaml.safe_dump(personality, allow_unicode=True),
        encoding="utf-8",
    )

    migrated = repository.load()

    assert migrated.personality == personality
    assert repository.load(migrate_legacy=False).personality == personality
