from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from infrastructure.persistence.configuration.documents import (
    resolve_bundled_config_root,
)
from infrastructure.persistence.configuration.world import (
    GenesisSourcePackageError,
    _validate_package,
    load_genesis_source_package,
)


def test_genesis_source_package_loads_the_published_version_bound_bundle() -> None:
    package = load_genesis_source_package()

    assert (package.world_id, package.display_name) == ("elfaria", "Elfaria")
    assert package.package_version == "elfaria-genesis.v4"
    assert package.manifest.status == "published"
    assert len(package.manifest.member_ids) == 18
    assert len(package.knowledge) == 160
    assert package.knowledge[0].fact_id == "A-01"
    assert package.knowledge[0].source_ref == "knowledge/elfaria.yaml#A-01"
    assert "Saevi、Tovren 和 Myelle" in package.knowledge[0].statement
    assert len(package.story_events) == 16
    assert len(package.routes) == 16
    assert package.place("earthbound_station").parent_id == "central_mixed"
    assert len(package.place_relations) == 7
    assert {
        (item.subject_id, item.relation, item.object_id)
        for item in package.place_relations
    } == {
        ("skyreach_tree", "at_center_of", "skyreach_square"),
        ("skyreach_square", "coordinate_origin_of", "mistyville_center"),
        ("cloudcrown_city", "suspended_above", "skymirror_lake"),
        ("cloudfall_falls", "outflow_from", "skymirror_lake"),
        ("riverturn_bend", "open_arc_below", "riverturn_hill"),
        ("lakeheart_isle", "in_center_of", "clearheart_lake"),
        ("undercity_gate", "public_entrance_to", "undercity"),
    }


def test_genesis_source_rejects_unregistered_experience_kinds(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    shutil.copytree(resolve_bundled_config_root() / "genesis", config_root / "genesis")
    shutil.copytree(resolve_bundled_config_root() / "memory", config_root / "memory")
    program_path = config_root / "genesis" / "program.yaml"
    document = yaml.safe_load(program_path.read_text(encoding="utf-8"))
    document["rules"]["episode_themes"]["themes"][0]["event_kind"] = "reset"
    canonical = dict(document)
    manifest = dict(document["manifest"])
    manifest.pop("content_sha256")
    canonical["manifest"] = manifest
    document["manifest"]["content_sha256"] = hashlib.sha256(
        json.dumps(
            canonical,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    program_path.write_text(
        yaml.safe_dump(document, allow_unicode=True), encoding="utf-8"
    )

    with pytest.raises(GenesisSourcePackageError, match="event_kind 无效"):
        load_genesis_source_package(root=config_root)


def test_geography_is_projected_as_uniform_region_then_cell_sampling() -> None:
    package = load_genesis_source_package()
    cells = package.spatial_population.cells

    assert len(cells) == 83
    assert all(cell.weight == 1.0 for cell in cells)
    assert {cell.region_id for cell in cells} == {
        "A1",
        "A2",
        "B",
        "C1",
        "C2",
        "C3",
        "D",
    }
    assert {
        species_id
        for cell in cells
        if cell.region_id == "D"
        for species_id in cell.species_ids
    } == {"fox", "dog", "cat"}
    assert all(cell.species_ids == ("fox",) for cell in cells if cell.region_id == "B")
    assert package.place("myelle_region").aliases == ("A1", "A2")


def test_resident_knowledge_keeps_source_conditions_as_atomic_gates() -> None:
    package = load_genesis_source_package()

    myelle_landscape = package.fact("B-02-02")
    assert myelle_landscape.conditions[0].kind == "place"
    assert myelle_landscape.conditions[0].value("id") == "myelle_region"
    assert myelle_landscape.conditions[0].value("contact") == "residence"
    assert package.fact("B-04-02").conditions[0].kind == "route"
    assert package.fact("B-04-02").conditions[0].value("status") == "traversed"
    assert package.fact("E-08-02").conditions[0].value("id") == "earth_arrival"
    assert package.generation_policy.seed_algorithm == "sha256-domain-v1"
    assert package.generation_policy.medium_knowledge_probability == 0.5
    assert package.earth_arrival_rules.required_knowledge_ids == ("E-08",)
    assert package.earth_arrival_rules.post_arrival_knowledge_ids == (
        "E-08-02",
        "E-08-03",
    )


def test_genesis_source_package_rejects_a_tampered_member(tmp_path: Path) -> None:
    root = tmp_path / "config"
    shutil.copytree(resolve_bundled_config_root(), root)
    member = root / "genesis" / "knowledge" / "elfaria.yaml"
    member.write_text(
        member.read_text(encoding="utf-8") + "# tampered\n", encoding="utf-8"
    )

    with pytest.raises(GenesisSourcePackageError):
        load_genesis_source_package(root=root)


def test_genesis_source_package_rejects_parent_cycles() -> None:
    package = load_genesis_source_package()
    station = package.place("earthbound_station")
    center = package.place("mistyville_center")
    places = tuple(
        replace(
            place,
            parent_id=(
                "mistyville_center"
                if place.place_id == station.place_id
                else "earthbound_station"
                if place.place_id == center.place_id
                else place.parent_id
            ),
        )
        for place in package.places
    )
    tampered = replace(package, places=places)

    with pytest.raises(ValueError, match="地点层级存在环"):
        _validate_package(tampered, {"program_version": package.package_version})


def test_public_geography_has_five_districts_and_separate_town_facilities() -> None:
    package = load_genesis_source_package()
    assert {p.place_id for p in package.places if p.parent_id == "mistyville"} == {
        "north_mountain",
        "east_forest",
        "south_plain",
        "central_mixed",
        "clearheart_lake",
    }
    assert package.place("mistyville_center").parent_id == "central_mixed"
    assert package.place("earthbound_station").parent_id == "central_mixed"
    assert package.place("D").parent_id == "central_mixed"
    assert package.place("X").parent_id == "elfaria"
    assert "混住" in package.place("central_mixed").description
