import ast
from pathlib import Path

import yaml

from scripts.check_quality_baseline import MYPY_SOURCE_ROOTS

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
FORBIDDEN_ELFIE_DIRECTORIES = frozenset({"state"})
REQUIRED_APP_DIRECTORIES = frozenset(
    {"bootstrap", "features", "infrastructure", "interfaces", "orchestration"}
)
REQUIRED_NEST_ENTRIES = frozenset(
    {"__init__.py", "engine", "events.py", "godot", "interaction", "nest.py", "state"}
)
REQUIRED_DESKTOP_SOURCE_DIRECTORIES = frozenset(
    {"platform", "resources", "supervisor", "windows"}
)
CURRENT_PYTHON_SOURCE_ROOTS = (
    "ai_runtime",
    "app",
    "elfie",
    "nest",
    "devtools",
    "scripts",
)
EXPECTED_QUALITY_COMMAND = "uv run --no-sync python scripts/check_quality_baseline.py"


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
        path.name
        for path in (PROJECT_ROOT / "desktop" / "src").iterdir()
        if path.is_dir()
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
                    imported_roots.update(
                        alias.name.split(".", 1)[0] for alias in node.names
                    )
                elif isinstance(node, ast.ImportFrom) and node.module is not None:
                    imported_roots.add(node.module.split(".", 1)[0])
            if imported_roots & forbidden_packages:
                offenders.append(path.relative_to(PROJECT_ROOT).as_posix())

    # Then
    assert offenders == []


def test_ci_uses_current_python_roots_and_required_quality_gates() -> None:
    # Given
    ci_config = yaml.safe_load(
        (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )

    # When
    jobs = ci_config["jobs"]
    run_commands = [
        step["run"] for job in jobs.values() for step in job["steps"] if "run" in step
    ]

    # Then
    assert EXPECTED_QUALITY_COMMAND in run_commands
    assert "uv run --no-sync pre-commit run --all-files" in run_commands
    assert "docs-build" in jobs
    assert "pnpm install --frozen-lockfile" in run_commands
    assert "pnpm build" in run_commands


def test_root_test_directory_contains_no_test_modules() -> None:
    # Given
    test_root = PROJECT_ROOT / "test"

    # When
    root_test_modules = sorted(path.name for path in test_root.glob("test_*.py"))

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
    assert MYPY_SOURCE_ROOTS == CURRENT_PYTHON_SOURCE_ROOTS
    assert set(local_hooks) == {"quality-baseline"}
    assert local_hooks["quality-baseline"]["entry"] == EXPECTED_QUALITY_COMMAND
    assert all(
        hook["language"] == "system" and hook["pass_filenames"] is False
        for hook in local_hooks.values()
    )
    assert gitleaks_repository["rev"] == "v8.30.1"
    assert [hook["id"] for hook in gitleaks_repository["hooks"]] == ["gitleaks"]
