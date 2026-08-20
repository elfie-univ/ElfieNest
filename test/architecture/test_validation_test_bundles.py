"""Contracts for reusable local test bundles and coverage evidence."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import scripts.architecture.validation_cache as validation_cache
import scripts.architecture.validation_test_bundles as test_bundles
from scripts.architecture.validation_cache import cache_store

EXPECTED_APP_BUNDLES = {
    "app_bootstrap",
    "app_features_accounts",
    "app_features_adoption",
    "app_features_bodies",
    "app_features_communication",
    "app_features_configuration_capabilities",
    "app_features_configuration_food",
    "app_features_configuration_providers",
    "app_features_configuration_settings",
    "app_features_elfies",
    "app_features_nest_management",
    "app_features_operations",
    "app_features_setup",
    "app_interfaces_api",
    "app_interfaces_cli",
    "app_interfaces_web",
    "app_orchestration_embodiment",
    "app_orchestration_lifecycle",
    "app_orchestration_message_delivery",
    "app_orchestration_nest_session",
    "app_orchestration_observer",
    "app_orchestration_resident_admission",
    "app_orchestration_setup_installation",
    "app_orchestration_crosscutting",
    "app_product_e2e",
}
EXPECTED_BUNDLES = EXPECTED_APP_BUNDLES | {
    "architecture",
    "devtools",
    "e2e",
    "elfie",
    "godot",
    "infrastructure",
    "nest",
    "scripts",
}


def _write_valid_coverage_artifact(path: Path) -> None:
    from coverage import CoverageData

    data = CoverageData(basename=str(path))
    data.add_lines({"test_sample.py": {1}})
    data.write()


def test_bundle_inventory_covers_every_top_level_test_package() -> None:
    assert {
        bundle.bundle_id for bundle in test_bundles.TEST_BUNDLES
    } == EXPECTED_BUNDLES

    app_root = test_bundles.PROJECT_ROOT / "test" / "app"
    app_tests = {
        path.relative_to(test_bundles.PROJECT_ROOT).as_posix()
        for path in app_root.rglob("test_*.py")
    }

    def owns(selector: str, path: str) -> bool:
        selector = selector.rstrip("/")
        return path == selector or path.startswith(f"{selector}/")

    ownership = {
        path: [
            bundle.bundle_id
            for bundle in test_bundles.APP_TEST_BUNDLES
            if any(owns(selector, path) for selector in bundle.selectors)
        ]
        for path in sorted(app_tests)
    }

    assert all(len(owners) == 1 for owners in ownership.values()), ownership
    assert set(ownership) == app_tests


def test_repository_paths_ignore_local_runtime_links_and_generated_roots(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        test_bundles.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            stdout=(
                ".venv\n"
                ".venv/bin/python3\n"
                "venv/bin/python\n"
                "devtools/web/node_modules\n"
                "docs/node_modules/.modules.yaml\n"
                "build/coverage.xml\n"
                "coverage.xml\n"
                "scripts/architecture/validation_cache.py\n"
            )
        ),
    )

    assert test_bundles.repository_paths() == [
        "scripts/architecture/validation_cache.py"
    ]


def test_bundle_inputs_are_conservative_but_do_not_include_unrelated_roots() -> None:
    bundle = test_bundles.bundle_by_id("elfie")
    repository_paths = [
        "app/service.py",
        "docs/guide.md",
        "elfie/brain/service.py",
        "infrastructure/models/client.py",
        "pyproject.toml",
        "test/conftest.py",
        "test/elfie/brain/test_service.py",
        "test/support/provider.py",
    ]

    inputs = set(test_bundles.bundle_input_paths(bundle, repository_paths))

    assert "elfie/brain/service.py" in inputs
    assert "infrastructure/models/client.py" in inputs
    assert "test/elfie/brain/test_service.py" in inputs
    assert "test/conftest.py" in inputs
    assert "test/support/provider.py" in inputs
    assert "pyproject.toml" in inputs
    assert "app/service.py" not in inputs
    assert "docs/guide.md" not in inputs


def test_bundle_inputs_cover_known_cross_root_consumers() -> None:
    repository_paths = [
        "devtools/nest_lab/world.py",
        "nest/public.py",
        "package.json",
        "pnpm-lock.yaml",
        "resources/config/default.yaml",
        "scripts/build_devtools_web.py",
        "test/devtools/nest_lab/test_world.py",
        "test/scripts/test_node_toolchain.py",
    ]

    devtools_inputs = set(
        test_bundles.bundle_input_paths(
            test_bundles.bundle_by_id("devtools"), repository_paths
        )
    )
    scripts_inputs = set(
        test_bundles.bundle_input_paths(
            test_bundles.bundle_by_id("scripts"), repository_paths
        )
    )

    assert "nest/public.py" in devtools_inputs
    assert "scripts/build_devtools_web.py" in devtools_inputs
    assert "nest/public.py" in set(
        test_bundles.bundle_input_paths(
            test_bundles.bundle_by_id("elfie"), repository_paths
        )
    )
    assert "package.json" in scripts_inputs
    assert "pnpm-lock.yaml" in scripts_inputs
    assert "resources/config/default.yaml" in scripts_inputs


def test_bundle_inputs_follow_shared_conftest_and_local_python_imports() -> None:
    repository_paths = [
        "elfie/profile/__init__.py",
        "infrastructure/persistence/configuration/config_store.py",
        "infrastructure/persistence/configuration/documents.py",
        "infrastructure/persistence/configuration/species.py",
        "nest/public.py",
        "test/conftest.py",
        "test/app/conftest.py",
        "test/nest/test_public.py",
    ]

    inputs = set(
        test_bundles.bundle_input_paths(
            test_bundles.bundle_by_id("nest"), repository_paths
        )
    )

    assert "elfie/profile/__init__.py" in inputs
    assert "infrastructure/persistence/configuration/species.py" in inputs
    assert "infrastructure/persistence/configuration/config_store.py" in inputs
    assert "test/app/conftest.py" not in inputs


def test_app_module_inputs_follow_shared_static_dependencies(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(test_bundles, "PROJECT_ROOT", tmp_path)
    for relative, source in {
        "app/features/bodies/service.py": (
            "from app.features.accounts import AccountPrincipal\n"
        ),
        "app/features/accounts/__init__.py": "value = 1\n",
        "app/features/adoption/__init__.py": "value = 1\n",
        "test/app/features/bodies/test_service.py": "def test_service(): pass\n",
        "test/conftest.py": "",
        "pyproject.toml": "[tool.pytest.ini_options]\n",
    }.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    inputs = set(
        test_bundles.bundle_input_paths(
            test_bundles.bundle_by_id("app_features_bodies"),
            [
                "app/features/bodies/service.py",
                "app/features/accounts/__init__.py",
                "app/features/adoption/__init__.py",
                "test/app/features/bodies/test_service.py",
                "test/conftest.py",
                "pyproject.toml",
            ],
        )
    )

    assert "app/features/accounts/__init__.py" in inputs
    assert "app/features/adoption/__init__.py" not in inputs


def test_dynamic_entrypoint_inputs_are_explicit() -> None:
    paths = [
        "app/bootstrap/__init__.py",
        "scripts/elfienest.py",
        "scripts/other_entrypoint.py",
        "test/app/bootstrap/test_cli_configuration.py",
    ]

    inputs = set(
        test_bundles.bundle_input_paths(
            test_bundles.bundle_by_id("app_bootstrap"), paths
        )
    )

    assert "scripts/elfienest.py" in inputs
    assert "scripts/other_entrypoint.py" not in inputs


def test_bundle_fingerprint_is_bound_to_immutable_base(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(validation_cache, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(test_bundles, "PROJECT_ROOT", tmp_path)
    for relative in (
        "app/features/accounts/__init__.py",
        "test/app/features/accounts/test_auth.py",
        "pyproject.toml",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("value = 1\n", encoding="utf-8")
    paths = [
        "app/features/accounts/__init__.py",
        "test/app/features/accounts/test_auth.py",
        "pyproject.toml",
    ]
    bundle = test_bundles.bundle_by_id("app_features_accounts")

    first = test_bundles.bundle_fingerprint(bundle, paths, base_sha="base-a")
    second = test_bundles.bundle_fingerprint(bundle, paths, base_sha="base-b")

    assert first != second


def test_unrelated_content_keeps_bundle_evidence_but_scoped_content_invalidates_it(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(validation_cache, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(test_bundles, "PROJECT_ROOT", tmp_path)
    for relative, source in {
        "app/service.py": "app = 1\n",
        "elfie/brain.py": "elfie = 1\n",
        "infrastructure/client.py": "client = 1\n",
        "pyproject.toml": "[tool.pytest.ini_options]\n",
        "test/conftest.py": "",
        "test/elfie/test_brain.py": "def test_brain(): pass\n",
    }.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    paths = [
        "app/service.py",
        "elfie/brain.py",
        "infrastructure/client.py",
        "pyproject.toml",
        "test/conftest.py",
        "test/elfie/test_brain.py",
    ]
    bundle = test_bundles.bundle_by_id("elfie")

    first = test_bundles.bundle_fingerprint(bundle, paths)
    (tmp_path / "app/service.py").write_text("app = 2\n", encoding="utf-8")
    after_unrelated = test_bundles.bundle_fingerprint(bundle, paths)
    (tmp_path / "elfie/brain.py").write_text("elfie = 2\n", encoding="utf-8")
    after_scoped = test_bundles.bundle_fingerprint(bundle, paths)

    assert after_unrelated == first
    assert after_scoped != first


def test_repository_snapshot_rejects_same_size_same_mtime_content_changes(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(validation_cache, "PROJECT_ROOT", tmp_path)
    path = tmp_path / "candidate.py"
    path.write_bytes(b"value = 1\n")
    original_stat = path.stat()
    snapshot = validation_cache.repository_snapshot(["candidate.py"])

    path.write_bytes(b"value = 2\n")
    os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

    assert not validation_cache.repository_snapshot_current(snapshot, ["candidate.py"])


def test_bundle_cache_requires_both_pass_record_and_coverage_artifact(
    tmp_path: Path,
) -> None:
    key = "a" * 64
    artifact = test_bundles.coverage_artifact_path(tmp_path, key)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    _write_valid_coverage_artifact(artifact)
    cache_store(
        tmp_path,
        key,
        "test-bundle:elfie",
        "content-scoped",
        metadata=test_bundles.coverage_cache_metadata(artifact),
    )

    assert test_bundles.bundle_cache_hit(tmp_path, key)

    artifact.write_bytes(b"corrupt coverage data")

    assert not test_bundles.bundle_cache_hit(tmp_path, key)
    assert not validation_cache.cache_hit(tmp_path, key)


def test_bundle_cache_rejects_legacy_record_and_arbitrary_coverage_bytes(
    tmp_path: Path,
) -> None:
    key = "f" * 64
    artifact = test_bundles.coverage_artifact_path(tmp_path, key)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"coverage-data")
    cache_store(tmp_path, key, "test-bundle:elfie", "content-scoped")

    assert not test_bundles.bundle_cache_hit(tmp_path, key)


def test_bundle_cache_rejects_nonportable_absolute_coverage(tmp_path: Path) -> None:
    key = "w" * 64
    artifact = test_bundles.coverage_artifact_path(tmp_path, key)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    from coverage import CoverageData

    data = CoverageData(basename=str(artifact))
    data.add_lines({str(tmp_path / "foreign" / "module.py"): {1}})
    data.write()
    metadata = test_bundles.coverage_cache_metadata(artifact)
    cache_store(
        tmp_path,
        key,
        "test-bundle:elfie",
        "content-scoped",
        metadata=metadata,
    )

    assert not test_bundles.bundle_cache_hit(tmp_path, key)


def test_new_coverage_fragment_is_normalized_to_relative_paths(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(test_bundles, "PROJECT_ROOT", tmp_path)
    artifact = tmp_path / "coverage.data"
    from coverage import CoverageData

    source_path = tmp_path / "app" / "module.py"
    source_path.parent.mkdir(parents=True)
    data = CoverageData(basename=str(artifact))
    data.add_lines({str(source_path): {1}})
    data.write()

    assert test_bundles._normalize_coverage_artifact(artifact)
    normalized = CoverageData(basename=str(artifact))
    normalized.read()
    assert normalized.measured_files() == {"app/module.py"}


def test_bundle_command_defers_coverage_threshold_until_combination() -> None:
    command = test_bundles.bundle_pytest_command(test_bundles.bundle_by_id("godot"))

    assert "--cov-fail-under=0" in command


def test_test_fingerprint_does_not_include_worktree_local_python_path(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(validation_cache, "PROJECT_ROOT", tmp_path)
    candidate = tmp_path / "candidate.py"
    candidate.write_text("value = 1\n", encoding="utf-8")
    paths = ["candidate.py"]

    monkeypatch.setattr(test_bundles.sys, "executable", "/one/.venv/bin/python3")
    first = test_bundles.focused_test_fingerprint("base", paths, paths)
    monkeypatch.setattr(test_bundles.sys, "executable", "/two/.venv/bin/python3")
    second = test_bundles.focused_test_fingerprint("base", paths, paths)

    assert first == second


def test_run_bundle_reuses_pass_without_starting_pytest(
    tmp_path: Path, monkeypatch
) -> None:
    bundle = test_bundles.bundle_by_id("elfie")
    key = "b" * 64
    artifact = test_bundles.coverage_artifact_path(tmp_path, key)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    _write_valid_coverage_artifact(artifact)
    cache_store(
        tmp_path,
        key,
        "test-bundle:elfie",
        "content-scoped",
        metadata=test_bundles.coverage_cache_metadata(artifact),
    )
    monkeypatch.setattr(test_bundles, "repository_paths", lambda: ["elfie/a.py"])
    monkeypatch.setattr(
        test_bundles,
        "bundle_fingerprint",
        lambda _bundle, _paths, **_kwargs: key,
    )
    monkeypatch.setattr(
        test_bundles,
        "_execute_bundle",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("cached bundle must not start pytest")
        ),
    )

    result = test_bundles.run_bundle(bundle, tmp_path)

    assert result.returncode == 0
    assert result.reused is True
    assert result.artifact == artifact


def test_cached_bundle_revalidates_repository_paths_before_reuse(
    tmp_path: Path, monkeypatch
) -> None:
    bundle = test_bundles.bundle_by_id("elfie")
    key = "g" * 64
    artifact = test_bundles.coverage_artifact_path(tmp_path, key)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    _write_valid_coverage_artifact(artifact)
    cache_store(
        tmp_path,
        key,
        "test-bundle:elfie",
        "content-scoped",
        metadata=test_bundles.coverage_cache_metadata(artifact),
    )
    snapshots = iter((["elfie/a.py"], ["elfie/a.py", "elfie/new.py"]))
    monkeypatch.setattr(test_bundles, "repository_paths", lambda: next(snapshots))
    monkeypatch.setattr(
        test_bundles,
        "bundle_fingerprint",
        lambda _bundle, paths, **_kwargs: key if len(paths) == 1 else "h" * 64,
    )
    executed = []
    monkeypatch.setattr(
        test_bundles,
        "_execute_bundle",
        lambda *_args, **_kwargs: executed.append(True) or 1,
    )

    result = test_bundles.run_bundle(bundle, tmp_path)

    assert result.returncode == 1
    assert executed == [True]


def test_focused_test_evidence_reuses_across_delivery_stages(
    tmp_path: Path, monkeypatch
) -> None:
    key = "d" * 64
    cache_store(tmp_path, key, "focused-pytest", "base")
    monkeypatch.setattr(test_bundles, "changed_paths", lambda _base: ["app/a.py"])
    monkeypatch.setattr(
        test_bundles, "check_fingerprint", lambda *_args, **_kwargs: key
    )
    monkeypatch.setattr(
        test_bundles.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("unchanged focused test evidence must be reused")
        ),
    )

    assert (
        test_bundles.run_focused_tests(["test/app/features/setup"], "base", tmp_path)
        == 0
    )


def test_complete_bundle_selector_uses_bundle_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    expected = test_bundles.BundleRun(
        returncode=0,
        key="e" * 64,
        artifact=tmp_path / "coverage",
        reused=True,
    )
    monkeypatch.setattr(
        test_bundles,
        "run_bundle",
        lambda bundle, cache_root, *, no_cache=False, base_sha="": (
            expected
            if bundle.bundle_id == "godot" and cache_root == tmp_path and not no_cache
            else None
        ),
    )
    monkeypatch.setattr(
        test_bundles,
        "run_focused_tests",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError(
                "a complete bundle must not create separate focused evidence"
            )
        ),
    )

    result = test_bundles.run_selected_tests(["test/godot/"], "base", tmp_path)

    assert result == 0


def test_nested_app_selector_uses_owning_module_bundle(
    tmp_path: Path, monkeypatch
) -> None:
    seen = []

    def run_bundle(bundle, cache_root, *, no_cache=False, base_sha=""):
        seen.append((bundle.bundle_id, base_sha))
        return test_bundles.BundleRun(0, "k", None, False)

    monkeypatch.setattr(test_bundles, "run_bundle", run_bundle)
    monkeypatch.setattr(
        test_bundles,
        "run_focused_tests",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("nested module selectors must use bundle evidence")
        ),
    )

    result = test_bundles.run_selected_tests(
        ["test/app/interfaces/api/v1/admin"], "base-sha", tmp_path
    )

    assert result == 0
    assert seen == [("app_interfaces_api", "base-sha")]


def test_parent_app_selector_expands_to_all_owned_modules(
    tmp_path: Path, monkeypatch
) -> None:
    seen = []

    def run_bundle(bundle, cache_root, *, no_cache=False, base_sha=""):
        seen.append(bundle.bundle_id)
        return test_bundles.BundleRun(0, "k", None, False)

    monkeypatch.setattr(test_bundles, "run_bundle", run_bundle)

    assert (
        test_bundles.run_selected_tests(["test/app/features"], "base-sha", tmp_path)
        == 0
    )
    assert seen == [
        bundle.bundle_id
        for bundle in test_bundles.APP_TEST_BUNDLES
        if bundle.bundle_id.startswith("app_features_")
    ]


def test_focused_test_fingerprint_includes_changed_source(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(validation_cache, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(test_bundles, "PROJECT_ROOT", tmp_path)
    source = tmp_path / "app" / "a.py"
    source.parent.mkdir(parents=True)
    source.write_text("value = 1\n", encoding="utf-8")
    paths = ["app/a.py"]

    first = test_bundles.focused_test_fingerprint("base", ["test/app"], paths)
    source.write_text("value = 2\n", encoding="utf-8")
    after_source = test_bundles.focused_test_fingerprint("base", ["test/app"], paths)

    assert after_source != first


def test_failed_bundle_is_not_recorded_as_pass(tmp_path: Path, monkeypatch) -> None:
    bundle = test_bundles.bundle_by_id("elfie")
    key = "c" * 64
    monkeypatch.setattr(test_bundles, "repository_paths", lambda: ["elfie/a.py"])
    monkeypatch.setattr(
        test_bundles,
        "bundle_fingerprint",
        lambda _bundle, _paths, **_kwargs: key,
    )
    monkeypatch.setattr(test_bundles, "_execute_bundle", lambda *_args: 1)
    artifact = test_bundles.coverage_artifact_path(tmp_path, key)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"old-coverage-data")
    cache_store(tmp_path, key, "test-bundle:elfie", "content-scoped")

    result = test_bundles.run_bundle(bundle, tmp_path, no_cache=True)

    assert result.returncode == 1
    assert result.reused is False
    assert not validation_cache.cache_hit(tmp_path, key)
    assert not artifact.exists()


def test_combined_coverage_enforces_the_repository_threshold_once(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(test_bundles, "PROJECT_ROOT", tmp_path)
    cache_root = tmp_path / "cache"
    artifacts = []
    for name in ("first", "second"):
        artifact = cache_root / f"{name}.coverage"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(name.encode("utf-8"))
        artifacts.append(artifact)
    commands = []
    monkeypatch.setattr(
        test_bundles.subprocess,
        "run",
        lambda command, **_kwargs: (
            commands.append(command) or SimpleNamespace(returncode=0)
        ),
    )

    result = test_bundles.combine_coverage(artifacts, cache_root)

    assert result == 0
    assert [command[3] for command in commands] == [
        "erase",
        "combine",
        "xml",
        "report",
    ]
    assert str(tmp_path / "build" / "coverage.xml") in commands[2]
    assert "--fail-under=0" not in commands[3]


def test_failed_coverage_combine_invalidates_the_involved_bundle_artifacts(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(test_bundles, "PROJECT_ROOT", tmp_path)
    cache_root = tmp_path / "cache"
    key = "i" * 64
    artifact = test_bundles.coverage_artifact_path(cache_root, key)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    _write_valid_coverage_artifact(artifact)
    cache_store(
        cache_root,
        key,
        "test-bundle:elfie",
        "content-scoped",
        metadata=test_bundles.coverage_cache_metadata(artifact),
    )

    def run(command, **_kwargs):
        return SimpleNamespace(returncode=1 if command[3] == "combine" else 0)

    monkeypatch.setattr(test_bundles.subprocess, "run", run)

    assert test_bundles.combine_coverage([artifact], cache_root) == 1
    assert not validation_cache.cache_hit(cache_root, key)
    assert not artifact.exists()


def test_pre_submit_uses_reusable_bundles_instead_of_monolithic_pytest() -> None:
    source = (test_bundles.PROJECT_ROOT / "scripts/pre_submit_gate.sh").read_text(
        encoding="utf-8"
    )

    assert "validation_test_bundles.py" in source
    assert "pytest --cov --cov-report=xml --cov-report=term-missing" not in source
    assert "--direct-main" in source
    assert "BUNDLE_ARGS+=(--no-cache)" in source


def test_coverage_fragments_are_normalized_before_cache_storage() -> None:
    source = (
        test_bundles.PROJECT_ROOT / "scripts/architecture/validation_test_bundles.py"
    ).read_text(encoding="utf-8")

    assert "_normalize_coverage_artifact" in source
    assert '"coverage_paths": "relative"' in source


def test_bundle_fingerprints_can_reuse_one_repository_snapshot(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(validation_cache, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(test_bundles, "PROJECT_ROOT", tmp_path)
    for relative in ("elfie/a.py", "test/elfie/test_a.py", "pyproject.toml"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("value = 1\n", encoding="utf-8")
    paths = ["elfie/a.py", "test/elfie/test_a.py", "pyproject.toml"]
    snapshot = validation_cache.repository_snapshot(paths)

    first = test_bundles.bundle_fingerprint(
        test_bundles.bundle_by_id("elfie"), paths, snapshot=snapshot
    )
    second = test_bundles.bundle_fingerprint(
        test_bundles.bundle_by_id("elfie"), paths, snapshot=snapshot
    )

    assert first == second
