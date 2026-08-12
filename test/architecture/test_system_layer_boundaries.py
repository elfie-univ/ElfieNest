"""Machine gates for the repository-wide system architecture contract."""

from __future__ import annotations

from pathlib import Path

from scripts.architecture.check_governance_change import classify_paths
from scripts.architecture.system_layer_scan import (
    RULE_NAMES,
    collect_system_layer_violations,
    deny_all_failures,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_system_scanner_permanently_denies_all_current_debt() -> None:
    current = collect_system_layer_violations(PROJECT_ROOT)
    assert set(current) == set(RULE_NAMES)
    assert deny_all_failures(current) == []


def test_system_deny_all_accepts_zero_and_rejects_any_violation() -> None:
    empty = {rule: frozenset() for rule in RULE_NAMES}
    assert deny_all_failures(empty) == []
    assert deny_all_failures({"rule": frozenset({"path -> dependency"})}) == [
        "rule: violations are forbidden in deny-all mode: ['path -> dependency']"
    ]


def test_system_scanner_catches_core_boundary_fixtures(tmp_path: Path) -> None:
    elfie = tmp_path / "elfie"
    nest = tmp_path / "nest"
    elfie.mkdir()
    nest.mkdir()
    (elfie / "bad.py").write_text(
        "import sqlite3\nfrom app.bootstrap import container\n",
        encoding="utf-8",
    )
    (nest / "bad.py").write_text(
        "import websockets\nfrom elfie import Elfie\n",
        encoding="utf-8",
    )

    violations = collect_system_layer_violations(tmp_path)
    assert violations["elfie_technical_imports"] == frozenset(
        {"elfie/bad.py -> sqlite3"}
    )
    assert violations["elfie_forbidden_module_imports"] == frozenset(
        {"elfie/bad.py -> app.bootstrap"}
    )
    assert violations["nest_technical_imports"] == frozenset(
        {"nest/bad.py -> websockets"}
    )
    assert violations["nest_forbidden_module_imports"] == frozenset(
        {"nest/bad.py -> elfie"}
    )


def test_system_contract_decision_and_agents_exist_in_both_languages() -> None:
    english_contract = (PROJECT_ROOT / "docs/developer/contracts/system.md").read_text(
        encoding="utf-8"
    )
    chinese_contract = (
        PROJECT_ROOT / "docs/zh/developer/contracts/system.md"
    ).read_text(encoding="utf-8")
    required_docs = {
        "docs/developer/decisions/0002-system-ports-adapters.md",
        "docs/zh/developer/decisions/0002-system-ports-adapters.md",
        "docs/developer/decisions/0009-zero-debt-governance-closure.md",
        "docs/zh/developer/decisions/0009-zero-debt-governance-closure.md",
        "docs/developer/decisions/0012-effective-dependency-targets.md",
        "docs/zh/developer/decisions/0012-effective-dependency-targets.md",
    }
    required_agents = {
        "elfie/AGENTS.md",
        "nest/AGENTS.md",
        "infrastructure/AGENTS.md",
        "infrastructure/persistence/AGENTS.md",
        "infrastructure/godot/AGENTS.md",
        "godot_project/AGENTS.md",
    }

    assert "**Contract version:** 1.5" in english_contract
    assert "**契约版本：** 1.5" in chinese_contract
    assert "**Macro architecture baseline:** v1 (frozen)" in english_contract
    assert "**宏观架构基线：** v1（已冻结）" in chinese_contract
    assert "always has exactly one Nest" in english_contract
    assert "永远只有一个精灵巢" in chinese_contract
    assert "facade can itself be an inbound Port" in english_contract
    assert "Facade 本身就可以承担入站 Port" in chinese_contract
    assert "There is no target AI Runtime module" in english_contract
    assert "目标架构不存在 AI Runtime 模块" in chinese_contract
    assert (
        "`godot_project/` remains a separate Godot source project" in english_contract
    )
    assert "`godot_project/` 永久保持为独立 Godot 源工程" in chinese_contract
    assert "ordinary Food lookup, model call" in english_contract
    assert "单只精灵通过注入 Port 读取" in chinese_contract
    assert all((PROJECT_ROOT / path).is_file() for path in required_docs)
    assert all((PROJECT_ROOT / path).is_file() for path in required_agents)
    assert not (PROJECT_ROOT / "app/infrastructure").exists()


def test_root_infrastructure_source_is_classified_as_production() -> None:
    governance, production = classify_paths(
        {
            "docs/developer/contracts/system.md",
            "infrastructure/persistence/sqlite_adapter.py",
        }
    )
    assert governance == {"docs/developer/contracts/system.md"}
    assert production == {"infrastructure/persistence/sqlite_adapter.py"}


def test_every_non_document_file_under_production_roots_is_product_source() -> None:
    governance, production = classify_paths(
        {
            "app/config/runtime.yaml",
            "elfie/assets/body.glb",
            "godot_project/main.tscn",
            "nest/README.md",
        }
    )
    assert governance == set()
    assert production == {
        "app/config/runtime.yaml",
        "elfie/assets/body.glb",
        "godot_project/main.tscn",
    }
