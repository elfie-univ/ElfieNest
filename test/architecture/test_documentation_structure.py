"""Machine gates for the public documentation information architecture."""

from __future__ import annotations

from pathlib import Path
from typing import Set

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCS_ROOT = PROJECT_ROOT / "docs"
PUBLIC_SECTIONS = {"story", "user-guide", "developer"}
DEVELOPER_REQUIRED_CATEGORIES = {
    "architecture",
    "contracts",
    "conformance",
    "decisions",
    "engineering",
}
DEVELOPER_OPTIONAL_CATEGORIES = {"designs"}
ROOT_TECHNICAL_DIRECTORIES = {
    ".internal",
    ".vitepress",
    "node_modules",
    "public",
    "scripts",
    "zh",
}
INTERNAL_TOP_LEVEL_DIRECTORIES = {"elfaria", "product", "drafts"}


def _directory_names(root: Path) -> Set[str]:
    return {path.name for path in root.iterdir() if path.is_dir()}


def _public_markdown_pages(root: Path) -> Set[str]:
    pages = {"index.md"} if (root / "index.md").is_file() else set()
    for section in PUBLIC_SECTIONS:
        section_root = root / section
        pages.update(
            path.relative_to(root).as_posix() for path in section_root.rglob("*.md")
        )
    return pages


def test_public_sections_and_legacy_paths_are_fixed() -> None:
    english_sections = _directory_names(DOCS_ROOT) - ROOT_TECHNICAL_DIRECTORIES
    chinese_sections = _directory_names(DOCS_ROOT / "zh")

    assert english_sections == PUBLIC_SECTIONS
    assert chinese_sections == PUBLIC_SECTIONS
    assert not (DOCS_ROOT / "getting-started").exists()
    assert not (DOCS_ROOT / "zh" / "getting-started").exists()


def test_developer_categories_are_direct_and_bilingual() -> None:
    english_root = DOCS_ROOT / "developer"
    chinese_root = DOCS_ROOT / "zh" / "developer"
    english_categories = _directory_names(english_root)
    chinese_categories = _directory_names(chinese_root)
    allowed = DEVELOPER_REQUIRED_CATEGORIES | DEVELOPER_OPTIONAL_CATEGORIES

    assert DEVELOPER_REQUIRED_CATEGORIES <= english_categories <= allowed
    assert chinese_categories == english_categories
    assert {path.name for path in english_root.glob("*.md")} == {"index.md"}
    assert {path.name for path in chinese_root.glob("*.md")} == {"index.md"}


def test_public_markdown_pages_have_language_mirrors() -> None:
    assert _public_markdown_pages(DOCS_ROOT) == _public_markdown_pages(DOCS_ROOT / "zh")


def test_internal_documents_have_only_the_three_flat_roots() -> None:
    internal_root = DOCS_ROOT / ".internal"

    assert _directory_names(internal_root) == INTERNAL_TOP_LEVEL_DIRECTORIES
    assert (internal_root / "AGENTS.md").is_file()

    for directory_name in INTERNAL_TOP_LEVEL_DIRECTORIES:
        directory = internal_root / directory_name
        assert directory.is_dir()
        assert all(path.parent == directory for path in directory.rglob("*.md")), (
            directory
        )


