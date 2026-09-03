from __future__ import annotations

from pathlib import Path

import pytest

from infrastructure.skills import BundledSkillCatalog, SkillCatalogError


def _write_skill(root: Path, name: str = "research") -> Path:
    directory = root / "brain" / "skills" / name
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\n"
        "description: Verify bounded external facts.\n"
        "---\n"
        "# Procedure\n\n"
        "1. Gather evidence.\n"
        "2. Report uncertainty.\n",
        encoding="utf-8",
    )
    return directory


def test_catalog_progressively_discloses_metadata_then_instructions(tmp_path: Path):
    _write_skill(tmp_path)
    catalog = BundledSkillCatalog(root=tmp_path)

    metadata = catalog.available_skills()
    document = catalog.load("research")

    assert [(item.name, item.description) for item in metadata] == [
        ("research", "Verify bounded external facts.")
    ]
    assert document is not None
    assert "Gather evidence" in document.instructions


def test_catalog_rejects_directory_name_mismatch(tmp_path: Path):
    _write_skill(tmp_path, name="wrong-directory")
    path = tmp_path / "brain" / "skills" / "wrong-directory" / "SKILL.md"
    path.write_text(
        "---\nname: research\ndescription: mismatch\n---\nInstructions\n",
        encoding="utf-8",
    )

    with pytest.raises(SkillCatalogError, match="match its directory"):
        BundledSkillCatalog(root=tmp_path).available_skills()


def test_catalog_is_read_only_and_does_not_execute_optional_files(tmp_path: Path):
    directory = _write_skill(tmp_path)
    (directory / "scripts").mkdir()
    (directory / "scripts" / "run.py").write_text(
        "raise RuntimeError", encoding="utf-8"
    )

    catalog = BundledSkillCatalog(root=tmp_path)

    assert catalog.load("research") is not None
    assert not (directory / "scripts" / "ran.marker").exists()
    assert catalog.load("unknown") is None


def test_catalog_accepts_standard_optional_frontmatter_without_granting_tools(
    tmp_path: Path,
):
    directory = _write_skill(tmp_path)
    (directory / "SKILL.md").write_text(
        "---\n"
        "name: research\n"
        "description: Verify bounded external facts.\n"
        "license: Apache-2.0\n"
        "compatibility: Requires network access through the host Tool.\n"
        "metadata:\n"
        "  author: elfienest\n"
        '  version: "1.0"\n'
        "allowed-tools: web_search\n"
        "---\n"
        "Use the evidence procedure.\n",
        encoding="utf-8",
    )

    document = BundledSkillCatalog(root=tmp_path).load("research")

    assert document is not None
    assert document.name == "research"
    assert not hasattr(document, "allowed_tools")
