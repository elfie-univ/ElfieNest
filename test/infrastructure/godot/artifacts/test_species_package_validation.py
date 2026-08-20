from __future__ import annotations

from pathlib import Path

import pytest

from infrastructure.godot.artifacts import (
    species_package_validation,
    species_runtime_catalog,
)
from infrastructure.persistence.configuration.species import load_species_catalog


def _godot_runner(
    stdout: str,
) -> species_package_validation.GodotSpeciesValidationRunner:
    def run(
        *,
        godot_binary: Path,
        godot_project: Path,
        timeout_seconds: float,
    ) -> species_package_validation.GodotSpeciesValidationResult:
        del godot_binary, godot_project, timeout_seconds
        return species_package_validation.GodotSpeciesValidationResult(0, stdout, "")

    return run


def test_source_species_gate_joins_config_and_godot_ids() -> None:

    assert species_package_validation.validate_source_species_packages(
        config_root=Path("config"),
        godot_project=Path("godot_project"),
        godot_runner=_godot_runner('SPECIES_CATALOG_IDS:["dog","fox"]\n'),
        godot_binary=Path("/bin/true"),
    ) == ("dog", "fox")


def test_source_species_gate_rejects_a_different_godot_catalog() -> None:
    with pytest.raises(
        species_package_validation.SpeciesPackageValidationError,
        match="discovery-set-mismatch",
    ):
        species_package_validation.validate_source_species_packages(
            config_root=Path("config"),
            godot_project=Path("godot_project"),
            godot_runner=_godot_runner('SPECIES_CATALOG_IDS:["fox"]\n'),
            godot_binary=Path("/bin/true"),
        )


def test_source_species_gate_preserves_godot_output_on_validation_failure() -> None:
    def failing_runner(
        *,
        godot_binary: Path,
        godot_project: Path,
        timeout_seconds: float,
    ) -> species_package_validation.GodotSpeciesValidationResult:
        del godot_binary, godot_project, timeout_seconds
        return species_package_validation.GodotSpeciesValidationResult(
            1,
            "godot stdout detail\n",
            "godot stderr detail\n",
        )

    with pytest.raises(
        species_package_validation.SpeciesPackageValidationError,
        match="godot-species-validation-failed exit=1",
    ) as raised:
        species_package_validation.validate_source_species_packages(
            config_root=Path("config"),
            godot_project=Path("godot_project"),
            godot_runner=failing_runner,
            godot_binary=Path("/bin/true"),
        )

    assert raised.value.stdout == "godot stdout detail\n"
    assert raised.value.stderr == "godot stderr detail\n"
    assert raised.value.phase == "species-validation"


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


def test_runtime_catalog_uses_the_injected_godot_runner_for_source_validation(
    tmp_path: Path,
) -> None:
    catalog = load_species_catalog()

    readiness = species_runtime_catalog.build_species_runtime_catalog(
        catalog,
        runtime_manifest=tmp_path / "missing-manifest.json",
        godot_binary=Path("/bin/true"),
        godot_runner=_godot_runner('SPECIES_CATALOG_IDS:["dog","fox"]\n'),
    )

    assert readiness.available_species_ids() == ("dog", "fox")
    assert readiness.source == "source-validation"


def test_runtime_catalog_resolves_frozen_config_from_launcher_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, Path] = {}

    def validating_source_packages(**kwargs: object) -> tuple[str, ...]:
        config_root = kwargs["config_root"]
        godot_project = kwargs["godot_project"]
        assert isinstance(config_root, Path)
        assert isinstance(godot_project, Path)
        observed["config_root"] = config_root
        observed["godot_project"] = godot_project
        return ("dog", "fox")

    monkeypatch.setattr(
        species_runtime_catalog,
        "validate_source_species_packages",
        validating_source_packages,
    )
    bundled_config = tmp_path / "Resources" / "config"
    application_root = tmp_path / "ElfieNest.app"
    monkeypatch.setenv("ELFIENEST_BUNDLED_CONFIG_DIR", str(bundled_config))
    monkeypatch.setenv("ELFIENEST_PROJECT_ROOT", str(application_root))
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
        runtime_manifest=tmp_path / "missing-manifest.json",
        godot_binary=Path("/bin/true"),
        godot_runner=_godot_runner('SPECIES_CATALOG_IDS:["dog","fox"]\n'),
    )

    assert readiness.source == "source-validation"
    assert observed == {
        "config_root": bundled_config.resolve(),
        "godot_project": (application_root / "godot_project").resolve(),
    }


def test_runtime_catalog_rejects_a_missing_godot_runner(
    tmp_path: Path,
) -> None:
    with pytest.raises(RuntimeError, match="injected Godot validation runner"):
        species_runtime_catalog.build_species_runtime_catalog(
            load_species_catalog(),
            runtime_manifest=tmp_path / "missing-manifest.json",
            godot_binary=Path("/bin/true"),
        )