def test_design_documents_use_the_lazy_owner_hierarchy() -> None:
    expected_brain_docs = {
        "elfie-brain-evaluation-system.md",
        "elfie-brain-ten-system-architecture.md",
        "elfie-emotion-system.md",
        "elfie-memory-architecture.md",
        "elfie-reasoning-core.md",
        "elfie-selfhood-and-fixed-model-header.md",
    }

    for language_root, relation_heading in (
        (DOCS_ROOT, "Design relations:"),
        (DOCS_ROOT / "zh", "设计关系："),
    ):
        design_root = language_root / "developer" / "designs"
        assert {path.name for path in design_root.iterdir() if path.is_dir()} == {
            "app",
            "elfie",
        }
        assert {path.name for path in design_root.glob("*.md")} == {
            "AGENTS.md",
            "index.md",
            "nest-godot-virtual-world-functional-architecture.md",
            "provider-model-availability.md",
        }
        assert {path.name for path in (design_root / "app").glob("*.md")} == {
            "native-release-validation.md",
            "service-lifecycle-state-machine.md",
        }
        assert {path.name for path in (design_root / "elfie").glob("*.md")} == {
            "elfie-top-level-module-design.md",
            "virtual-appearance-generation.md",
        }
        assert {
            path.name for path in (design_root / "elfie" / "brain").glob("*.md")
        } == expected_brain_docs
        assert {
            path.relative_to(design_root).as_posix()
            for path in design_root.rglob("index.md")
        } == {"index.md"}

        forbidden_empty_branches = (
            "system",
            "infrastructure",
            "nest",
            "elfie/communication",
            "elfie/genesis",
            "elfie/embodiment",
        )
        assert all(
            not (design_root / branch).exists() for branch in forbidden_empty_branches
        )

        design_docs = (
            design_root / "provider-model-availability.md",
            design_root / "nest-godot-virtual-world-functional-architecture.md",
            design_root / "app" / "native-release-validation.md",
            design_root / "app" / "service-lifecycle-state-machine.md",
            design_root / "elfie" / "elfie-top-level-module-design.md",
            design_root / "elfie" / "virtual-appearance-generation.md",
            *(design_root / "elfie" / "brain").glob("*.md"),
        )
        assert all(
            relation_heading in path.read_text(encoding="utf-8") for path in design_docs
        )


def test_public_content_directories_are_not_empty() -> None:
    for language_root in (DOCS_ROOT, DOCS_ROOT / "zh"):
        for section in PUBLIC_SECTIONS:
            for directory in (language_root / section).rglob("*"):
                if directory.is_dir():
                    assert any(directory.iterdir()), directory


def test_vitepress_navigation_uses_the_protected_paths() -> None:
    config = (DOCS_ROOT / ".vitepress" / "config.mts").read_text(encoding="utf-8")
    required_paths = {
        'link: "/user-guide/"',
        'link: "/zh/user-guide/"',
        'link: "/developer/architecture/"',
        'link: "/developer/contracts/"',
        'link: "/developer/conformance/elfie"',
        'link: "/developer/decisions/"',
        'link: "/developer/engineering/quality-governance"',
        'link: "/developer/designs/elfie/brain/elfie-memory-architecture"',
        'link: "/developer/designs/elfie/brain/elfie-reasoning-core"',
        'link: "/developer/designs/app/service-lifecycle-state-machine"',
        'link: "/developer/designs/nest-godot-virtual-world-functional-architecture"',
        'link: "/developer/designs/elfie/elfie-top-level-module-design"',
        'link: "/developer/designs/elfie/virtual-appearance-generation"',
        'link: "/zh/developer/architecture/"',
        'link: "/zh/developer/contracts/"',
        'link: "/zh/developer/conformance/elfie"',
        'link: "/zh/developer/decisions/"',
        'link: "/zh/developer/engineering/quality-governance"',
        'link: "/zh/developer/designs/elfie/brain/elfie-memory-architecture"',
        'link: "/zh/developer/designs/elfie/brain/elfie-reasoning-core"',
        'link: "/zh/developer/designs/app/service-lifecycle-state-machine"',
        'link: "/zh/developer/designs/nest-godot-virtual-world-functional-architecture"',
        'link: "/zh/developer/designs/elfie/elfie-top-level-module-design"',
        'link: "/zh/developer/designs/elfie/virtual-appearance-generation"',
    }

    assert all(path in config for path in required_paths)
    assert "/getting-started" not in config


def test_developer_sidebar_preserves_category_hierarchy() -> None:
    config = (DOCS_ROOT / ".vitepress" / "config.mts").read_text(encoding="utf-8")
    english_categories = (
        'text: "Designs",\n                  collapsed: true',
        'text: "Contracts",\n                  collapsed: true',
        'text: "Conformance",\n                  collapsed: true',
        'text: "Decisions (ADRs)",\n                  collapsed: true',
        'text: "Engineering",\n              collapsed: true',
    )
    chinese_categories = (
        'text: "设计文档",\n                  collapsed: true',
        'text: "架构契约",\n                  collapsed: true',
        'text: "架构一致性",\n                  collapsed: true',
        'text: "架构决策记录（ADR）",\n                  collapsed: true',
        'text: "工程实践",\n              collapsed: true',
    )

    assert all(category in config for category in english_categories)
    assert all(category in config for category in chinese_categories)
