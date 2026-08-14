from pathlib import Path

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
    assert tuple(definition.sort_order for definition in definitions) == (0, 1, 2)
    assert all(
        definition.avatar_url.startswith("/assets/adoption/")
        for definition in definitions
    )
    assert all(definition.scene_id for definition in definitions)
    assert all(len(definition.canon.candidate_names) >= 5 for definition in definitions)

    project_root = Path(__file__).resolve().parents[3]
    for definition in definitions:
        avatar_path = (
            project_root
            / "app/interfaces/web/frontend/public"
            / definition.avatar_url.lstrip("/")
        )
        scene_path = (
            project_root
            / "godot_project/characters"
            / definition.scene_id
            / f"{definition.scene_id}.tscn"
        )
        assert avatar_path.is_file()
        assert scene_path.is_file()


def test_species_lookup_is_data_driven_for_each_registered_id() -> None:
    for definition in list_species_definitions():
        resolved = get_species_definition(definition.species_id)
        assert resolved.canon_id == definition.canon_id
        assert resolved.appearance.species_id == definition.species_id
