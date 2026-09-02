from pathlib import Path

import pytest
import yaml

from infrastructure.persistence.configuration.world import (
    GenesisSourcePackageError,
    _document_hash,
    load_genesis_source_package,
)


def _copy_world_config(root: Path) -> Path:
    source = Path(__file__).resolve().parents[4] / "config" / "world" / "elfaria.yaml"
    target = root / "world" / "elfaria.yaml"
    target.parent.mkdir(parents=True)
    target.write_bytes(source.read_bytes())
    return target


def test_genesis_source_package_loads_the_bounded_first_version() -> None:
    package = load_genesis_source_package()

    assert (package.world_id, package.display_name) == ("elfaria", "Elfaria")
    assert package.known_region_id == "mistyville"
    assert {place.place_id for place in package.places} >= {
        "mistyville_square",
        "mistyville_homes",
        "mistyville_learning_house",
        "mistyville_waystation",
        "earth_gateway_station",
        "elfie_nest",
    }
    assert {event.event_id for event in package.story_events} >= {
        "story_signal",
        "story_confirmation",
        "story_station",
        "story_program",
        "story_arrival",
    }
    topics = {fact.topic for fact in package.knowledge}
    assert {
        "world_identity",
        "nature_and_physics",
        "geography",
        "species_and_body",
        "society_and_civilization",
        "history_and_culture",
        "earth_and_arrival",
        "knowledge_boundary",
    } <= topics
    assert any(fact.status == "unknown-boundary" for fact in package.knowledge)


def test_genesis_source_package_publishes_resident_weather_facts() -> None:
    package = load_genesis_source_package()

    light_cycle = package.fact("nature.light_cycle")
    seasons = package.fact("nature.seasons")
    water_cycle = package.fact("nature.water_cycle")

    assert "伊洛拉" in light_cycle.statement
    assert "196 个本地日" in light_cycle.statement
    assert light_cycle.level == "common"
    assert light_cycle.status == "active"
    assert "雨季" in seasons.statement
    assert "旱季" in seasons.statement
    assert seasons.level == "common"
    assert seasons.status == "active"
    assert "降雨" in water_cycle.statement
    assert water_cycle.level == "common"
    assert water_cycle.status == "active"
    assert all(
        "Canon" not in fact.statement for fact in (light_cycle, seasons, water_cycle)
    )


def test_genesis_source_package_publishes_complete_generation_catalogs() -> None:
    package = load_genesis_source_package()

    fact_ids = {fact.fact_id for fact in package.knowledge}
    mapped_ids = [
        resident_id
        for link in package.coverage_manifest.links
        for resident_id in link.resident_fact_ids
    ]

    assert package.coverage_manifest.creator_source_ref
    assert package.coverage_manifest.resident_source_ref
    assert len(mapped_ids) == len(fact_ids)
    assert set(mapped_ids) == fact_ids
    assert len(mapped_ids) == len(set(mapped_ids))
    assert package.life_archetypes
    assert package.relationship_archetypes
    assert package.episode_themes
    assert package.routes


def test_genesis_source_package_rejects_incomplete_coverage_manifest(
    tmp_path: Path,
) -> None:
    path = _copy_world_config(tmp_path)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    links = document["genesis"]["coverage_manifest"]["links"]
    document["genesis"]["coverage_manifest"]["links"] = links[:-1]
    document["genesis"]["content_sha256"] = _document_hash(document)
    path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(GenesisSourcePackageError, match="CoverageManifest"):
        load_genesis_source_package(root=tmp_path)


def test_genesis_source_package_rejects_a_modified_core_fact(tmp_path: Path) -> None:
    path = _copy_world_config(tmp_path)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["earth_relation"]["earth_home_name"] = "另一个基地"
    path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(GenesisSourcePackageError):
        load_genesis_source_package(root=tmp_path)


def test_genesis_source_package_rejects_an_unknown_place_reference(
    tmp_path: Path,
) -> None:
    path = _copy_world_config(tmp_path)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["knowledge"][0]["related_ids"] = ["not-a-place"]
    path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(GenesisSourcePackageError):
        load_genesis_source_package(root=tmp_path)


def test_genesis_source_package_preserves_optional_knowledge_importance(
    tmp_path: Path,
) -> None:
    path = _copy_world_config(tmp_path)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["knowledge"][0]["importance"] = 0.91
    path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    package = load_genesis_source_package(root=tmp_path)

    assert package.knowledge[0].importance == 0.91
