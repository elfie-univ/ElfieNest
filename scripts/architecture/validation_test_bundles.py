#!/usr/bin/env python3
"""Run reusable local pytest bundles and combine their coverage evidence."""

from __future__ import annotations

import argparse
import ast
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if __package__ is None:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.architecture.validation_cache import (
    RepositorySnapshot,
    cache_hit,
    cache_invalidate,
    cache_lock,
    cache_record,
    cache_store,
    check_fingerprint,
    file_sha256,
    installed_package_version,
    repository_snapshot,
    repository_snapshot_current,
    scoped_fingerprint,
)
from scripts.architecture.validation_plan import changed_paths

TEST_BUNDLE_RULE_VERSION = "pytest-bundles-v4"
GENERATED_PATHS = frozenset({"coverage.xml"})
LOCAL_RUNTIME_PATHS = frozenset({".venv", "venv"})
LOCAL_RUNTIME_PREFIXES = (
    "node_modules",
    "app/interfaces/desktop/node_modules",
    "app/interfaces/web/frontend/node_modules",
    "devtools/web/node_modules",
    "docs/node_modules",
)
COMMON_EXACT_INPUTS = frozenset(
    {
        ".python-version",
        "pyproject.toml",
        "uv.lock",
        "test/__init__.py",
        "test/conftest.py",
        "scripts/architecture/validation_cache.py",
        "scripts/architecture/validation_test_bundles.py",
    }
)
COMMON_INPUT_PREFIXES = ("config/", "test/support/")
KNOWN_ROOT_PREFIXES = (
    ".agents/",
    ".github/",
    "app/",
    "config/",
    "devtools/",
    "docs/",
    "elfie/",
    "godot_project/",
    "infrastructure/",
    "nest/",
    "resources/",
    "scripts/",
    "test/",
)
KNOWN_ROOT_EXACT = frozenset(
    {
        ".gitignore",
        ".pre-commit-config.yaml",
        ".python-version",
        "AGENTS.md",
        "CONTRIBUTING.md",
        "CONTRIBUTING_zh.md",
        "LICENSE",
        "README.md",
        "README_zh.md",
        "package.json",
        "pnpm-lock.yaml",
        "pyproject.toml",
        "uv.lock",
    }
)


@dataclass(frozen=True)
class TestBundle:
    bundle_id: str
    selectors: Tuple[str, ...]
    input_prefixes: Tuple[str, ...]
    input_exact: Tuple[str, ...] = ()
    all_repository: bool = False
    # Source roots seed the local-Python dependency closure.  Keeping these
    # separate from input_prefixes lets a bundle declare a narrow direct
    # scope while still following imports that leave that scope.
    source_prefixes: Tuple[str, ...] = ()
    # Dynamic loaders, script entrypoints and non-Python resources cannot be
    # recovered safely from an AST.  They are explicit, conservative inputs.
    dynamic_input_prefixes: Tuple[str, ...] = ()
    dynamic_input_exact: Tuple[str, ...] = ()


def _app_bundle(
    bundle_id: str,
    selectors: Tuple[str, ...],
    source_prefix: str,
    *,
    input_prefixes: Tuple[str, ...] = (),
    input_exact: Tuple[str, ...] = (),
    source_prefixes: Optional[Tuple[str, ...]] = None,
    dynamic_input_prefixes: Tuple[str, ...] = (),
    dynamic_input_exact: Tuple[str, ...] = (),
) -> TestBundle:
    """Declare one App test slice and its explicit non-static inputs.

    The source prefix is both a direct fingerprint input and a root for the
    import closure.  The latter captures shared Feature/Orchestration
    dependencies without making every App slice depend on all of ``app/``.
    Entry-point/resource inputs stay explicit so a dynamic boundary cannot
    silently produce a false cache hit.
    """

    return TestBundle(
        bundle_id,
        selectors,
        (source_prefix, *input_prefixes),
        input_exact,
        source_prefixes=(source_prefix,)
        if source_prefixes is None
        else source_prefixes,
        dynamic_input_prefixes=dynamic_input_prefixes,
        dynamic_input_exact=dynamic_input_exact,
    )


