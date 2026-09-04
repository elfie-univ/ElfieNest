"""Permanent architecture gates for the two-root configuration contract."""

from __future__ import annotations

import ast
from pathlib import Path

from infrastructure.persistence.configuration.documents import (
    CONFIG_DOCUMENTS,
    BundledConfigSource,
    ConfigDocumentId,
    ConfigPolicy,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BUNDLED_ROOT = PROJECT_ROOT / "config"
DYNAMIC_PACKAGE_ROOT = BUNDLED_ROOT / "species"
SKILL_RESOURCE_ROOT = BUNDLED_ROOT / "brain" / "skills"


def _python_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module)
    return modules


def test_bundled_root_is_exactly_the_registered_document_inventory() -> None:
    registered = {
        spec.bundled_relative_path
        for spec in CONFIG_DOCUMENTS.values()
        if spec.required_bundled
    }
    actual = {
        path.relative_to(BUNDLED_ROOT).as_posix()
        for path in BUNDLED_ROOT.rglob("*")
        if path.is_file()
        and (
            path.relative_to(BUNDLED_ROOT).as_posix() == "species/catalog.yaml"
            or (
                DYNAMIC_PACKAGE_ROOT not in path.parents
                and SKILL_RESOURCE_ROOT not in path.parents
            )
        )
    }

    assert None not in registered
    assert actual == registered
    # Standard SKILL.md resources use their own frontmatter/catalog loader;
    # they are not YAML configuration documents in CONFIG_DOCUMENTS.
    assert (SKILL_RESOURCE_ROOT / "research" / "SKILL.md").is_file()
    # Species package members are intentionally discovered from the registered
    # catalog. Requiring each future species file to become a closed document
    # ID would defeat configuration-only species onboarding.
    assert (DYNAMIC_PACKAGE_ROOT / "catalog.yaml").is_file()


def test_every_required_bundled_document_loads_through_the_closed_registry() -> None:
    source = BundledConfigSource(BUNDLED_ROOT)

    for document_id, spec in CONFIG_DOCUMENTS.items():
        if not spec.required_bundled:
            continue
        loaded = source.load(document_id)
        assert loaded.spec.document_id is document_id
        assert loaded.document["version"] == spec.version


def test_registry_policy_keeps_user_only_and_bundled_only_documents_separate() -> None:
    for spec in CONFIG_DOCUMENTS.values():
        if spec.policy is ConfigPolicy.BUNDLED_ONLY:
            assert spec.bundled_relative_path is not None
            assert spec.user_relative_path is None
        if spec.policy is ConfigPolicy.USER_ONLY:
            assert spec.bundled_relative_path is None
            assert spec.user_relative_path is not None

    assert CONFIG_DOCUMENTS[ConfigDocumentId.AUTH_ENV].bundled_relative_path is None
    assert (
        CONFIG_DOCUMENTS[ConfigDocumentId.PROVIDER_CONNECTIONS].bundled_relative_path
        is None
    )


def test_provider_and_model_catalogs_keep_the_registered_config_root() -> None:
    assert (
        CONFIG_DOCUMENTS[ConfigDocumentId.PROVIDER_CATALOG].bundled_relative_path
        == "models/provider-catalog.yaml"
    )
    assert (
        CONFIG_DOCUMENTS[ConfigDocumentId.MODEL_CATALOG].bundled_relative_path
        == "models/model-catalog.yaml"
    )
    assert (BUNDLED_ROOT / "models/provider-catalog.yaml").is_file()
    assert (BUNDLED_ROOT / "models/model-catalog.yaml").is_file()


def test_old_package_local_bundled_configuration_locations_are_gone() -> None:
    old_paths = (
        "elfie/brain/emotion/emotion_expressions.yaml",
        "elfie/brain/energy/defaults.yaml",
        "elfie/brain/selfhood/defaults.yaml",
        "infrastructure/models/providers/provider-catalog.yaml",
        "infrastructure/models/providers/model-catalog.yaml",
    )

    assert [path for path in old_paths if (PROJECT_ROOT / path).exists()] == []


