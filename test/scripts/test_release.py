from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts import release, release_pipeline
from test.support.paths import PROJECT_ROOT


def test_release_plan_keeps_non_native_targets_as_explicit_runner_work() -> None:
    # Given: a release coordinator on macOS ARM with two requested targets.
    requested = ("darwin-arm64", "win32-x64")

    # When: it plans the complete release matrix.
    plan = release.plan_release(requested_targets=requested, host_target="darwin-arm64")

    # Then: the local runner builds its target and reports—not discards—the other one.
    assert plan.native_targets == ("darwin-arm64",)
    assert plan.requires_native_runner == ("win32-x64",)
    assert plan.is_complete is False


def test_release_plan_rejects_an_unknown_target() -> None:
    # Given: a requested target outside the checked-in release matrix.

    # When/Then: planning fails before it can declare any release work successful.
    with pytest.raises(release.ReleasePlanError, match="unsupported"):
        release.plan_release(
            requested_targets=("darwin-arm64", "freebsd-x64"),
            host_target="darwin-arm64",
        )


def test_native_pipeline_passes_the_exact_target_to_the_packager(tmp_path) -> None:
    # Given: every checked release stage on one native runner.
    events: list[str] = []
    core = tmp_path / "ElfieNestCore"
    cli = tmp_path / "ElfieNestCli"
    archive = tmp_path / "ollama-darwin.tgz"
    resources = tmp_path / "resources"
    artifact = tmp_path / "ElfieNest-0.1.0-internal-mac-arm64.dmg"

    def package(target: str, received_resources, environment: dict[str, str]):
        assert received_resources == resources
        assert environment["ELFIENEST_TARGET"] == target
        events.append("package")
        return artifact

    steps = release_pipeline.NativeReleaseSteps(
        ensure_dependencies=lambda: events.append("dependencies"),
        build_web=lambda: events.append("web"),
        build_godot=lambda: events.append("godot"),
        freeze_core=lambda target: events.append("core") or core,
        freeze_cli=lambda target: events.append("cli") or cli,
        download_sidecar=lambda target: events.append("sidecar") or archive,
        assemble=lambda target, received_core, received_cli, received_archive: (
            assert_release_inputs(
                target, received_core, received_cli, received_archive, core, cli, archive
            ),
            events.append("assemble"),
            resources,
        )[-1],
        validate=lambda received_resources: events.append("validate"),
        package=package,
    )

    # When: the native pipeline executes.
    result = release_pipeline.run_native_release(
        target="darwin-arm64",
        host_target="darwin-arm64",
        steps=steps,
    )

    # Then: all required stages run before the target-scoped installer command.
    assert result == artifact
    assert events == [
        "web",
        "godot",
        "dependencies",
        "core",
        "cli",
        "sidecar",
        "assemble",
        "validate",
        "package",
    ]


def assert_release_inputs(
    target, received_core, received_cli, received_archive, core, cli, archive
) -> None:
    """Keep the assembly assertion out of the one-When pipeline test."""
    assert target == "darwin-arm64"
    assert received_core == core
    assert received_cli == cli
    assert received_archive == archive


def test_native_pipeline_stops_before_packaging_when_godot_build_fails() -> None:
    # Given: a native pipeline whose mandatory Godot export fails.
    events: list[str] = []
    steps = release_pipeline.NativeReleaseSteps(
        ensure_dependencies=lambda: events.append("dependencies"),
        build_web=lambda: events.append("web"),
        build_godot=lambda: (_ for _ in ()).throw(OSError("godot missing")),
        freeze_core=lambda target: events.append("core"),
        freeze_cli=lambda target: events.append("cli"),
        download_sidecar=lambda target: events.append("sidecar"),
        assemble=lambda target, core, cli, archive: events.append("assemble"),
        validate=lambda resources: events.append("validate"),
        package=lambda target, resources, environment: events.append("package"),
    )

    # When/Then: failure is explicit and no later stage can create an installer.
    with pytest.raises(release_pipeline.ReleasePipelineError, match="stage=godot"):
        release_pipeline.run_native_release(
            target="darwin-arm64",
            host_target="darwin-arm64",
            steps=steps,
        )
    assert events == ["web"]


def test_release_cli_only_reports_success_after_its_native_pipeline_finishes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: an otherwise native release request with a deterministic pipeline.
    artifact = tmp_path / "ElfieNest-0.1.0-internal-mac-arm64.dmg"
    calls: list[str] = []
    monkeypatch.setattr(release.package_python_core, "host_target", lambda: "darwin-arm64")
    monkeypatch.setattr(release, "uses_project_python", lambda: True)
    monkeypatch.setattr(release, "ensure_release_environment", lambda: calls.append("sync") or True)
    monkeypatch.setattr(release_pipeline, "default_release_steps", lambda: "steps")
    monkeypatch.setattr(
        release_pipeline,
        "run_native_release",
        lambda target, host_target, steps: calls.append(target) or artifact,
    )

    # When: the command coordinates the current host target.
    result = release.main(["--target", "darwin-arm64"])

    # Then: exit zero is only possible after the native installer pipeline ran.
    assert result == 0
    assert calls == ["sync", "darwin-arm64"]


