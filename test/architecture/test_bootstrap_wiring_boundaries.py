"""Bootstrap composition scopes are peers, not a dependency layer."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _imports_under(relative_root: str) -> set[str]:
    imports: set[str] = set()
    root = PROJECT_ROOT / relative_root
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
    return imports


def test_bootstrap_has_two_peer_wiring_scopes() -> None:
    app_imports = _imports_under("app/bootstrap/app_wiring")
    system_imports = _imports_under("app/bootstrap/system_wiring")

    assert not any(
        name == "app.bootstrap.system_wiring"
        or name.startswith("app.bootstrap.system_wiring.")
        for name in app_imports
    )
    assert not any(
        name == "app.bootstrap.app_wiring"
        or name.startswith("app.bootstrap.app_wiring.")
        for name in system_imports
    )


def test_bootstrap_wiring_scopes_exist_without_speculative_runtime_aliases() -> None:
    assert (PROJECT_ROOT / "app/bootstrap/app_wiring").is_dir()
    assert (PROJECT_ROOT / "app/bootstrap/system_wiring").is_dir()
    assert not (PROJECT_ROOT / "app/bootstrap/application").exists()
    assert not (PROJECT_ROOT / "app/bootstrap/system").exists()


def test_production_entrypoints_use_bootstrap_instead_of_infrastructure_imports() -> (
    None
):
    for relative_path in (
        "scripts/elfienest.py",
        "scripts/serve.py",
        "scripts/chat_with_elfie.py",
    ):
        source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        imported.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        assert not any(name.startswith("infrastructure") for name in imported)
        assert not any(name.startswith("devtools") for name in imported)
