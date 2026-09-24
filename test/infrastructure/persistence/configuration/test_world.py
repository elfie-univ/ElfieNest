from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from infrastructure.persistence.configuration.documents import (
    resolve_bundled_config_root,
)
from infrastructure.persistence.configuration.world import (
    GenesisSourcePackageError,
    load_genesis_source_package,
)


def test_genesis_source_package_loads_the_published_version_bound_bundle() -> None:
    package = load_genesis_source_package()

    assert (package.world_id, package.display_name) == ("elfaria", "Elfaria")
    assert package.package_version == "elfaria-genesis.v1"
    assert package.manifest.status == "published"
    assert len(package.manifest.member_ids) == 18
    assert len(package.knowledge) == 161
    assert package.knowledge[0].fact_id == "A-01"
    assert package.knowledge[0].source_ref == "knowledge/elfaria.yaml#A-01"
    assert "Saevi、Tovren 和 Myelle" in package.knowledge[0].statement
    assert len(package.story_events) == 16
    assert len(package.routes) == 16


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
