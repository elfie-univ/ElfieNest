import json
from pathlib import Path

import pytest

from elfie.profile import (
    SUPPORTED_SPECIES,
    get_species_definition,
    list_species_definitions,
    validate_species_registry,
)


def test_species_registry_is_complete_and_stably_ordered() -> None:
    validate_species_registry()
    definitions = list_species_definitions()

    assert (
        tuple(definition.species_id for definition in definitions) == SUPPORTED_SPECIES
    )
    assert tuple(definition.sort_order for definition in definitions) == (0, 1)
    assert all(definition.scene_id for definition in definitions)
    assert all(not hasattr(definition.canon, "candidate_names") for definition in definitions)

    project_root = Path(__file__).resolve().parents[3]
    package_root = project_root / "godot_project" / "characters"
    package_ids = {
        manifest.parent.name
        for manifest in package_root.glob("*/species_manifest.json")
    }
    assert package_ids == set(SUPPORTED_SPECIES)
    for definition in definitions:
        manifest_path = package_root / definition.scene_id / "species_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        scene_path = package_root / definition.scene_id / manifest["scene_file"]
        model_path = package_root / definition.scene_id / manifest["model_file"]
        assert manifest["species_id"] == definition.species_id
        assert scene_path.is_file()
        assert model_path.is_file()
        assert manifest["required_nodes"]
        assert manifest["required_animations"]
        assert manifest["required_capabilities"] == [
            "movement",
            "appearance",
            "portrait",
            "preview",
        ]

    assert not (package_root / "cat").exists()


def test_species_lookup_is_data_driven_for_each_registered_id() -> None:
    for definition in list_species_definitions():
        resolved = get_species_definition(definition.species_id)
        assert resolved.canon_id == definition.canon_id
        assert resolved.appearance.species_id == definition.species_id

    with pytest.raises(ValueError, match="cat"):
        get_species_definition("cat")
