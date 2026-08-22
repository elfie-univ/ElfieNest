import ast
from pathlib import Path

import yaml

from scripts.check_quality_baseline import (
    MYPY_SOURCE_ROOT_CANDIDATES,
    MYPY_SOURCE_ROOTS,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

REQUIRED_ROOT_DIRECTORIES = frozenset(
    {
        "app",
        "devtools",
        "docs",
        "elfie",
        "godot_project",
        "infrastructure",
        "nest",
    }
    | {"scripts", "test"}
)
FORBIDDEN_SOURCE_DIRECTORIES = frozenset(
    {"ai_runtime", "desktop", "elfienest", "godot", "godot_runtime", "runtime"}
)
FORBIDDEN_ELFIE_DIRECTORIES = frozenset({"state"})
REQUIRED_APP_DIRECTORIES = frozenset(
    {"bootstrap", "features", "interfaces", "orchestration"}
)
REQUIRED_APP_INTERFACE_DIRECTORIES = frozenset({"api", "cli", "desktop", "web"})
REQUIRED_NEST_ENTRIES = frozenset(
    {
        "__init__.py",
        "config.py",
        "elfie_interaction",
        "events.py",
        "living_rules",
        "nest.py",
        "public.py",
        "snapshot.py",
        "space_facilities",
        "time_environment",
    }
)
FORBIDDEN_NEST_DIRECTORIES = frozenset({"embodiment", "godot_gateway"})
REQUIRED_DESKTOP_SOURCE_DIRECTORIES = frozenset({"resources", "windows"})
REQUIRED_DESKTOP_SOURCE_FILES = frozenset(
    {"desktop_role_lifecycle.ts", "lifecycle_client.ts", "main.ts"}
)
FORBIDDEN_DESKTOP_SOURCE_FILES = frozenset({"role_dispatch.ts"})
CURRENT_PYTHON_SOURCE_ROOTS = (
    "app",
    "elfie",
    "nest",
    "infrastructure",
    "devtools",
    "scripts",
)
EXPECTED_QUALITY_COMMAND = "uv run --no-sync python scripts/check_quality_baseline.py"
NEST_FORBIDDEN_IMPORT_ROOTS = frozenset(
    {"ai_runtime", "app", "elfie", "godot_project", "godot_runtime", "infrastructure"}
)
NEST_SPATIAL_LAYOUT_NAMES = frozenset(
    {
        "DEFAULT_BED_COLUMNS",
        "DEFAULT_BED_X",
        "DEFAULT_BED_Y_GAP",
        "DEFAULT_BED_Y_START",
        "grid_x",
        "grid_y",
    }
)
NEST_LEGACY_GODOT_NAMES = frozenset(
    {"FurnitureState", "GODOT_INBOUND_EVENTS", "register_scene_furniture"}
    | {"send_action", "target_furniture"}
)


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif (
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module is not None
        ):
            imported_roots.add(node.module.split(".", 1)[0])
    return imported_roots


def _names_in_python_source(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            names.add(node.value)
    return names


def test_stable_repository_directories_exist() -> None:
    # Given
    existing = {path.name for path in PROJECT_ROOT.iterdir() if path.is_dir()}

    # When
    missing = REQUIRED_ROOT_DIRECTORIES - existing

    # Then
    assert missing == frozenset()


def test_root_infrastructure_is_a_first_class_python_source() -> None:
    # Given: root Infrastructure is a production package, not checkout-only code.
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    # When/Then: release discovery, import sorting and coverage all classify it.
    assert 'include = ["app*", "elfie*", "infrastructure*", "nest*"]' in pyproject
    assert 'known-first-party = ["app", "elfie", "infrastructure", "nest"]' in pyproject
    assert 'source = ["app", "elfie", "infrastructure", "nest"]' in pyproject
    assert '"infrastructure.models.providers"' not in pyproject
    assert (PROJECT_ROOT / "config" / "models" / "provider-catalog.yaml").is_file()
    assert (PROJECT_ROOT / "config" / "models" / "model-catalog.yaml").is_file()
    assert "ai_runtime" not in pyproject


def test_legacy_source_directories_are_removed() -> None:
    # Given
    existing = {path.name for path in PROJECT_ROOT.iterdir() if path.is_dir()}

    # When
    legacy = FORBIDDEN_SOURCE_DIRECTORIES & existing

    # Then
    assert legacy == frozenset()


def test_elfie_has_no_persisted_runtime_state_package() -> None:
    # Given
    existing = {
        path.name for path in (PROJECT_ROOT / "elfie").iterdir() if path.is_dir()
    }

    # When
    persisted_state_packages = FORBIDDEN_ELFIE_DIRECTORIES & existing

    # Then
    assert persisted_state_packages == frozenset()


def test_app_and_nest_have_the_confirmed_secondary_structure() -> None:
    # Given
    app_entries = {path.name for path in (PROJECT_ROOT / "app").iterdir()}
    app_interface_entries = {
        path.name
        for path in (PROJECT_ROOT / "app" / "interfaces").iterdir()
        if path.is_dir()
    }
    nest_entries = {path.name for path in (PROJECT_ROOT / "nest").iterdir()}

    # When
    missing_app_entries = REQUIRED_APP_DIRECTORIES - app_entries
    missing_interface_entries = (
        REQUIRED_APP_INTERFACE_DIRECTORIES - app_interface_entries
    )
    missing_nest_entries = REQUIRED_NEST_ENTRIES - nest_entries

    # Then
    assert missing_app_entries == frozenset()
    assert missing_interface_entries == frozenset()
    assert missing_nest_entries == frozenset()
    assert not FORBIDDEN_NEST_DIRECTORIES.intersection(nest_entries)


def test_desktop_source_has_the_confirmed_secondary_structure() -> None:
    # Given
    desktop_source_root = PROJECT_ROOT / "app" / "interfaces" / "desktop" / "src"
    source_entries = {
        path.name for path in desktop_source_root.iterdir() if path.is_dir()
    }
    source_files = {
        path.name for path in desktop_source_root.iterdir() if path.is_file()
    }

    # When
    missing_directories = REQUIRED_DESKTOP_SOURCE_DIRECTORIES - source_entries
    missing_files = REQUIRED_DESKTOP_SOURCE_FILES - source_files

    # Then
    assert missing_directories == frozenset()
    assert missing_files == frozenset()
    assert not FORBIDDEN_DESKTOP_SOURCE_FILES.intersection(source_files)


def test_python_sources_do_not_import_legacy_packages() -> None:
    # Given
    source_roots = (
        PROJECT_ROOT / "app",
        PROJECT_ROOT / "devtools",
        PROJECT_ROOT / "elfie",
        PROJECT_ROOT / "infrastructure",
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
            imported_roots = _imported_roots(path)
            if imported_roots & forbidden_packages:
                offenders.append(path.relative_to(PROJECT_ROOT).as_posix())

    # Then
    assert offenders == []


def test_python_39_sources_do_not_use_dataclass_slots() -> None:
    # Given: the repository's fixed CPython 3.9.25 runtime contract.
    source_roots = tuple(PROJECT_ROOT / root for root in CURRENT_PYTHON_SOURCE_ROOTS)

    # When: dataclass decorator keyword arguments are inspected.
    offenders: list[str] = []
    for source_root in source_roots:
        for path in source_root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for decorator in ast.walk(tree):
                if not isinstance(decorator, ast.Call):
                    continue
                if (
                    not isinstance(decorator.func, ast.Name)
                    or decorator.func.id != "dataclass"
                ):
                    continue
                if any(keyword.arg == "slots" for keyword in decorator.keywords):
                    offenders.append(path.relative_to(PROJECT_ROOT).as_posix())

    # Then: no Python 3.10-only dataclass slots argument can reach runtime.
    assert offenders == []


def test_nest_python_sources_do_not_import_product_or_godot_source_layers() -> None:
    # Given
    nest_root = PROJECT_ROOT / "nest"

    # When
    offenders = []
    for path in nest_root.rglob("*.py"):
        imported_forbidden_roots = _imported_roots(path) & NEST_FORBIDDEN_IMPORT_ROOTS
        if imported_forbidden_roots:
            offenders.append(
                (
                    path.relative_to(PROJECT_ROOT).as_posix(),
                    sorted(imported_forbidden_roots),
                )
            )

    # Then
    assert offenders == []


def test_nest_boundary_check_catches_illegal_reverse_dependency_fixture(
    tmp_path: Path,
) -> None:
    # Given
    source_path = tmp_path / "fixture.py"
    source_path.write_text(
        "from app.orchestration.nest_session import NestSession\n",
        encoding="utf-8",
    )

    # When
    imported_roots = _imported_roots(source_path)

    # Then
    assert imported_roots & NEST_FORBIDDEN_IMPORT_ROOTS == {"app"}


def test_nest_source_text_check_catches_spatial_layout_fixture() -> None:
    # Given
    source = (
        "DEFAULT_BED_X = (18, 39, 60)\ndef place(grid_x: int) -> int: return grid_x\n"
    )

    # When
    spatial_names = _names_in_python_source(source) & NEST_SPATIAL_LAYOUT_NAMES

    # Then
    assert spatial_names == {"DEFAULT_BED_X", "grid_x"}


def test_nest_does_not_retain_v1_godot_or_furniture_mirror_api() -> None:
    offenders = []
    for path in (PROJECT_ROOT / "nest").rglob("*.py"):
        legacy_names = (
            _names_in_python_source(path.read_text(encoding="utf-8"))
            & NEST_LEGACY_GODOT_NAMES
        )
        if legacy_names:
            offenders.append(
                (
                    path.relative_to(PROJECT_ROOT).as_posix(),
                    sorted(legacy_names),
                )
            )

    assert offenders == []


def test_ci_uses_current_python_roots_and_required_quality_gates() -> None:
    # Given
    ci_config = yaml.safe_load(
        (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    pre_submit = (PROJECT_ROOT / "scripts" / "pre_submit_gate.sh").read_text(
        encoding="utf-8"
    )

    # When
    jobs = ci_config["jobs"]
    run_commands = [
        step["run"] for job in jobs.values() for step in job["steps"] if "run" in step
    ]

    # Then
    assert "scripts/check_quality_baseline.py" in pre_submit
    assert "pre-commit run --all-files" in pre_submit
    assert "postsubmit-full" in jobs
    assert "--stage full --direct-full" in "\n".join(run_commands)
    assert "docs-build" in jobs
    assert "pnpm install --frozen-lockfile" in run_commands
    assert "pnpm build" in run_commands


def test_root_test_directory_contains_no_test_modules() -> None:
    # Given
    root_test_modules = sorted(
        path.name for path in (PROJECT_ROOT / "test").glob("test_*.py")
    )

    # Then
    assert root_test_modules == []


def test_precommit_uses_locked_project_tools_and_gitleaks() -> None:
    # Given
    precommit_config = yaml.safe_load(
        (PROJECT_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    )

    # When
    repositories = precommit_config["repos"]
    local_repository = next(
        repository for repository in repositories if repository["repo"] == "local"
    )
    local_hooks = {hook["id"]: hook for hook in local_repository["hooks"]}
    gitleaks_repository = next(
        repository
        for repository in repositories
        if repository["repo"] == "https://github.com/gitleaks/gitleaks"
    )

    # Then
    assert MYPY_SOURCE_ROOT_CANDIDATES == CURRENT_PYTHON_SOURCE_ROOTS
    assert MYPY_SOURCE_ROOTS == tuple(
        root for root in CURRENT_PYTHON_SOURCE_ROOTS if (PROJECT_ROOT / root).is_dir()
    )
    assert set(local_hooks) == {"quality-baseline"}
    assert local_hooks["quality-baseline"]["entry"] == EXPECTED_QUALITY_COMMAND
    assert all(
        hook["language"] == "system" and hook["pass_filenames"] is False
        for hook in local_hooks.values()
    )
    assert gitleaks_repository["rev"] == "v8.30.1"
    assert [hook["id"] for hook in gitleaks_repository["hooks"]] == ["gitleaks"]
