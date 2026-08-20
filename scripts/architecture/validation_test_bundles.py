#!/usr/bin/env python3
"""Run reusable local pytest bundles and combine their coverage evidence."""

from __future__ import annotations

import argparse
import ast
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

TEST_BUNDLE_RULE_VERSION = "pytest-bundles-v3"
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
    TestBundle(
        "app",
        ("test/app",),
        (
            ".github/",
            "app/",
            "docs/",
            "elfie/",
            "infrastructure/",
            "nest/",
            "resources/",
            "scripts/",
        ),
        ("AGENTS.md", "CONTRIBUTING.md"),
    ),
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
        )
    }
    discovered = set(roots)
    pending = list(roots)
    while pending:
        path = pending.pop()
        module = _module_name(path)
        if not module:
            continue
        try:
            tree = ast.parse((PROJECT_ROOT / path).read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            for imported in _imported_modules(node, module, path):
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
            or _matches_prefix(path, COMMON_INPUT_PREFIXES)
            or _matches_prefix(path, bundle.input_prefixes)
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
    snapshot: Optional[RepositorySnapshot] = None,
) -> str:
    return scoped_fingerprint(
        f"{TEST_BUNDLE_RULE_VERSION}:{bundle.bundle_id}",
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
    }


def _coverage_artifact_is_readable(artifact: Path) -> bool:
    try:
        import coverage

        coverage.CoverageData(basename=str(artifact)).read()
    except (OSError, coverage.CoverageException):
        return False
    return True


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
) -> BundleRun:
    shared_snapshot = snapshot is not None
    candidate_paths = list(candidate_paths or repository_paths())
    snapshot = snapshot or repository_snapshot(candidate_paths)
    key = bundle_fingerprint(bundle, candidate_paths, snapshot=snapshot)
    artifact = coverage_artifact_path(cache_root, key)
    lock = cache_root / f"{key}.lock"
    with cache_lock(lock):
        if not no_cache and not shared_snapshot:
            current_paths = repository_paths()
            if current_paths != candidate_paths:
                candidate_paths = current_paths
                snapshot = repository_snapshot(candidate_paths)
                key = bundle_fingerprint(bundle, candidate_paths, snapshot=snapshot)
                artifact = coverage_artifact_path(cache_root, key)
        elif not no_cache and not repository_snapshot_current(
            snapshot, candidate_paths
        ):
            candidate_paths = repository_paths()
            snapshot = repository_snapshot(candidate_paths)
            key = bundle_fingerprint(bundle, candidate_paths, snapshot=snapshot)
            artifact = coverage_artifact_path(cache_root, key)
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
        if repository_snapshot_current(snapshot, candidate_paths):
            after = bundle_fingerprint(bundle, candidate_paths, snapshot=snapshot)
        else:
            after_paths = repository_paths()
            after_snapshot = repository_snapshot(after_paths)
            after = bundle_fingerprint(bundle, after_paths, snapshot=after_snapshot)
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
    """Reuse bundle evidence when the selection is one complete stable bundle."""

    normalized = tuple(sorted({selector.rstrip("/") for selector in selectors}))
    for bundle in TEST_BUNDLES:
        bundle_selectors = tuple(
            sorted(selector.rstrip("/") for selector in bundle.selectors)
        )
        if normalized == bundle_selectors:
            return run_bundle(bundle, cache_root, no_cache=no_cache).returncode
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
    if args.selectors:
        base_sha = (
            args.base_sha
            or subprocess.check_output(
                ["git", "rev-parse", "origin/main^{commit}"],
                cwd=PROJECT_ROOT,
                text=True,
            ).strip()
        )
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
        )
        if result.returncode != 0 or result.artifact is None:
            return result.returncode or 1
        artifacts.append(result.artifact)
    if args.all:
        return combine_coverage(artifacts, cache_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
