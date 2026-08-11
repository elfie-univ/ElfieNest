"""防止运行数据边界在后续改动中回退。"""

from __future__ import annotations

import ast
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEVELOPER_PRODUCTION_GUARD_FILES = frozenset({"devtools/elfie_lab/app.py"})
ACTIVE_CHAT_ROUTE_FILES = (
    "app/interfaces/api/v1/me/conversations/routes.py",
    "app/interfaces/api/v1/realtime/chat/routes.py",
    "app/interfaces/api/ws_gateway_messaging.py",
)
LEGACY_CHAT_INTERFACE_FILES = (
    "app/interfaces/api/v1/realtime_chat_models.py",
    "app/interfaces/api/v1/realtime_chat_routes.py",
)
APPLICATION_SQL_ROOTS = (
    "app/bootstrap",
    "app/features",
    "app/interfaces",
    "app/orchestration",
)
GENERATED_DIRECTORY_NAMES = frozenset(
    {".git", ".venv", "__pycache__", "build", "dist", "node_modules"}
)
SQL_LITERAL_PATTERN = re.compile(
    r"\b(?:SELECT|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|"
    r"CREATE\s+TABLE|ALTER\s+TABLE|DROP\s+TABLE|PRAGMA\s+\w+|"
    r"BEGIN\s+(?:DEFERRED|IMMEDIATE|EXCLUSIVE))\b",
    re.IGNORECASE,
)


def test_developer_tools_only_reference_production_home_for_an_explicit_guard() -> None:
    offenders: list[str] = []
    for path in (PROJECT_ROOT / "devtools").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        imports_production_root = "get_elfie_home" in source or "get_db_path" in source
        relative_path = path.relative_to(PROJECT_ROOT).as_posix()
        if (
            imports_production_root
            and relative_path not in DEVELOPER_PRODUCTION_GUARD_FILES
        ):
            offenders.append(relative_path)

    assert offenders == []


def test_legacy_nest_chat_storage_has_no_runtime_path() -> None:
    offenders = []
    for relative_path in ACTIVE_CHAT_ROUTE_FILES:
        path = PROJECT_ROOT / relative_path
        if not path.is_file():
            continue
        source = path.read_text(encoding="utf-8")
        if (
            "chat_messages" in source
            or "app.infrastructure.persistence.chat_history" in source
        ):
            offenders.append(relative_path)

    assert offenders == []
    assert all(
        not (PROJECT_ROOT / relative_path).exists()
        for relative_path in LEGACY_CHAT_INTERFACE_FILES
    )
    assert not (
        PROJECT_ROOT / "app/infrastructure/persistence/chat_history.py"
    ).exists()
    assert not (
        PROJECT_ROOT / "app/infrastructure/persistence/legacy_chat_migration.py"
    ).exists()
    assert not (PROJECT_ROOT / "app/infrastructure/persistence/schema.py").exists()
    assert not (PROJECT_ROOT / "app/infrastructure/persistence/nest_schema.py").exists()
    graph_storage = PROJECT_ROOT / "elfie/brain/memory/graph_storage.py"
    if graph_storage.is_file():
        assert "graph_memory.db" not in graph_storage.read_text(encoding="utf-8")


def test_data_home_declares_production_developer_and_elfie_workspace_roots() -> None:
    source_path = PROJECT_ROOT / "infrastructure/persistence/data_home.py"
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
        "get_configs_dir",
        "get_credentials_dir",
        "get_oauth_credentials_dir",
        "get_provider_catalog_path",
        "get_provider_config_path",
        "get_reports_dir",
        "get_report_database_path",
        "get_report_exports_dir",
        "get_runtime_config_paths",
        "get_tool_config_path",
    } <= functions
    assert not (PROJECT_ROOT / "ai_runtime/storage/data_home.py").exists()
    assert not (PROJECT_ROOT / "ai_runtime/storage/data_layout.py").exists()


def test_application_layers_do_not_own_sql() -> None:
    offenders: list[str] = []
    for relative_root in APPLICATION_SQL_ROOTS:
        for path in (PROJECT_ROOT / relative_root).rglob("*.py"):
            if GENERATED_DIRECTORY_NAMES.intersection(path.parts):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            has_sql = any(
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and SQL_LITERAL_PATTERN.search(node.value) is not None
                for node in ast.walk(tree)
            )
            imports_sqlite = any(
                (
                    isinstance(node, ast.Import)
                    and any(alias.name == "sqlite3" for alias in node.names)
                )
                or (isinstance(node, ast.ImportFrom) and node.module == "sqlite3")
                for node in ast.walk(tree)
            )
            if has_sql or imports_sqlite:
                offenders.append(path.relative_to(PROJECT_ROOT).as_posix())

    assert offenders == []


def test_application_layers_do_not_derive_data_home_from_database_paths() -> None:
    offenders: list[str] = []
    for relative_root in APPLICATION_SQL_ROOTS:
        for path in (PROJECT_ROOT / relative_root).rglob("*.py"):
            if GENERATED_DIRECTORY_NAMES.intersection(path.parts):
                continue
            source = path.read_text(encoding="utf-8")
            if re.search(
                r"Path\([^)]*(?:db_path|database_path)[^)]*\)"
                r"(?:\.expanduser\(\)|\.resolve\(\))*\.parent",
                source,
            ):
                offenders.append(path.relative_to(PROJECT_ROOT).as_posix())

    assert offenders == []
