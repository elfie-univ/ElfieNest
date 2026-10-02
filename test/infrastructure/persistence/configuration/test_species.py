from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
import yaml

from infrastructure.persistence.configuration.documents import (
    resolve_bundled_config_root,
)
from infrastructure.persistence.configuration.species import (
    SpeciesCatalogError,
    load_species_catalog,
    species_asset_path,
)


def _refresh_package_hashes(root: Path) -> None:
    program_path = root / "genesis" / "program.yaml"
    document = yaml.safe_load(program_path.read_text(encoding="utf-8"))
    package_root = program_path.parent
    for member in document["manifest"]["members"]:
        payload = (package_root / member["path"]).read_bytes()
        member["sha256"] = hashlib.sha256(payload).hexdigest()
    document["manifest"].pop("content_sha256", None)
    canonical = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    document["manifest"]["content_sha256"] = hashlib.sha256(canonical).hexdigest()
    program_path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def test_bundled_catalog_loads_only_complete_adoptable_species() -> None:
    catalog = load_species_catalog()

    assert catalog.supported_species == ("fox", "dog")
    assert [item.species_id for item in catalog.definitions] == ["fox", "dog"]
    assert catalog.definition("fox").display_name == "Saevi"
    assert catalog.definition("dog").display_name == "Tovren"
    assert catalog.definition("fox").presentation_images is not None
    assert catalog.definition("dog").genesis is not None
    assert catalog.definition("fox").genesis.terminal_age_years == 17
    assert catalog.definition("dog").genesis.terminal_age_years == 22
    assert catalog.definition("fox").genesis.median_age_years == 15
    assert catalog.definition("dog").genesis.median_age_years == 20
    assert catalog.definition("dog").genesis.stage_ranges["mature"] == (6, 14)
    assert catalog.definition("fox").genesis.stage_ranges["mature"] == (5, 10)
    assert len(catalog.digest) == 64
    assert catalog.definition("fox").appearance.supported_controls == (
        "stature",
        "build",
        "signature",
    )


def test_species_stage_ranges_are_contiguous_and_use_half_open_endpoints() -> None:
    catalog = load_species_catalog()

    for definition in catalog.definitions:
        assert definition.genesis is not None
        ranges = definition.genesis.stage_ranges
        assert tuple(ranges) == ("childhood", "adolescent", "mature", "elder")
        assert ranges["childhood"][0] == 0
        assert ranges["childhood"][1] == ranges["adolescent"][0]
        assert ranges["adolescent"][1] == ranges["mature"][0]
        assert ranges["mature"][1] == ranges["elder"][0]
        assert ranges["elder"][1] == definition.genesis.terminal_age_years


@pytest.mark.parametrize("species_id", ("fox", "dog"))
def test_reviewed_elbow_knee_and_tail_underside_regions_are_colorable(
    species_id: str,
) -> None:
    appearance = load_species_catalog().definition(species_id).appearance

    for region_id in ("elbow_cuff_pair", "knee_cuff_pair", "tail_underside"):
        rule = appearance.region_rules[region_id]
        assert rule.mode == "color-only"
        assert rule.allowed_colors == appearance.palettes
        assert rule.allowed_grades == ("L1", "L2", "D1", "D2")


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


def test_species_digest_is_stable_across_text_checkout_newlines(tmp_path: Path) -> None:
    root = tmp_path / "config"
    shutil.copytree(resolve_bundled_config_root(), root)
    for path in (root / "genesis" / "species").rglob("*"):
        if path.is_file() and path.suffix.lower() in {".yaml", ".yml"}:
            path.write_bytes(
                path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            )
    _refresh_package_hashes(root)

    assert load_species_catalog(root=root).digest == load_species_catalog().digest


def test_published_species_rejects_invalid_png_members(tmp_path: Path) -> None:
    root = tmp_path / "config"
    shutil.copytree(resolve_bundled_config_root(), root)
    (root / "genesis" / "species" / "saevi" / "assets" / "headshot.png").write_bytes(
        b"not-a-png"
    )
    _refresh_package_hashes(root)

    with pytest.raises(SpeciesCatalogError, match="有效 PNG"):
        load_species_catalog(root=root)


def test_published_species_rejects_duplicate_presentation_images(
    tmp_path: Path,
) -> None:
    root = tmp_path / "config"
    shutil.copytree(resolve_bundled_config_root(), root)
    source = root / "genesis" / "species" / "saevi" / "assets" / "headshot.png"
    target = root / "genesis" / "species" / "saevi" / "assets" / "full-body.png"
    target.write_bytes(source.read_bytes())
    _refresh_package_hashes(root)

    with pytest.raises(SpeciesCatalogError, match="不得使用同一张图片"):
        load_species_catalog(root=root)


def test_species_appearance_must_declare_each_supported_control(
    tmp_path: Path,
) -> None:
    root = tmp_path / "config"
    shutil.copytree(resolve_bundled_config_root(), root)
    appearance = root / "genesis" / "species" / "saevi" / "appearance.yaml"
    document = yaml.safe_load(appearance.read_text(encoding="utf-8"))
    document["supported_controls"].remove("signature")
    appearance.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    _refresh_package_hashes(root)

    with pytest.raises(SpeciesCatalogError, match="必要控制"):
        load_species_catalog(root=root)


def test_species_appearance_must_declare_options_for_each_control(
    tmp_path: Path,
) -> None:
    root = tmp_path / "config"
    shutil.copytree(resolve_bundled_config_root(), root)
    appearance = root / "genesis" / "species" / "saevi" / "appearance.yaml"
    document = yaml.safe_load(appearance.read_text(encoding="utf-8"))
    document["control_options"].pop("signature")
    appearance.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    _refresh_package_hashes(root)

    with pytest.raises(SpeciesCatalogError, match="必要控制"):
        load_species_catalog(root=root)


@pytest.mark.parametrize(
    ("package", "elder", "median", "terminal"),
    [("saevi", 10, 15, 17), ("tovren", 14, 20, 22), ("myelle", 14, 20, 22)],
)
def test_species_lifespan_separates_median_from_hard_endpoint(
    package: str,
    elder: int,
    median: int,
    terminal: int,
) -> None:
    from infrastructure.persistence.configuration.species import _genesis_profile

    path = (
        resolve_bundled_config_root()
        / "genesis"
        / "species"
        / package
        / "generation.yaml"
    )
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    profile = _genesis_profile(document)
    assert profile.median_age_years == median
    assert profile.stage_ranges["elder"] == (elder, terminal)
    assert profile.terminal_age_years == terminal
    assert profile.stage_ranges["mature"][1] == elder
    for invalid_median in (elder, terminal):
        document["stage_endpoint_policy"]["median_age_local_years"] = invalid_median
        with pytest.raises(ValueError, match="寿命中位数"):
            _genesis_profile(document)