def test_business_and_domain_layers_do_not_import_configuration_io() -> None:
    source_roots = (
        PROJECT_ROOT / "app" / "features",
        PROJECT_ROOT / "app" / "interfaces",
        PROJECT_ROOT / "app" / "orchestration",
        PROJECT_ROOT / "elfie",
        PROJECT_ROOT / "nest",
    )
    forbidden = {
        "yaml",
        "infrastructure.persistence.configuration",
        "infrastructure.persistence.configuration.config_store",
        "infrastructure.persistence.configuration.documents",
    }
    offenders: list[tuple[str, list[str]]] = []
    for root in source_roots:
        for path in root.rglob("*.py"):
            imports = _python_imports(path)
            matched = sorted(
                module
                for module in imports
                if module in forbidden
                or module.startswith("infrastructure.persistence.configuration.")
            )
            if matched:
                offenders.append((path.relative_to(PROJECT_ROOT).as_posix(), matched))

    assert offenders == []


def test_non_infrastructure_layers_contain_no_global_yaml_documents() -> None:
    source_roots = (
        PROJECT_ROOT / "app" / "features",
        PROJECT_ROOT / "app" / "orchestration",
        PROJECT_ROOT / "elfie",
        PROJECT_ROOT / "nest",
    )
    yaml_files = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for root in source_roots
        for path in root.rglob("*")
        if path.is_file() and path.suffix in {".yaml", ".yml"}
    ]

    assert yaml_files == []


def test_model_catalog_values_are_not_redeclared_as_python_literals() -> None:
    path = PROJECT_ROOT / "infrastructure" / "models" / "catalog.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    literal_entries: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "ModelEntry":
            continue
        model_id = next(
            (keyword.value for keyword in node.keywords if keyword.arg == "model_id"),
            None,
        )
        if isinstance(model_id, ast.Constant) and isinstance(model_id.value, str):
            literal_entries.append(model_id.value)

    assert literal_entries == []


def test_configuration_contract_freezes_genesis_source_ownership() -> None:
    english = (
        PROJECT_ROOT / "docs/developer/contracts/configuration-management.md"
    ).read_text(encoding="utf-8")
    chinese = (
        PROJECT_ROOT / "docs/zh/developer/contracts/configuration-management.md"
    ).read_text(encoding="utf-8")
    conformance = (
        PROJECT_ROOT / "docs/developer/conformance/configuration-management.md"
    ).read_text(encoding="utf-8")
    species_english = (
        PROJECT_ROOT / "docs/developer/contracts/species-asset-package.md"
    ).read_text(encoding="utf-8")
    species_chinese = (
        PROJECT_ROOT / "docs/zh/developer/contracts/species-asset-package.md"
    ).read_text(encoding="utf-8")
    english_normalized = " ".join(english.split())
    chinese_normalized = " ".join(chinese.split())
    species_english_normalized = " ".join(species_english.split())
    species_chinese_normalized = " ".join(species_chinese.split())

    assert "**Contract version:** 1.4" in english
    assert "**契约版本：** 1.4" in chinese
    assert "world/elfaria.yaml" in english
    assert (
        "Profile receives only the final generated dossier fields" in english_normalized
    )
    assert "Profile 只接收最终生成的档案字段" in chinese_normalized
    assert (
        "runtime asset view separately from the Genesis creation projection" in english
    )
    assert "运行时资产 View 与 Genesis 创建投影分开暴露" in chinese_normalized
    assert "second hard-coded Profile Canon" in english_normalized
    assert "第二份硬编码 Profile Canon" in chinese_normalized
    assert "| CFG-005 | P0 | closed (v0.2 structural) |" in conformance
    assert "Status: normative, version 3" in species_english_normalized
    assert "状态：规范性契约，版本 3" in species_chinese_normalized
    assert "Profile receives neither catalog nor package" in species_english_normalized
    assert "Profile 不接收目录或资料包" in species_chinese_normalized