def test_release_artifact_output_is_available_only_for_one_complete_native_target(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: a native build that returns one installer path.
    artifact = tmp_path / "ElfieNest.dmg"
    output = tmp_path / "artifact-path"
    monkeypatch.setattr(release.package_python_core, "host_target", lambda: "darwin-arm64")
    monkeypatch.setattr(release, "uses_project_python", lambda: True)
    monkeypatch.setattr(release, "ensure_release_environment", lambda: True)
    monkeypatch.setattr(release_pipeline, "default_release_steps", lambda: "steps")
    monkeypatch.setattr(
        release_pipeline,
        "run_native_release",
        lambda *args, **kwargs: artifact,
    )

    # When: an installer caller requests the artifact through its dedicated file.
    result = release.main(["--target", "darwin-arm64", "--artifact-output", str(output)])

    # Then: it receives exactly the completed installer path, not parsed console output.
    assert result == 0
    assert output.read_text(encoding="utf-8") == f"{artifact.resolve()}\n"


def test_release_cli_reports_a_remote_target_without_initializing_local_builds(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: a macOS runner asked only to coordinate a Windows release target.
    monkeypatch.setattr(release.package_python_core, "host_target", lambda: "darwin-arm64")
    monkeypatch.setattr(
        release_pipeline,
        "default_release_steps",
        lambda: (_ for _ in ()).throw(AssertionError("local pipeline must stay idle")),
    )

    # When: no requested target belongs to this runner.
    result = release.main(["--target", "win32-x64"])

    # Then: the result is explicitly incomplete, rather than a local build failure.
    assert result == 3
    assert "release-target-requires-native-runner target=win32-x64" in capsys.readouterr().out


def test_documented_direct_release_script_resolves_the_repository_package() -> None:
    # Given: a target which this runner must only coordinate, not build.
    host = release.package_python_core.host_target()
    remote = next(target for target in release.SUPPORTED_TARGETS if target != host)

    # When: the documented direct-script invocation is executed from the repository root.
    result = subprocess.run(
        [sys.executable, "scripts/release.py", "--target", remote],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    # Then: it imports the package and explicitly requests the matching native runner.
    assert result.returncode == 3
    assert f"release-target-requires-native-runner target={remote}" in result.stdout
    assert "ModuleNotFoundError" not in result.stderr


def test_native_direct_script_refuses_an_unmanaged_python_before_building() -> None:
    # Given: the local host target is requested through the base interpreter, not .venv.
    host = release.package_python_core.host_target()
    unmanaged_python = Path(sys.base_prefix) / "bin" / "python3.9"
    if not unmanaged_python.is_file():
        pytest.skip("The active base interpreter path is unavailable for this check")

    # When: the direct script invocation does not use the repository virtual environment.
    result = subprocess.run(
        [str(unmanaged_python), "scripts/release.py", "--target", host],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    # Then: it refuses before importing/building release dependencies or creating artifacts.
    assert result.returncode == 2
    assert "release-python-required" in result.stdout
    assert "Traceback" not in result.stderr


def test_packager_publishes_only_the_verified_single_native_installer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: a target staging root and an Electron command adapter that produces one DMG.
    build_root = tmp_path / "build"
    dist_root = tmp_path / "dist"
    resources = build_root / "staging" / "darwin-arm64" / "resources"
    resources.mkdir(parents=True)
    observed_environment: dict[str, str] = {}

    def run_builder(command, cwd, environment) -> None:
        observed_environment.update(environment or {})
        output_argument = next(
            value for value in command if value.startswith("--config.directories.output=")
        )
        output = Path(output_argument.split("=", 1)[1])
        output.mkdir(parents=True)
        (output / "ElfieNest-0.1.0-internal-mac-arm64.dmg").write_bytes(b"installer")

    monkeypatch.setattr(release_pipeline, "BUILD_DIR", build_root)
    monkeypatch.setattr(release_pipeline, "DIST_DIR", dist_root)
    monkeypatch.setattr(release_pipeline, "_run_command", run_builder)

    # When: Electron packaging succeeds with one target-native installer file.
    artifact = release_pipeline._package_installer(
        "darwin-arm64",
        resources,
        {"ELFIENEST_TARGET": "darwin-arm64"},
    )

    # Then: only the final installer appears in dist and its target reaches the builder.
    assert artifact == dist_root / "ElfieNest-0.1.0-internal-mac-arm64.dmg"
    assert artifact.read_bytes() == b"installer"
    assert observed_environment["ELFIENEST_TARGET"] == "darwin-arm64"
    assert not (build_root / "package-output" / "darwin-arm64").exists()


def test_packager_replaces_a_previous_same_version_local_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: a completed local build for the same internal version already exists.
    build_root = tmp_path / "build"
    dist_root = tmp_path / "dist"
    resources = build_root / "staging" / "darwin-arm64" / "resources"
    resources.mkdir(parents=True)
    destination = dist_root / "ElfieNest-0.1.0-internal-mac-arm64.dmg"
    destination.parent.mkdir()
    destination.write_bytes(b"previous")

    def run_builder(command, cwd, environment) -> None:
        output_argument = next(
            value for value in command if value.startswith("--config.directories.output=")
        )
        output = Path(output_argument.split("=", 1)[1])
        output.mkdir(parents=True)
        (output / destination.name).write_bytes(b"replacement")

    monkeypatch.setattr(release_pipeline, "BUILD_DIR", build_root)
    monkeypatch.setattr(release_pipeline, "DIST_DIR", dist_root)
    monkeypatch.setattr(release_pipeline, "_run_command", run_builder)

    # When: the verified package stage completes again.
    artifact = release_pipeline._package_installer(
        "darwin-arm64", resources, {"ELFIENEST_TARGET": "darwin-arm64"}
    )

    # Then: the final artifact is updated only after the new package exists.
    assert artifact == destination
    assert destination.read_bytes() == b"replacement"
