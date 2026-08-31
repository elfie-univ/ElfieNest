from pathlib import Path

import pytest
import yaml

from infrastructure.persistence.configuration.world import (
    WorldCanonError,
    load_world_canon,
)


def _copy_world_config(root: Path) -> Path:
    source = Path(__file__).resolve().parents[4] / "config" / "world" / "elfaria.yaml"
    target = root / "world" / "elfaria.yaml"
    target.parent.mkdir(parents=True)
    target.write_bytes(source.read_bytes())
    return target


def test_world_canon_loads_the_bounded_first_version() -> None:
    package = load_world_canon()

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


def test_world_canon_rejects_a_modified_core_fact(tmp_path: Path) -> None:
    path = _copy_world_config(tmp_path)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["earth_relation"]["earth_home_name"] = "另一个基地"
    path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(WorldCanonError):
        load_world_canon(root=tmp_path)


def test_world_canon_rejects_an_unknown_place_reference(tmp_path: Path) -> None:
    path = _copy_world_config(tmp_path)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["knowledge"][0]["related_ids"] = ["not-a-place"]
    path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(WorldCanonError):
        load_world_canon(root=tmp_path)


def test_world_canon_preserves_optional_knowledge_importance(tmp_path: Path) -> None:
    path = _copy_world_config(tmp_path)
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["knowledge"][0]["importance"] = 0.91
    path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    package = load_world_canon(root=tmp_path)

    assert package.knowledge[0].importance == 0.91
