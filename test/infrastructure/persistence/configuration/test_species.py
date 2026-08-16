from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from infrastructure.persistence.configuration.documents import (
    resolve_bundled_config_root,
)
from infrastructure.persistence.configuration.species import (
    SpeciesCatalogError,
    load_species_catalog,
    species_asset_path,
)


def test_bundled_catalog_loads_only_complete_adoptable_species() -> None:
    catalog = load_species_catalog()

    assert catalog.supported_species == ("fox", "dog")
    assert [item.species_id for item in catalog.definitions] == ["fox", "dog", "cat"]
    assert catalog.definition("fox").presentation_images is not None
    assert catalog.definition("dog").genesis is not None
    assert len(catalog.digest) == 64
    assert catalog.definition("fox").appearance.supported_controls == (
        "stature",
        "build",
        "face",
        "signature",
    )
    assert catalog.definition("fox").appearance.control_options["face"] == (
        "soft",
        "balanced",
        "defined",
        "any",
    )


def test_species_assets_are_validated_inside_their_package(tmp_path: Path) -> None:
    root = tmp_path / "config"
    shutil.copytree(resolve_bundled_config_root(), root)
    catalog = load_species_catalog(root=root)
    definition = catalog.definition("fox")

    headshot = species_asset_path(root, definition, "headshot")
    full_body = species_asset_path(root, definition, "full-body")

    assert headshot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert full_body.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert headshot != full_body


def test_published_species_rejects_invalid_png_members(tmp_path: Path) -> None:
    root = tmp_path / "config"
    shutil.copytree(resolve_bundled_config_root(), root)
    (root / "species" / "fox" / "assets" / "headshot.png").write_bytes(
        b"not-a-png"
    )

    with pytest.raises(SpeciesCatalogError, match="有效 PNG"):
        load_species_catalog(root=root)


def test_published_species_rejects_duplicate_presentation_images(tmp_path: Path) -> None:
    root = tmp_path / "config"
    shutil.copytree(resolve_bundled_config_root(), root)
    source = root / "species" / "fox" / "assets" / "headshot.png"
    target = root / "species" / "fox" / "assets" / "full-body.png"
    target.write_bytes(source.read_bytes())

    with pytest.raises(SpeciesCatalogError, match="不得使用同一张图片"):
        load_species_catalog(root=root)


def test_species_appearance_must_declare_the_existing_four_control_protocol(
    tmp_path: Path,
) -> None:
    root = tmp_path / "config"
    shutil.copytree(resolve_bundled_config_root(), root)
    appearance = root / "species" / "fox" / "appearance.yaml"
    appearance.write_text(
        appearance.read_text(encoding="utf-8").replace("  - signature\n", ""),
        encoding="utf-8",
    )

    with pytest.raises(SpeciesCatalogError, match="必要控制"):
        load_species_catalog(root=root)


def test_species_appearance_must_declare_options_for_each_control(
    tmp_path: Path,
) -> None:
    root = tmp_path / "config"
    shutil.copytree(resolve_bundled_config_root(), root)
    appearance = root / "species" / "fox" / "appearance.yaml"
    appearance.write_text(
        appearance.read_text(encoding="utf-8").replace(
            "  signature: [warm, marked, ears, any]\n", ""
        ),
        encoding="utf-8",
    )

    with pytest.raises(SpeciesCatalogError, match="必要控制"):
        load_species_catalog(root=root)