APP_TEST_BUNDLES: Tuple[TestBundle, ...] = (
    _app_bundle(
        "app_bootstrap",
        ("test/app/bootstrap",),
        "app/bootstrap/",
        dynamic_input_exact=(
            "scripts/bootstrap.sh",
            "scripts/elfienest.py",
            "scripts/serve.py",
        ),
    ),
    _app_bundle(
        "app_features_accounts",
        ("test/app/features/accounts",),
        "app/features/accounts/",
    ),
    _app_bundle(
        "app_features_adoption",
        ("test/app/features/adoption",),
        "app/features/adoption/",
        input_prefixes=("docs/public/assets/",),
    ),
    _app_bundle(
        "app_features_bodies",
        ("test/app/features/bodies",),
        "app/features/bodies/",
    ),
    _app_bundle(
        "app_features_communication",
        ("test/app/features/communication",),
        "app/features/communication/",
    ),
    _app_bundle(
        "app_features_configuration_capabilities",
        ("test/app/features/configuration/capabilities",),
        "app/features/configuration/capabilities/",
    ),
    _app_bundle(
        "app_features_configuration_food",
        ("test/app/features/configuration/food",),
        "app/features/configuration/food/",
    ),
    _app_bundle(
        "app_features_configuration_providers",
        ("test/app/features/configuration/providers",),
        "app/features/configuration/providers/",
    ),
    _app_bundle(
        "app_features_configuration_settings",
        ("test/app/features/configuration/settings",),
        "app/features/configuration/settings/",
    ),
    _app_bundle(
        "app_features_elfies",
        ("test/app/features/elfies",),
        "app/features/elfies/",
    ),
    _app_bundle(
        "app_features_nest_management",
        ("test/app/features/nest_management",),
        "app/features/nest_management/",
    ),
    _app_bundle(
        "app_features_operations",
        ("test/app/features/operations",),
        "app/features/operations/",
    ),
    _app_bundle(
        "app_features_setup",
        ("test/app/features/setup",),
        "app/features/setup/",
    ),
    _app_bundle(
        "app_interfaces_api",
        ("test/app/interfaces/api",),
        "app/interfaces/api/",
        dynamic_input_prefixes=("resources/", "scripts/"),
    ),
    _app_bundle(
        "app_interfaces_cli",
        ("test/app/interfaces/cli",),
        "app/interfaces/cli/",
        input_exact=("package.json", "pnpm-lock.yaml"),
        dynamic_input_prefixes=("resources/", "scripts/"),
    ),
    _app_bundle(
        "app_interfaces_web",
        ("test/app/interfaces/web",),
        "app/interfaces/web/",
        input_prefixes=("app/interfaces/web/frontend/",),
    ),
    _app_bundle(
        "app_orchestration_embodiment",
        ("test/app/orchestration/embodiment",),
        "app/orchestration/embodiment/",
    ),
    _app_bundle(
        "app_orchestration_lifecycle",
        ("test/app/orchestration/lifecycle",),
        "app/orchestration/lifecycle/",
        dynamic_input_prefixes=("scripts/",),
    ),
    _app_bundle(
        "app_orchestration_message_delivery",
        ("test/app/orchestration/message_delivery",),
        "app/orchestration/message_delivery/",
    ),
    _app_bundle(
        "app_orchestration_nest_session",
        ("test/app/orchestration/nest_session",),
        "app/orchestration/nest_session/",
    ),
    _app_bundle(
        "app_orchestration_observer",
        ("test/app/orchestration/observer",),
        "app/orchestration/observer/",
    ),
    _app_bundle(
        "app_orchestration_resident_admission",
        ("test/app/orchestration/resident_admission",),
        "app/orchestration/resident_admission/",
    ),
    _app_bundle(
        "app_orchestration_setup_installation",
        ("test/app/orchestration/setup_installation",),
        "app/orchestration/setup_installation/",
    ),
    _app_bundle(
        "app_orchestration_crosscutting",
        (
            "test/app/orchestration/test_godot_owner_channel.py",
            "test/app/orchestration/test_observer_projection.py",
        ),
        "app/orchestration/",
        dynamic_input_prefixes=("scripts/",),
    ),
    _app_bundle(
        "app_product_e2e",
        (
            "test/app/test_final_storage_e2e.py",
            "test/app/test_product_chat_brain_e2e.py",
        ),
        "app/",
        source_prefixes=(),
        dynamic_input_prefixes=("resources/", "scripts/"),
    ),
)


