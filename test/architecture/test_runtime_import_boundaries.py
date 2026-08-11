"""Prevent non-orchestration application layers from taking Runtime control."""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NON_ORCHESTRATION_APP_ROOTS = (
    PROJECT_ROOT / "app" / "interfaces",
    PROJECT_ROOT / "app" / "features",
    PROJECT_ROOT / "app" / "infrastructure",
)
PUBLIC_GATEWAY_IMPORTS = frozenset(
    {
        "infrastructure.godot.gateway.bundle",
        "nest.godot_gateway.observer",
    }
)


def _runtime_imports(path: Path) -> set[str]:
    """Return authority-host and Godot Gateway imports from one source file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module)
    return {
        module
        for module in imports
        if module == "godot_runtime"
        or module.startswith("godot_runtime.")
        or module == "nest.godot_gateway"
        or module.startswith("nest.godot_gateway.")
        or module == "infrastructure.godot"
        or module.startswith("infrastructure.godot.")
    }


def test_non_orchestration_app_layers_do_not_take_runtime_control() -> None:
    """Keep authority hosting and raw protocol control inside orchestration."""
    # Given: interfaces, features and infrastructure may need only public read APIs.
    sources = tuple(
        path for root in NON_ORCHESTRATION_APP_ROOTS for path in root.rglob("*.py")
    )

    # When: their imports are compared with the narrow read-only Gateway allowlist.
    offenders = {
        path.relative_to(PROJECT_ROOT).as_posix(): sorted(
            module
            for module in _runtime_imports(path)
            if module not in PUBLIC_GATEWAY_IMPORTS
        )
        for path in sources
        if {
            module
            for module in _runtime_imports(path)
            if module not in PUBLIC_GATEWAY_IMPORTS
        }
    }

    # Then: none may import an authority host or raw Gateway protocol implementation.
    assert offenders == {}


def test_runtime_import_scanner_flags_raw_protocol_control(tmp_path: Path) -> None:
    """Reject a direct Gateway protocol import outside orchestration."""
    # Given: an interface implementation tries to import a raw protocol frame.
    source = tmp_path / "runtime_route.py"
    source.write_text(
        "from infrastructure.godot.gateway.messages import RuntimeEventFrame\n",
        encoding="utf-8",
    )

    # When: the boundary scanner inspects the source.
    imports = _runtime_imports(source)

    # Then: the import is recognized as non-public Runtime control.
    assert imports - PUBLIC_GATEWAY_IMPORTS == {"infrastructure.godot.gateway.messages"}
