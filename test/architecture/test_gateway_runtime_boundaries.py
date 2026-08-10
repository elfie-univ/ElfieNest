"""Machine contracts for the Gateway rename and Runtime host boundary."""

import ast
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DESKTOP_BOUNDARY_PATHS = (
    PROJECT_ROOT / "desktop",
    PROJECT_ROOT / "app/interfaces/desktop",
)
DESKTOP_SOURCE_SUFFIXES = frozenset({".js", ".jsx", ".py", ".ts", ".tsx"})
GATEWAY_IMPORT_PATTERN = re.compile(
    r"(?:from\s+|import\s*\()[\"']((?:nest\.godot_gateway|"
    r"infrastructure\.godot)(?:\.[^\"']*)?)[\"']"
)


def _imported_modules(path: Path) -> set[str]:
    """Return absolute import module names from one Python source file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def _desktop_source_files() -> tuple[Path, ...]:
    """Find Python and JavaScript-family sources in either Desktop layout."""
    return tuple(
        path
        for root in DESKTOP_BOUNDARY_PATHS
        if root.is_dir()
        for path in root.rglob("*")
        if path.is_file() and path.suffix in DESKTOP_SOURCE_SUFFIXES
    )


def _gateway_internal_imports(path: Path) -> set[str]:
    """Extract direct Gateway imports from a supported Desktop source file."""
    if path.suffix == ".py":
        return {
            module
            for module in _imported_modules(path)
            if module == "nest.godot_gateway"
            or module.startswith("nest.godot_gateway.")
            or module == "infrastructure.godot"
            or module.startswith("infrastructure.godot.")
        }
    return {
        match.group(1)
        for match in GATEWAY_IMPORT_PATTERN.finditer(path.read_text(encoding="utf-8"))
    }


def test_removed_gateway_alias_is_not_restored() -> None:
    # Current migration paths may disappear; the obsolete alias may not return.
    assert not (PROJECT_ROOT / "nest/godot").exists()


def test_runtime_host_does_not_import_nest_business_objects() -> None:
    # Given: the Runtime host selects/launches artifacts rather than Nest business state.
    runtime_roots = (
        PROJECT_ROOT / "godot_runtime",
        PROJECT_ROOT / "infrastructure/godot",
    )

    # When: every Runtime host module is checked for absolute Nest imports.
    offenders = {
        path.relative_to(PROJECT_ROOT).as_posix(): sorted(
            module
            for module in _imported_modules(path)
            if module == "nest" or module.startswith("nest.")
        )
        for runtime_root in runtime_roots
        if runtime_root.is_dir()
        for path in runtime_root.rglob("*.py")
        if any(
            module == "nest" or module.startswith("nest.")
            for module in _imported_modules(path)
        )
    }

    # Then: no Nest business object crosses into the host boundary.
    assert offenders == {}


def test_desktop_interface_does_not_import_gateway_internals() -> None:
    # Given: either current or migrated Desktop may not import Gateway code.
    desktop_sources = _desktop_source_files()

    # When: Python and TypeScript-family Desktop sources are inspected.
    offenders = {
        path.relative_to(PROJECT_ROOT).as_posix(): sorted(
            _gateway_internal_imports(path)
        )
        for path in desktop_sources
        if _gateway_internal_imports(path)
    }

    # Then: protocol internals remain behind the Gateway boundary.
    assert desktop_sources
    assert offenders == {}


def test_desktop_boundary_scanner_rejects_gateway_import_fixture(
    tmp_path: Path,
) -> None:
    # Given: a Desktop adapter reaches into a Gateway implementation directly.
    fixture = tmp_path / "desktop_adapter.py"
    fixture.write_text(
        "from nest.godot_gateway.api import GodotAPIServer\n", encoding="utf-8"
    )

    # When: the shared Desktop boundary scanner analyzes the adapter.
    imports = _gateway_internal_imports(fixture)

    # Then: the forbidden protocol import is reported for the architecture guard.
    assert imports == {"nest.godot_gateway.api"}