@dataclass(frozen=True)
class BundleRun:
    returncode: int
    key: str
    artifact: Optional[Path]
    reused: bool


TEST_BUNDLES: Tuple[TestBundle, ...] = (
    TestBundle("architecture", ("test/architecture",), (), all_repository=True),
    TestBundle("godot", ("test/godot",), ("godot_project/", "infrastructure/godot/")),
    TestBundle("nest", ("test/nest",), ("nest/",)),
    TestBundle(
        "scripts",
        ("test/scripts",),
        (
            ".github/",
            "app/",
            "devtools/",
            "docs/",
            "elfie/",
            "godot_project/",
            "infrastructure/",
            "nest/",
            "resources/",
            "scripts/",
        ),
        ("package.json", "pnpm-lock.yaml"),
    ),
    TestBundle(
        "devtools",
        ("test/devtools",),
        (
            "devtools/",
            "app/",
            "elfie/",
            "infrastructure/",
            "nest/",
            "resources/",
            "scripts/",
        ),
    ),
    TestBundle("elfie", ("test/elfie",), ("elfie/", "infrastructure/", "nest/")),
    *APP_TEST_BUNDLES,
    TestBundle(
        "infrastructure",
        ("test/infrastructure",),
        ("app/", "elfie/", "infrastructure/", "nest/", "resources/"),
    ),
    TestBundle(
        "e2e",
        ("test/e2e",),
        ("app/", "elfie/", "infrastructure/", "nest/", "resources/"),
    ),
)


def bundle_by_id(bundle_id: str) -> TestBundle:
    for bundle in TEST_BUNDLES:
        if bundle.bundle_id == bundle_id:
            return bundle
    raise KeyError(bundle_id)


