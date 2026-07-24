"""防止运行数据边界在后续改动中回退。"""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEVELOPER_PRODUCTION_GUARD_FILES = frozenset({"devtools/elfie_lab/app.py"})
ACTIVE_CHAT_ROUTE_FILES = (
    "app/interfaces/api/chat_persistence.py",
    "app/interfaces/api/user_chat_routes.py",
    "app/interfaces/api/v1/client_routes.py",
    "app/interfaces/api/v1/realtime.py",
    "app/interfaces/api/ws_gateway.py",
)


def test_developer_tools_only_reference_production_home_for_an_explicit_guard() -> None:
    offenders: list[str] = []
    for path in (PROJECT_ROOT / "devtools").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        imports_production_root = "get_elfie_home" in source or "get_db_path" in source
        relative_path = path.relative_to(PROJECT_ROOT).as_posix()
        if imports_production_root and relative_path not in DEVELOPER_PRODUCTION_GUARD_FILES:
            offenders.append(relative_path)

    assert offenders == []


def test_legacy_nest_chat_storage_has_no_runtime_path() -> None:
    offenders = []
    for relative_path in ACTIVE_CHAT_ROUTE_FILES:
        source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        if "chat_messages" in source or "app.infrastructure.persistence.chat_history" in source:
            offenders.append(relative_path)

    assert offenders == []
    assert not (
        PROJECT_ROOT / "app/infrastructure/persistence/chat_history.py"
    ).exists()
    assert not (
        PROJECT_ROOT / "app/infrastructure/persistence/legacy_chat_migration.py"
    ).exists()
    schema_source = (
        PROJECT_ROOT / "app/infrastructure/persistence/schema.py"
    ).read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS chat_messages" not in schema_source


def test_data_home_declares_production_developer_and_elfie_workspace_roots() -> None:
    source_path = PROJECT_ROOT / "ai_runtime" / "storage" / "data_home.py"
    functions = {
        node.name
        for node in ast.walk(ast.parse(source_path.read_text(encoding="utf-8")))
        if isinstance(node, ast.FunctionDef)
    }

    assert {
        "get_elfie_home",
        "get_elfie_developer_home",
        "get_elfie_workspace_dir",
        "get_elfie_conversations_dir",
    } <= functions
