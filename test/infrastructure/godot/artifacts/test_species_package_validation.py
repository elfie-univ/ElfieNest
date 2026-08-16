from __future__ import annotations

from pathlib import Path

import pytest

from infrastructure.godot.artifacts import (
    species_package_validation,
    species_runtime_catalog,
)


def test_source_species_gate_joins_config_and_godot_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Completed:
        returncode = 0
        stdout = 'SPECIES_CATALOG_IDS:["dog","fox"]\n'
        stderr = ""

    monkeypatch.setattr(
        species_package_validation.subprocess,
        "run",
        lambda *args, **kwargs: Completed(),
    )

    assert species_package_validation.validate_source_species_packages(
        config_root=Path("config"),
        godot_project=Path("godot_project"),
        godot_binary=Path("/bin/true"),
    ) == ("dog", "fox")


def test_source_species_gate_rejects_a_different_godot_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Completed:
        returncode = 0
        stdout = 'SPECIES_CATALOG_IDS:["fox"]\n'
        stderr = ""

    monkeypatch.setattr(
        species_package_validation.subprocess,
        "run",
        lambda *args, **kwargs: Completed(),
    )

    with pytest.raises(
        species_package_validation.SpeciesPackageValidationError,
        match="discovery-set-mismatch",
    ):
        species_package_validation.validate_source_species_packages(
            config_root=Path("config"),
            godot_project=Path("godot_project"),
            godot_binary=Path("/bin/true"),
        )


def test_runtime_catalog_accepts_only_a_matching_validated_export_manifest(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "build-manifest.json"
    manifest.write_text(
        '{"schema_version": 2, "species_catalog_digest": "digest", '
        '"species_package_ids": ["dog", "fox"]}',
        encoding="utf-8",
    )
    catalog = type(
        "Catalog",
        (),
        {
            "digest": "digest",
            "definitions": (
                type(
                    "Definition", (), {"godot_package_id": "fox", "resolvable": True}
                )(),
                type(
                    "Definition", (), {"godot_package_id": "dog", "resolvable": True}
                )(),
            ),
        },
    )()

    readiness = species_runtime_catalog.build_species_runtime_catalog(
        catalog,
        runtime_manifest=manifest,
        godot_binary=Path("/missing/godot"),
    )

    assert readiness.available_species_ids() == ("dog", "fox")
    assert readiness.is_available("cat") is False


def test_runtime_catalog_fails_closed_for_old_or_mismatched_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = tmp_path / "build-manifest.json"
    manifest.write_text(
        '{"schema_version": 1, "species_catalog_digest": "digest", '
        '"species_package_ids": ["dog", "fox"]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(species_runtime_catalog, "_find_godot_binary", lambda: None)
    catalog = type(
        "Catalog",
        (),
        {
            "digest": "digest",
            "definitions": (
                type(
                    "Definition", (), {"godot_package_id": "fox", "resolvable": True}
                )(),
            ),
        },
    )()

    readiness = species_runtime_catalog.build_species_runtime_catalog(
        catalog,
        runtime_manifest=manifest,
    )

    assert readiness.available_species_ids() == ()
