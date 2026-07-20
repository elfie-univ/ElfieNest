import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

REQUIRED_ROOT_DIRECTORIES = frozenset(
    {
        "ai_runtime",
        "app",
        "desktop",
        "devtools",
        "docs",
        "elfie",
        "godot",
        "nest",
        "scripts",
        "test",
    }
)
FORBIDDEN_SOURCE_DIRECTORIES = frozenset({"elfienest", "runtime"})
REQUIRED_APP_DIRECTORIES = frozenset(
    {"bootstrap", "features", "infrastructure", "interfaces", "orchestration"}
)
REQUIRED_NEST_ENTRIES = frozenset(
    {"__init__.py", "engine", "events.py", "godot", "interaction", "nest.py", "state"}
)
REQUIRED_DESKTOP_SOURCE_DIRECTORIES = frozenset(
    {"platform", "resources", "supervisor", "windows"}
)


def test_target_root_directories_exist() -> None:
    # Given
    existing = {path.name for path in PROJECT_ROOT.iterdir() if path.is_dir()}

    # When
    missing = REQUIRED_ROOT_DIRECTORIES - existing

    # Then
    assert missing == frozenset()


def test_legacy_source_directories_are_removed() -> None:
    # Given
    existing = {path.name for path in PROJECT_ROOT.iterdir() if path.is_dir()}

    # When
    legacy = FORBIDDEN_SOURCE_DIRECTORIES & existing

    # Then
    assert legacy == frozenset()


def test_app_and_nest_have_the_confirmed_secondary_structure() -> None:
    # Given
    app_entries = {path.name for path in (PROJECT_ROOT / "app").iterdir()}
    nest_entries = {path.name for path in (PROJECT_ROOT / "nest").iterdir()}

    # When
    missing_app_entries = REQUIRED_APP_DIRECTORIES - app_entries
    missing_nest_entries = REQUIRED_NEST_ENTRIES - nest_entries

    # Then
    assert missing_app_entries == frozenset()
    assert missing_nest_entries == frozenset()


def test_desktop_source_has_the_confirmed_secondary_structure() -> None:
    # Given
    source_entries = {
        path.name for path in (PROJECT_ROOT / "desktop" / "src").iterdir() if path.is_dir()
    }

    # When
    missing = REQUIRED_DESKTOP_SOURCE_DIRECTORIES - source_entries

    # Then
    assert missing == frozenset()


def test_python_sources_do_not_import_legacy_packages() -> None:
    # Given
    source_roots = (
        PROJECT_ROOT / "ai_runtime",
        PROJECT_ROOT / "app",
        PROJECT_ROOT / "devtools",
        PROJECT_ROOT / "elfie",
        PROJECT_ROOT / "nest",
        PROJECT_ROOT / "scripts",
        PROJECT_ROOT / "test",
    )
    forbidden_packages = frozenset({"elfienest", "runtime"})

    # When
    offenders = []
    for source_root in source_roots:
        if not source_root.exists():
            continue
        for path in source_root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imported_roots = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module is not None:
                    imported_roots.add(node.module.split(".", 1)[0])
            if imported_roots & forbidden_packages:
                offenders.append(path.relative_to(PROJECT_ROOT).as_posix())

    # Then
    assert offenders == []