def repository_paths() -> List[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted(
        {
            path
            for path in result.stdout.splitlines()
            if path
            and path not in GENERATED_PATHS
            and path not in LOCAL_RUNTIME_PATHS
            and not path.startswith("build/")
            and not path.startswith((".venv/", "venv/"))
            and not any(
                path == prefix or path.startswith(f"{prefix}/")
                for prefix in LOCAL_RUNTIME_PREFIXES
            )
        }
    )


def _matches_prefix(path: str, prefixes: Sequence[str]) -> bool:
    return any(path.startswith(prefix) for prefix in prefixes)


def _is_unknown_input(path: str) -> bool:
    if path in KNOWN_ROOT_EXACT or _matches_prefix(path, KNOWN_ROOT_PREFIXES):
        return False
    return not path.endswith((".md", ".rst"))


def _module_name(path: str) -> Optional[str]:
    if not path.endswith(".py"):
        return None
    module = path[:-3].replace("/", ".")
    if module.endswith(".__init__"):
        module = module[: -len(".__init__")]
    return module


def _python_module_index(candidate_paths: Sequence[str]) -> dict:
    index = {}
    for path in candidate_paths:
        module = _module_name(path)
        if module:
            index[module] = path
    return index


def _resolve_relative_base(current_module: str, current_path: str, level: int) -> str:
    if level == 0:
        return ""
    current_parts = current_module.split(".") if current_module else []
    package_parts = (
        current_parts if current_path.endswith("/__init__.py") else current_parts[:-1]
    )
    trim = max(level - 1, 0)
    return ".".join(package_parts[: len(package_parts) - trim])


def _imported_modules(
    node: ast.AST, current_module: str, current_path: str
) -> List[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if not isinstance(node, ast.ImportFrom):
        return []
    base = _resolve_relative_base(current_module, current_path, node.level)
    if node.module:
        base = ".".join(part for part in (base, node.module) if part)
    modules = [base] if base else []
    modules.extend(
        ".".join(part for part in (base, alias.name) if part)
        for alias in node.names
        if alias.name != "*"
    )
    return modules


_IMPORTS_CACHE: dict[Tuple[str, str, str], Tuple[str, ...]] = {}


def _cached_imported_modules(path: str, current_module: str) -> Tuple[str, ...]:
    """Parse each unchanged Python file once per process.

    Bundle fingerprints still hash file contents independently.  This cache
    only avoids reparsing the same source while constructing several module
    impact closures in one G3 invocation; the content digest in its key
    prevents a same-path edit from reusing a stale dependency edge.
    """

    try:
        source = (PROJECT_ROOT / path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ()
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    cache_key = (str(PROJECT_ROOT.resolve()), path, digest)
    cached = _IMPORTS_CACHE.get(cache_key)
    if cached is not None:
        return cached
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ()
    modules = tuple(
        imported
        for node in ast.walk(tree)
        for imported in _imported_modules(node, current_module, path)
    )
    _IMPORTS_CACHE[cache_key] = modules
    return modules


def _local_python_dependency_paths(
    bundle: TestBundle, candidate_paths: Sequence[str]
) -> set:
    """Follow local Python imports from a bundle's tests and shared fixtures.

    The explicit bundle prefixes remain a conservative safety net for dynamic
    entry points and non-Python resources. This closure fixes the common case
    where a test imports a module in another top-level package that the manual
    matrix did not list.
    """

    candidate_set = set(candidate_paths)
    index = _python_module_index(candidate_paths)
    test_prefixes = tuple(f"{selector.rstrip('/')}/" for selector in bundle.selectors)
    roots = {
        path
        for path in candidate_set
        if path.endswith(".py")
        and (
            _matches_prefix(path, test_prefixes)
            or path == "test/conftest.py"
            or _matches_prefix(path, COMMON_INPUT_PREFIXES)
            or _matches_prefix(path, bundle.source_prefixes)
        )
    }
    discovered = set(roots)
    pending = list(roots)
    while pending:
        path = pending.pop()
        module = _module_name(path)
        if not module:
            continue
        for imported in _cached_imported_modules(path, module):
            dependency = index.get(imported)
            if dependency and dependency not in discovered:
                discovered.add(dependency)
                pending.append(dependency)
    return discovered


def bundle_input_paths(bundle: TestBundle, candidate_paths: Sequence[str]) -> List[str]:
    if bundle.all_repository:
        return sorted(set(candidate_paths) - GENERATED_PATHS)
    test_prefixes = tuple(f"{selector.rstrip('/')}/" for selector in bundle.selectors)
    direct_inputs = {
        path
        for path in candidate_paths
        if (
            path in COMMON_EXACT_INPUTS
            or path in bundle.input_exact
            or path in bundle.dynamic_input_exact
            or _matches_prefix(path, COMMON_INPUT_PREFIXES)
            or _matches_prefix(path, bundle.input_prefixes)
            or _matches_prefix(path, bundle.dynamic_input_prefixes)
            or _matches_prefix(path, test_prefixes)
            or _is_unknown_input(path)
        )
    }
    return sorted(
        direct_inputs | _local_python_dependency_paths(bundle, candidate_paths)
    )


def bundle_fingerprint(
    bundle: TestBundle,
    candidate_paths: Sequence[str],
    *,
    base_sha: str = "",
    snapshot: Optional[RepositorySnapshot] = None,
) -> str:
    namespace = ":".join(
        (
            TEST_BUNDLE_RULE_VERSION,
            bundle.bundle_id,
            base_sha or "<unspecified-base>",
        )
    )
    return scoped_fingerprint(
        namespace,
        bundle_input_paths(bundle, candidate_paths),
        _fingerprint_pytest_command(bundle.selectors, coverage=True),
        snapshot=snapshot,
    )


def coverage_artifact_path(cache_root: Path, key: str) -> Path:
    return cache_root / "coverage" / f"{key}.coverage"


def coverage_cache_metadata(artifact: Path) -> dict:
    return {
        "artifact_sha256": file_sha256(artifact),
        "coverage_version": installed_package_version("coverage"),
        "pytest_cov_version": installed_package_version("pytest-cov"),
        "pytest_version": installed_package_version("pytest"),
        "coverage_paths": "relative",
    }


def _coverage_artifact_is_readable(artifact: Path) -> bool:
    try:
        import coverage

        coverage.CoverageData(basename=str(artifact)).read()
    except (OSError, coverage.CoverageException):
        return False
    return True


def _portable_coverage_path(path: str) -> Optional[str]:
    """Return a repository-relative coverage path, or reject it fail-closed."""

    candidate = Path(path)
    root = PROJECT_ROOT.resolve()
    if candidate.is_absolute():
        resolved = candidate.resolve()
        if resolved != root and root not in resolved.parents:
            return None
        return resolved.relative_to(root).as_posix()
    normalized = Path(os.path.normpath(path))
    if normalized == Path("..") or Path("..") in normalized.parents:
        return None
    return normalized.as_posix()


def _coverage_artifact_is_portable(artifact: Path) -> bool:
    """Reject coverage fragments that embed a worktree-specific path."""

    try:
        import coverage

        data = coverage.CoverageData(basename=str(artifact))
        data.read()
        for path in data.measured_files():
            if _portable_coverage_path(path) is None:
                return False
        return True
    except (OSError, coverage.CoverageException):
        return False


def _normalize_coverage_artifact(artifact: Path) -> bool:
    """Rewrite a newly produced fragment so it is safe across candidate trees."""

    try:
        import coverage

        source = coverage.CoverageData(basename=str(artifact))
        source.read()
        has_arcs = source.has_arcs()
        line_data = {}
        arc_data = {}
        for filename in source.measured_files():
            relative = _portable_coverage_path(filename)
            if relative is None:
                return False
            if has_arcs:
                arc_data[relative] = source.arcs(filename) or []
            else:
                line_data[relative] = source.lines(filename) or []
        temporary = artifact.with_name(f".{artifact.name}.normalized.tmp")
        temporary.unlink(missing_ok=True)
        normalized = coverage.CoverageData(basename=str(temporary))
        if has_arcs:
            normalized.add_arcs(arc_data)
        else:
            normalized.add_lines(line_data)
        normalized.write()
        os.replace(temporary, artifact)
        return _coverage_artifact_is_portable(artifact)
    except (OSError, coverage.CoverageException):
        return False


def _invalidate_bundle_artifacts(cache_root: Path, key: str) -> None:
    cache_invalidate(cache_root, key)
    coverage_artifact_path(cache_root, key).unlink(missing_ok=True)


def bundle_cache_hit(cache_root: Path, key: str) -> bool:
    artifact = coverage_artifact_path(cache_root, key)
    record = cache_record(cache_root, key)
    if not cache_hit(cache_root, key) or not artifact.is_file():
        return False
    metadata = record.get("metadata") if record else None
    if not isinstance(metadata, dict):
        return False
    try:
        expected = coverage_cache_metadata(artifact)
    except OSError:
        _invalidate_bundle_artifacts(cache_root, key)
        return False
    if any(metadata.get(name) != value for name, value in expected.items()):
        _invalidate_bundle_artifacts(cache_root, key)
        return False
    if not _coverage_artifact_is_readable(artifact):
        _invalidate_bundle_artifacts(cache_root, key)
        return False
    if not _coverage_artifact_is_portable(artifact):
        _invalidate_bundle_artifacts(cache_root, key)
        return False
    return True


def bundle_pytest_command(bundle: TestBundle) -> Tuple[str, ...]:
    return (
        sys.executable,
        "-m",
        "pytest",
        *bundle.selectors,
        "--cov",
        "--cov-report=",
        "--cov-fail-under=0",
    )


def _fingerprint_pytest_command(
    selectors: Sequence[str], *, coverage: bool = False
) -> Tuple[str, ...]:
    """Describe pytest without baking a worktree-local interpreter path into keys."""

    command = ("python", "-m", "pytest", *selectors)
    if coverage:
        command += ("--cov", "--cov-report=", "--cov-fail-under=0")
    return command


def _execute_bundle(bundle: TestBundle, coverage_file: Path) -> int:
    env = os.environ.copy()
    env.setdefault("UV_CACHE_DIR", "/tmp/elfienest-uv-cache")
    env["COVERAGE_FILE"] = str(coverage_file)
    command = list(bundle_pytest_command(bundle))
    print(f"\n==> test bundle {bundle.bundle_id}: {' '.join(command)}")
    return subprocess.run(command, cwd=PROJECT_ROOT, env=env, check=False).returncode


def run_bundle(
    bundle: TestBundle,
    cache_root: Path,
    *,
    no_cache: bool = False,
    candidate_paths: Optional[Sequence[str]] = None,
    snapshot: Optional[RepositorySnapshot] = None,
    base_sha: str = "",
) -> BundleRun:
    shared_snapshot = snapshot is not None
    candidate_paths = list(candidate_paths or repository_paths())
    snapshot = snapshot or repository_snapshot(candidate_paths)
    key = bundle_fingerprint(
        bundle, candidate_paths, base_sha=base_sha, snapshot=snapshot
    )
    artifact = coverage_artifact_path(cache_root, key)
    lock = cache_root / f"{key}.lock"
    with cache_lock(lock):
        if not no_cache and not shared_snapshot:
            current_paths = repository_paths()
            if current_paths != candidate_paths:
                return run_bundle(
                    bundle,
                    cache_root,
                    no_cache=no_cache,
                    candidate_paths=current_paths,
                    snapshot=repository_snapshot(current_paths),
                    base_sha=base_sha,
                )
        elif not no_cache and not repository_snapshot_current(
            snapshot, candidate_paths
        ):
            current_paths = repository_paths()
            return run_bundle(
                bundle,
                cache_root,
                no_cache=no_cache,
                candidate_paths=current_paths,
                snapshot=repository_snapshot(current_paths),
                base_sha=base_sha,
            )
        if not no_cache and bundle_cache_hit(cache_root, key):
            print(f"✅ reused passed test bundle {bundle.bundle_id}: {key}")
            return BundleRun(0, key, artifact, True)
        artifact.parent.mkdir(parents=True, exist_ok=True)
        temporary = artifact.with_name(f".{artifact.name}.{os.getpid()}.tmp")
        temporary.unlink(missing_ok=True)
        result = _execute_bundle(bundle, temporary)
        if result != 0:
            temporary.unlink(missing_ok=True)
            _invalidate_bundle_artifacts(cache_root, key)
            return BundleRun(result, key, None, False)
        if not _normalize_coverage_artifact(temporary):
            temporary.unlink(missing_ok=True)
            _invalidate_bundle_artifacts(cache_root, key)
            print(
                f"❌ test bundle {bundle.bundle_id} produced non-portable coverage",
                file=sys.stderr,
            )
            return BundleRun(1, key, None, False)
        if repository_snapshot_current(snapshot, candidate_paths):
            after = bundle_fingerprint(
                bundle, candidate_paths, base_sha=base_sha, snapshot=snapshot
            )
        else:
            after_paths = repository_paths()
            after_snapshot = repository_snapshot(after_paths)
            after = bundle_fingerprint(
                bundle,
                after_paths,
                base_sha=base_sha,
                snapshot=after_snapshot,
            )
        if after != key or not temporary.is_file():
            temporary.unlink(missing_ok=True)
            cache_invalidate(cache_root, key)
            artifact.unlink(missing_ok=True)
            print(
                f"❌ test bundle {bundle.bundle_id} changed inputs or produced no coverage",
                file=sys.stderr,
            )
            return BundleRun(1, key, None, False)
        os.replace(temporary, artifact)
        if not no_cache:
            cache_store(
                cache_root,
                key,
                f"test-bundle:{bundle.bundle_id}",
                "content-scoped",
                metadata=coverage_cache_metadata(artifact),
            )
        return BundleRun(0, key, artifact, False)


def run_focused_tests(
    selectors: Sequence[str], base_sha: str, cache_root: Path, *, no_cache: bool = False
) -> int:
    normalized = tuple(sorted(set(selectors)))
    paths = changed_paths(base_sha)
    snapshot = repository_snapshot(paths)
    command = (sys.executable, "-m", "pytest", *normalized)
    key = focused_test_fingerprint(base_sha, normalized, paths, snapshot=snapshot)
    lock = cache_root / f"{key}.lock"
    with cache_lock(lock):
        if not no_cache and not repository_snapshot_current(snapshot, paths):
            paths = changed_paths(base_sha)
            snapshot = repository_snapshot(paths)
            key = focused_test_fingerprint(
                base_sha, normalized, paths, snapshot=snapshot
            )
        if not no_cache and cache_hit(cache_root, key):
            print(f"✅ reused passed focused tests: {key}")
            return 0
        env = os.environ.copy()
        env.setdefault("UV_CACHE_DIR", "/tmp/elfienest-uv-cache")
        print(f"\n==> focused tests: {' '.join(command)}")
        result = subprocess.run(
            list(command), cwd=PROJECT_ROOT, env=env, check=False
        ).returncode
        if result != 0:
            if no_cache:
                cache_invalidate(cache_root, key)
            return result
        after_paths = changed_paths(base_sha)
        after_snapshot = repository_snapshot(after_paths)
        if (
            focused_test_fingerprint(
                base_sha, normalized, after_paths, snapshot=after_snapshot
            )
            != key
        ):
            cache_invalidate(cache_root, key)
            print("❌ candidate changed during focused tests", file=sys.stderr)
            return 1
        if not no_cache:
            cache_store(cache_root, key, "focused-pytest", base_sha)
        return 0


def run_selected_tests(
    selectors: Sequence[str],
    base_sha: str,
    cache_root: Path,
    *,
    no_cache: bool = False,
) -> int:
    """Reuse complete bundle evidence for exact or contained selectors.

    ``validation_plan`` often returns a nested test directory for a changed
    source file (for example ``test/app/interfaces/api/v1``).  That selector
    is still owned by the registered API bundle, so running the complete
    module is both safer and reusable.  A parent selector such as
    ``test/app`` expands to all owned App modules; unrelated selectors remain
    focused and never masquerade as a complete bundle.
    """

    normalized = tuple(sorted({selector.rstrip("/") for selector in selectors}))
    if not normalized:
        return 0

    def is_within(root: str, selector: str) -> bool:
        root = root.rstrip("/")
        selector = selector.rstrip("/")
        return selector == root or selector.startswith(f"{root}/")

    owned: List[TestBundle] = []
    unresolved = set(normalized)
    for bundle in TEST_BUNDLES:
        roots = tuple(selector.rstrip("/") for selector in bundle.selectors)
        related = {
            requested
            for requested in normalized
            if any(
                is_within(root, requested) or is_within(requested, root)
                for root in roots
            )
        }
        if related:
            owned.append(bundle)
            unresolved.difference_update(related)

    # A selector can be related to a broad bundle and a narrower one at the
    # same time.  Prefer the narrowest complete owner for descendant paths,
    # while retaining all modules for an explicit parent (e.g. test/app).
    if not unresolved:
        selected: List[TestBundle] = []
        for bundle in owned:
            roots = tuple(selector.rstrip("/") for selector in bundle.selectors)
            include = any(
                any(is_within(root, requested) for root in roots)
                or any(is_within(requested, root) for root in roots)
                for requested in normalized
            )
            if include:
                selected.append(bundle)
        if selected:
            # A nested selector is covered by every ancestor bundle.  Choose
            # the owner with the longest selector root; parent selectors keep
            # all children because they explicitly request the parent scope.
            for requested in normalized:
                matching = [
                    bundle
                    for bundle in selected
                    if any(is_within(root, requested) for root in bundle.selectors)
                ]
                if matching:
                    longest = max(
                        len(root.rstrip("/"))
                        for bundle in matching
                        for root in bundle.selectors
                        if is_within(root, requested)
                    )
                    selected = [
                        bundle
                        for bundle in selected
                        if bundle in matching
                        and any(
                            len(root.rstrip("/")) == longest
                            for root in bundle.selectors
                            if is_within(root, requested)
                        )
                        or bundle not in matching
                    ]
            # Stable declaration order prevents cache/test ordering from
            # changing between invocations.
            selected = [bundle for bundle in TEST_BUNDLES if bundle in selected]
            for bundle in selected:
                result = run_bundle(
                    bundle,
                    cache_root,
                    no_cache=no_cache,
                    base_sha=base_sha,
                )
                if result.returncode != 0:
                    return result.returncode
            return 0
    return run_focused_tests(normalized, base_sha, cache_root, no_cache=no_cache)


def focused_test_fingerprint(
    base_sha: str,
    selectors: Sequence[str],
    candidate_paths: Sequence[str],
    *,
    snapshot: Optional[RepositorySnapshot] = None,
) -> str:
    normalized = tuple(sorted(set(selectors)))
    fingerprint_command = _fingerprint_pytest_command(normalized)
    test_inputs = list(candidate_paths)
    return check_fingerprint(
        base_sha,
        "focused-pytest",
        test_inputs,
        fingerprint_command,
        snapshot=snapshot,
    )


def _invalidate_coverage_fragments(artifacts: Sequence[Path], cache_root: Path) -> None:
    coverage_root = cache_root / "coverage"
    for artifact in artifacts:
        try:
            relative = artifact.relative_to(coverage_root)
        except ValueError:
            continue
        if len(relative.parts) == 1 and relative.suffix == ".coverage":
            _invalidate_bundle_artifacts(cache_root, relative.stem)


def combine_coverage(artifacts: Sequence[Path], cache_root: Path) -> int:
    output_root = PROJECT_ROOT / "build"
    output_root.mkdir(parents=True, exist_ok=True)
    coverage_file = output_root / ".coverage"
    coverage_xml = output_root / "coverage.xml"
    env = os.environ.copy()
    env.setdefault("UV_CACHE_DIR", "/tmp/elfienest-uv-cache")
    env["COVERAGE_FILE"] = str(coverage_file)
    with tempfile.TemporaryDirectory(dir=cache_root) as temporary:
        combine_root = Path(temporary)
        for index, artifact in enumerate(artifacts):
            shutil.copy2(artifact, combine_root / f".coverage.{index:02d}")
        commands = (
            [sys.executable, "-m", "coverage", "erase"],
            [sys.executable, "-m", "coverage", "combine", str(combine_root)],
            [
                sys.executable,
                "-m",
                "coverage",
                "xml",
                "-o",
                str(coverage_xml),
            ],
            [sys.executable, "-m", "coverage", "report", "--show-missing"],
        )
        for label, command in zip(
            ("coverage erase", "coverage combine", "coverage xml", "coverage report"),
            commands,
        ):
            print(f"\n==> coverage evidence: {' '.join(command)}")
            if (
                subprocess.run(
                    command, cwd=PROJECT_ROOT, env=env, check=False
                ).returncode
                != 0
            ):
                if label == "coverage combine":
                    _invalidate_coverage_fragments(artifacts, cache_root)
                return 1
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all", action="store_true")
    selection.add_argument(
        "--bundle", action="append", choices=[b.bundle_id for b in TEST_BUNDLES]
    )
    selection.add_argument("--selectors", nargs="+")
    parser.add_argument("--base-sha", default="")
    parser.add_argument(
        "--cache-root",
        default=os.environ.get(
            "ELFIENEST_VALIDATION_CACHE_ROOT", "build/validation-cache"
        ),
    )
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args(argv)
    cache_root = Path(args.cache_root)
    if not cache_root.is_absolute():
        cache_root = PROJECT_ROOT / cache_root
    base_sha = (
        args.base_sha
        or subprocess.check_output(
            ["git", "rev-parse", "origin/main^{commit}"],
            cwd=PROJECT_ROOT,
            text=True,
        ).strip()
    )
    if args.selectors:
        return run_selected_tests(
            args.selectors, base_sha, cache_root, no_cache=args.no_cache
        )
    bundles = (
        TEST_BUNDLES
        if args.all
        else tuple(bundle_by_id(value) for value in args.bundle)
    )
    candidate_paths = repository_paths()
    snapshot = repository_snapshot(candidate_paths)
    artifacts: List[Path] = []
    for bundle in bundles:
        result = run_bundle(
            bundle,
            cache_root,
            no_cache=args.no_cache,
            candidate_paths=candidate_paths,
            snapshot=snapshot,
            base_sha=base_sha,
        )
        if result.returncode != 0 or result.artifact is None:
            return result.returncode or 1
        artifacts.append(result.artifact)
    if args.all:
        return combine_coverage(artifacts, cache_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
