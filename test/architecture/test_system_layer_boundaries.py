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
    english_nest_contract = (
        PROJECT_ROOT / "docs/developer/contracts/nest-godot-semantic-world.md"
    ).read_text(encoding="utf-8")
    chinese_nest_contract = (
        PROJECT_ROOT / "docs/zh/developer/contracts/nest-godot-semantic-world.md"
    ).read_text(encoding="utf-8")
    english_nest_migration = (
        PROJECT_ROOT
        / "docs/developer/conformance/nest-godot-semantic-world-migration.md"
    ).read_text(encoding="utf-8")
    chinese_nest_migration = (
        PROJECT_ROOT
        / "docs/zh/developer/conformance/nest-godot-semantic-world-migration.md"
    ).read_text(encoding="utf-8")
    required_docs = {
        "docs/developer/decisions/0002-system-ports-adapters.md",
        "docs/zh/developer/decisions/0002-system-ports-adapters.md",
        "docs/developer/decisions/0009-zero-debt-governance-closure.md",
        "docs/zh/developer/decisions/0009-zero-debt-governance-closure.md",
        "docs/developer/decisions/0012-effective-dependency-targets.md",
        "docs/zh/developer/decisions/0012-effective-dependency-targets.md",
        "docs/developer/decisions/0013-nest-godot-semantic-world-boundary.md",
        "docs/zh/developer/decisions/0013-nest-godot-semantic-world-boundary.md",
    }
    required_agents = {
        "elfie/AGENTS.md",
        "nest/AGENTS.md",
        "infrastructure/AGENTS.md",
        "infrastructure/persistence/AGENTS.md",
        "infrastructure/godot/AGENTS.md",
        "godot_project/AGENTS.md",
    }

    assert "**Contract version:** 1.6" in english_contract
    assert "**契约版本：** 1.6" in chinese_contract
    assert "**Contract version:** 1.0" in english_nest_contract
    assert "**契约版本：** 1.0" in chinese_nest_contract
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
    assert "Nest has four first-level functional owners" in english_nest_contract
    assert "Nest 有四个一级功能所有者" in chinese_nest_contract
    assert "is not a fifth business module" in english_nest_contract
    assert "不是第五个业务模块" in chinese_nest_contract
    assert "Broadcast is an audience shape" in english_nest_contract
    assert "广播只是" in chinese_nest_contract
    migration_cards = [f"NG-M{index:02d}" for index in range(1, 16)]
    assert all(card in english_nest_migration for card in migration_cards)
    assert all(card in chinese_nest_migration for card in migration_cards)
    assert "DATA-01" in english_nest_migration
    assert "DATA-01" in chinese_nest_migration
    assert "One active migration card" in english_nest_migration
    assert "同一时间只做一张迁移卡" in chinese_nest_migration
    assert "Replace protocol v2 with one clean protocol v3 cutover" in (
        english_nest_migration
    )
    assert "协议 v2 干净切换到 v3" in chinese_nest_migration
    assert "`InteractionHub` only now" in english_nest_migration
    assert "才在本卡删除 `InteractionHub`" in chinese_nest_migration
    assert "No compatibility architecture" in english_nest_migration
    assert "禁止兼容架构" in chinese_nest_migration
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
