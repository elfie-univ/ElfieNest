from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scripts import release
from scripts.internal.release import release_pipeline, release_planning
from test.support.paths import PROJECT_ROOT


def _create_built_desktop_interface(build_root: Path) -> None:
    interface = build_root / "components" / "desktop-interface"
    interface.mkdir(parents=True)
    (interface / "main.js").write_text("export {};\n", encoding="utf-8")


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


def test_release_pipeline_accepts_windows_venv_layout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: a Windows runner's repository-controlled virtual environment.
    executable = tmp_path / ".venv" / "Scripts" / "python.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"python")
    monkeypatch.setattr(release_pipeline, "PROJECT_ROOT", tmp_path)

    # When: the native pipeline resolves the interpreter for a build stage.
    resolved = release_pipeline._project_python()

    # Then: it uses the Windows venv rather than assuming POSIX bin/.
    assert resolved == str(executable)


def test_release_pipeline_uses_bash_for_bootstrap_and_npx_cmd_on_windows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: a Windows-native release runner with Git Bash and npm shims.
    monkeypatch.setattr(release_pipeline.os, "name", "nt")
    monkeypatch.setattr(
        release_pipeline.shutil,
        "which",
        lambda name: "C:/Program Files/Git/bin/bash.exe" if name == "bash" else None,
    )

    # When: shell and Node commands are assembled for the runner.
    bootstrap = release_pipeline._bash_script_command(tmp_path / "scripts/bootstrap.sh")
    npx = release_pipeline._node_command("npx", "--version")

    # Then: Bash owns shell scripts and npx resolves through its Windows shim.
    assert bootstrap == (
        "C:/Program Files/Git/bin/bash.exe",
        str(tmp_path / "scripts/bootstrap.sh"),
    )
    assert npx == ("npx.cmd", "--version")


def test_packaged_cli_imports_when_windows_readline_is_unavailable() -> None:
    # Given: Windows does not provide the POSIX readline extension imported on macOS/Linux.
    entrypoint = PROJECT_ROOT / "scripts" / "elfienest.py"
    probe = f"""
import builtins
import runpy

original_import = builtins.__import__

def import_without_readline(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "readline":
        raise ModuleNotFoundError("No module named 'readline'", name="readline")
    return original_import(name, globals, locals, fromlist, level)

builtins.__import__ = import_without_readline
namespace = runpy.run_path({str(entrypoint)!r}, run_name="elfienest_windows_probe")
assert callable(namespace["main"])
"""

    # When: the frozen CLI entrypoint is imported in that environment.
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    # Then: optional line-editing support cannot prevent the CLI from starting.
    assert result.returncode == 0, result.stderr
    assert "ModuleNotFoundError" not in result.stderr


def test_desktop_release_workflow_has_four_native_targets_and_tag_publish_gate() -> (
    None
):
    # Given: the checked-in GitHub Actions desktop release workflow.
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "release.yml"
    source = workflow_path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(source)
    godot_web = workflow["jobs"]["godot-web"]
    native_build = workflow["jobs"]["build"]
    matrix = native_build["strategy"]["matrix"]["include"]

    # Then: one Linux job exports the platform-neutral Web runtime, each supported
    # package consumes it on a native runner, and publication remains tag-gated.
    assert godot_web["runs-on"] == "ubuntu-latest"
    assert native_build["needs"] == "godot-web"
    assert {entry["target"] for entry in matrix} == set(release.SUPPORTED_TARGETS)
    assert {entry["runner"] for entry in matrix} == {
        "macos-latest",
        "macos-15-intel",
        "windows-latest",
        "ubuntu-latest",
    }
    assert 'tags:\n      - "v*"' in source
    assert "workflow_dispatch:" in source
    assert source.count("ref: ${{ inputs.release_tag || github.ref }}") == 3
    assert workflow["env"]["PYTHONUTF8"] == "1"
    assert source.count("install_official_godot_toolchain") == 1
    assert "name: godot-web-runtime" in source
    assert "name: godot-linux-dedicated-runtime" in source
    assert "build_godot_dedicated.py" in source
    assert "tar -C build/components -czf build/godot-linux-dedicated.tar.gz" in source
    assert "tar -C build/components -xzf" in source
    assert "GODOT_USER_HOME" not in source
    assert "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02" in source
    assert (
        "actions/download-artifact@634f93cb2916e3fdff6788551b99b062d0335ce0" in source
    )
    assert "gh release create" in source
    assert "release_args+=(--prerelease)" in source
    assert "--prebuilt-godot-web" in source
    assert "--run-install-smoke" in source
    assert "dist/ElfieNest-${RELEASE_TARGET}-install-smoke.json" in source
    assert "release-artifacts/*-install-smoke.json" not in source
    assert "SHA256SUMS" not in source
    assert "release-artifacts/manifest.json" not in source
    assert 'test -x "$extract_root/opt/ElfieNest/elfienest-gui"' in source
    assert (
        'test -x "$extract_root/opt/ElfieNest/resources/godot-linux-dedicated/ElfieNestRuntime"'
        in source
    )
    assert 'test -x "$extract_root/usr/bin/elfienest-gui"' not in source

    # Public filenames must describe the platform without exposing the CI-only
    # internal build channel.
    artifact_config = (
        PROJECT_ROOT / "app" / "bootstrap" / "desktop_host" / "electron-builder.yml"
    ).read_text(encoding="utf-8")
    assert "artifactName: ElfieNest-${version}-${os}-${arch}.${ext}" in artifact_config
    assert "-internal-" not in artifact_config


def test_prebuilt_godot_web_step_checks_the_shared_runtime_without_exporting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a native release runner consuming the shared Godot Web artifact.
    commands: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        release_pipeline.check_release_version,
        "check_versions",
        lambda *_args: "0.1.0-beta.1",
    )
    monkeypatch.setattr(
        release_pipeline,
        "_project_python",
        lambda: "/managed/python",
    )
    monkeypatch.setattr(
        release_pipeline,
        "_run_command",
        lambda command, _cwd, _environment=None: commands.append(command),
    )

    # When: concrete steps are created for a prebuilt Godot Web runtime.
    steps = release_pipeline.default_release_steps(prebuilt_godot_web=True)
    steps.build_godot("darwin-arm64")

    # Then: the runner validates the artifact and never requests another Godot export.
    assert commands == [
        (
            "/managed/python",
            "scripts/internal/build/build_godot_web.py",
            "--check",
        )
    ]


def test_prebuilt_linux_godot_step_checks_the_shared_dedicated_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the Linux runner has downloaded both shared Godot artifacts.
    commands: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        release_pipeline.check_release_version,
        "check_versions",
        lambda *_args: "0.1.0-beta.1",
    )
    monkeypatch.setattr(release_pipeline, "_project_python", lambda: "/managed/python")
    monkeypatch.setattr(
        release_pipeline,
        "_run_command",
        lambda command, _cwd, _environment=None: commands.append(command),
    )

    # When: concrete Linux steps validate the prebuilt runtime inputs.
    steps = release_pipeline.default_release_steps(prebuilt_godot_web=True)
    steps.build_godot("linux-x64")

    # Then: Web and Dedicated exports are both checked without rebuilding either one.
    assert commands == [
        (
            "/managed/python",
            "scripts/internal/build/build_godot_web.py",
            "--check",
        ),
        (
            "/managed/python",
            "scripts/internal/build/build_godot_dedicated.py",
            "--check",
        ),
    ]


def test_local_linux_godot_step_exports_web_and_dedicated_runtimes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a Linux release runner with the controlled Godot toolchain available.
    commands: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        release_pipeline.check_release_version,
        "check_versions",
        lambda *_args: "0.1.0-beta.1",
    )
    monkeypatch.setattr(release_pipeline, "_project_python", lambda: "/managed/python")
    monkeypatch.setattr(
        release_pipeline,
        "_run_command",
        lambda command, _cwd, _environment=None: commands.append(command),
    )

    # When: a local Linux release prepares its Godot inputs.
    steps = release_pipeline.default_release_steps()
    steps.build_godot("linux-x64")

    # Then: both required authority surfaces are exported before assembly.
    assert commands == [
        (
            "/managed/python",
            "scripts/internal/build/build_godot_web.py",
            "--ensure",
        ),
        (
            "/managed/python",
            "scripts/internal/build/build_godot_dedicated.py",
        ),
    ]


def test_release_session_dispatches_all_targets_and_requires_artifact_hash_and_smoke(
    tmp_path: Path,
) -> None:
    # Given: four native runners, each returning a verified installer and smoke evidence.
    artifact = tmp_path / "ElfieNest.pkg"
    artifact.write_bytes(b"installer")
    requests = release_planning.release_requests(
        targets=release.SUPPORTED_TARGETS,
        version="0.1.0",
        source_commit="a" * 40,
        input_manifest="b" * 64,
    )
    dispatched: list[str] = []

    def runner(
        request: release_planning.ReleaseRequest,
    ) -> release_planning.RunnerResult:
        dispatched.append(request.target)
        return release_planning.completed_runner_result(
            request,
            artifact=artifact,
            smoke_evidence=f"smoke:{request.target}",
        )

    # When: one coordinator invocation fans out the complete matrix.
    session = release_planning.coordinate_release(
        requests,
        dict.fromkeys(release.SUPPORTED_TARGETS, runner),
    )

    # Then: the aggregate is complete only with one hashed installer and smoke per target.
    assert session.status == "complete"
    assert set(dispatched) == set(release.SUPPORTED_TARGETS)
    assert {result.target for result in session.results} == set(
        release.SUPPORTED_TARGETS
    )
    assert all(result.artifact_sha256 for result in session.results)
    assert all(result.smoke_evidence for result in session.results)


def test_release_session_keeps_successful_artifacts_when_one_runner_is_missing(
    tmp_path: Path,
) -> None:
    # Given: only one native runner is configured for a two-target matrix.
    artifact = tmp_path / "ElfieNest.pkg"
    artifact.write_bytes(b"installer")
    requests = release_planning.release_requests(
        targets=("darwin-arm64", "win32-x64"),
        version="0.1.0",
        source_commit="a" * 40,
        input_manifest="b" * 64,
    )

    # When: the unavailable Windows target is dispatched with the local target.
    session = release_planning.coordinate_release(
        requests,
        {
            "darwin-arm64": lambda request: release_planning.completed_runner_result(
                request,
                artifact=artifact,
                smoke_evidence="smoke:darwin-arm64",
            )
        },
    )

    # Then: the completed artifact remains recorded, while the session is explicitly incomplete.
    assert session.status == "incomplete"
    results = {result.target: result for result in session.results}
    assert results["darwin-arm64"].artifact == artifact
    assert results["win32-x64"].status == "incomplete"
    assert results["win32-x64"].error == "release-runner-unavailable"


def test_release_cli_without_target_requests_the_complete_matrix_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a runner environment where only the coordinator is observed.
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        release.package_python_core, "host_target", lambda: "darwin-arm64"
    )
    monkeypatch.setattr(release, "uses_project_python", lambda: True)
    monkeypatch.setattr(release, "ensure_release_environment", lambda: True)
    monkeypatch.setattr(release, "release_version", lambda: "0.1.0")
    monkeypatch.setattr(release, "source_commit", lambda: "a" * 40)
    monkeypatch.setattr(release, "release_input_manifest", lambda: "b" * 64)
    monkeypatch.setattr(release_pipeline, "default_release_steps", lambda: "steps")

    def coordinate(requests, adapters):
        captured["targets"] = tuple(request.target for request in requests)
        captured["adapters"] = tuple(adapters)
        return release_planning.coordinate_release(requests, {})

    monkeypatch.setattr(release, "coordinate_release", coordinate)

    # When: the publish command is invoked without a target argument.
    result = release.main([])

    # Then: all four targets enter one session, with absent runners reported as incomplete.
    assert result == 3
    assert captured["targets"] == release.SUPPORTED_TARGETS
    assert captured["adapters"] == ("darwin-arm64",)


def test_native_package_output_writes_the_current_native_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: a native build whose installer has not yet received post-install smoke evidence.
    artifact = tmp_path / "ElfieNest.pkg"
    artifact.write_bytes(b"installer")
    output = tmp_path / "artifact-path"
    monkeypatch.setattr(
        release.package_python_core, "host_target", lambda: "darwin-arm64"
    )
    monkeypatch.setattr(release, "uses_project_python", lambda: True)
    monkeypatch.setattr(release, "ensure_release_environment", lambda: True)
    monkeypatch.setattr(release, "release_version", lambda: "0.1.0")
    monkeypatch.setattr(release, "source_commit", lambda: "a" * 40)
    monkeypatch.setattr(release, "release_input_manifest", lambda: "b" * 64)
    monkeypatch.setattr(release_pipeline, "default_release_steps", lambda: "steps")
    monkeypatch.setattr(
        release_pipeline,
        "run_native_release",
        lambda **_kwargs: artifact,
    )

    # When: the native workflow requests the current host artifact path.
    result = release.main(
        ["--target", "darwin-arm64", "--native-package-output", str(output)]
    )

    # Then: it receives the package while release status remains incomplete.
    assert result == 3
    assert output.read_text(encoding="utf-8") == f"{artifact.resolve()}\n"


def test_release_cli_can_close_a_native_target_with_install_smoke_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "ElfieNest.pkg"
    artifact.write_bytes(b"installer")
    evidence = tmp_path / "smoke.json"
    monkeypatch.setattr(
        release.package_python_core, "host_target", lambda: "darwin-arm64"
    )
    monkeypatch.setattr(release, "uses_project_python", lambda: True)
    monkeypatch.setattr(release, "ensure_release_environment", lambda: True)
    monkeypatch.setattr(release, "release_version", lambda: "0.1.0")
    monkeypatch.setattr(release, "source_commit", lambda: "a" * 40)
    monkeypatch.setattr(release, "release_input_manifest", lambda: "b" * 64)
    monkeypatch.setattr(release_pipeline, "default_release_steps", lambda: "steps")
    monkeypatch.setattr(
        release_pipeline,
        "run_native_release",
        lambda **_kwargs: artifact,
    )
    monkeypatch.setattr(
        release,
        "execute_install_smoke",
        lambda _target, _artifact, output, **_kwargs: output.write_text(
            '{"result":"passed"}\n', encoding="utf-8"
        ),
    )

    result = release.main(
        [
            "--target",
            "darwin-arm64",
            "--run-install-smoke",
            "--smoke-evidence-output",
            str(evidence),
        ]
    )

    assert result == 0
    assert evidence.read_text(encoding="utf-8") == '{"result":"passed"}\n'


def test_release_cli_forwards_the_prebuilt_godot_web_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: one native runner whose shared Godot Web artifact was built upstream.
    artifact = tmp_path / "ElfieNest.pkg"
    artifact.write_bytes(b"installer")
    observed: dict[str, bool] = {}
    monkeypatch.setattr(
        release.package_python_core, "host_target", lambda: "darwin-arm64"
    )
    monkeypatch.setattr(release, "uses_project_python", lambda: True)
    monkeypatch.setattr(release, "ensure_release_environment", lambda: True)
    monkeypatch.setattr(release, "release_version", lambda: "0.1.0-beta.1")
    monkeypatch.setattr(release, "source_commit", lambda: "a" * 40)
    monkeypatch.setattr(release, "release_input_manifest", lambda: "b" * 64)

    def default_steps(*, prebuilt_godot_web: bool = False):
        observed["prebuilt_godot_web"] = prebuilt_godot_web
        return "steps"

    monkeypatch.setattr(release_pipeline, "default_release_steps", default_steps)
    monkeypatch.setattr(
        release_pipeline,
        "run_native_release",
        lambda **_kwargs: artifact,
    )

    # When: the release command is told to reuse that artifact.
    result = release.main(["--target", "darwin-arm64", "--prebuilt-godot-web"])

    # Then: the native pipeline receives the explicit reuse contract.
    assert result == 3
    assert observed == {"prebuilt_godot_web": True}


def test_native_pipeline_passes_the_exact_target_to_the_packager(tmp_path) -> None:
    # Given: every checked release stage on one native runner.
    events: list[str] = []
    core = tmp_path / "ElfieNestCore"
    cli = tmp_path / "ElfieNestCli"
    resources = tmp_path / "resources"
    artifact = tmp_path / "ElfieNest-0.1.0-mac-arm64.pkg"

    def package(target: str, received_resources, environment: dict[str, str]):
        assert received_resources == resources
        assert environment["ELFIENEST_TARGET"] == target
        events.append("package")
        return artifact

    steps = release_pipeline.NativeReleaseSteps(
        ensure_dependencies=lambda: events.append("dependencies"),
        build_web=lambda: events.append("web"),
        build_godot=lambda target: events.append(f"godot:{target}"),
        freeze_core=lambda target: events.append("core") or core,
        freeze_cli=lambda target: events.append("cli") or cli,
        assemble=lambda target, received_core, received_cli: (
            assert_release_inputs(target, received_core, received_cli, core, cli),
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
        "godot:darwin-arm64",
        "dependencies",
        "core",
        "cli",
        "assemble",
        "validate",
        "package",
    ]


def assert_release_inputs(target, received_core, received_cli, core, cli) -> None:
    """Keep the assembly assertion out of the one-When pipeline test."""
    assert target == "darwin-arm64"
    assert received_core == core
    assert received_cli == cli


def test_native_pipeline_stops_before_packaging_when_godot_build_fails() -> None:
    # Given: a native pipeline whose mandatory Godot export fails.
    events: list[str] = []
    steps = release_pipeline.NativeReleaseSteps(
        ensure_dependencies=lambda: events.append("dependencies"),
        build_web=lambda: events.append("web"),
        build_godot=lambda _target: (_ for _ in ()).throw(OSError("godot missing")),
        freeze_core=lambda target: events.append("core"),
        freeze_cli=lambda target: events.append("cli"),
        assemble=lambda target, core, cli: events.append("assemble"),
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


def test_default_release_steps_use_the_current_desktop_interface_manifest() -> None:
    # Given: the Desktop interface has moved under the frozen App interface boundary.

    # When: the concrete release pipeline resolves its package roots.

    # Then: it never falls back to the retired top-level desktop directory.
    assert release_pipeline.DESKTOP_DIR == (
        PROJECT_ROOT / "app" / "interfaces" / "desktop"
    )
    assert (release_pipeline.DESKTOP_DIR / "package.json").is_file()
    manifest = json.loads(
        (release_pipeline.DESKTOP_DIR / "package.json").read_text(encoding="utf-8")
    )
    assert manifest["devDependencies"]["electron"] == "37.10.3"
    assert manifest["homepage"] == "https://github.com/elfie-univ/ElfieNest"
    assert manifest["author"]["email"] == "elfie-univ@users.noreply.github.com"


def test_desktop_general_build_does_not_require_the_macos_wifi_helper() -> None:
    # Given: development and test builds run on every supported desktop platform.
    manifest = json.loads(
        (release_pipeline.DESKTOP_DIR / "package.json").read_text(encoding="utf-8")
    )
    scripts = manifest["scripts"]

    # Then: TypeScript compilation is cross-platform, while native packaging opts
    # into the strict macOS helper build explicitly.
    assert "build_macos_wifi_helper.mjs" not in scripts["build"]
    assert scripts["build:macos-helper"] == "node scripts/build_macos_wifi_helper.mjs"
    assert "pnpm build:macos-helper" in scripts["package"]


def test_desktop_packaging_uses_only_the_current_brand_icon() -> None:
    # Given: the public App icon is the current brand source approved for releases.
    current_brand_icon = PROJECT_ROOT / "docs/public/assets/elfienest-app-icon.png"
    desktop_icon = release_pipeline.DESKTOP_DIR / "assets/elfienest-app-icon.png"
    macos_icon = release_pipeline.DESKTOP_DIR / "assets/elfienest-macos-app-icon.png"
    retired_icon = release_pipeline.DESKTOP_DIR / "assets/elfienest.png"
    builder_config = (
        PROJECT_ROOT / "app/bootstrap/desktop_host/electron-builder.yml"
    ).read_text(encoding="utf-8")
    builder = yaml.safe_load(builder_config)

    # When/Then: Windows/Linux retain the identical brand source, while macOS uses
    # a padded transparent app-icon canvas instead of the retired full-bleed square.
    assert desktop_icon.read_bytes() == current_brand_icon.read_bytes()
    assert macos_icon.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert macos_icon.read_bytes() != desktop_icon.read_bytes()
    assert builder["mac"]["icon"] == "assets/elfienest-macos-app-icon.png"
    assert builder["extraResources"] == [{"from": "packaged-resources", "to": "."}]
    assert builder["mac"]["extraResources"] == [
        {"from": "desktop-interface/macos", "to": "wifi-access-helper"}
    ]
    assert "target: [pkg]" in builder_config
    assert "scripts: packaging/macos" in builder_config
    assert "win:\n  icon: assets/elfienest-app-icon.png" in builder_config
    assert "include: packaging/windows/installer.nsh" in builder_config
    assert "linux:\n  icon: assets/elfienest-app-icon.png" in builder_config
    assert "executableName: elfienest-gui" in builder_config
    assert "target: [deb]" in builder_config
    assert "afterInstall: packaging/linux/after-install.sh" in builder_config
    assert not retired_icon.exists()


def test_native_installers_publish_the_global_cli_launcher_contract() -> None:
    # Given: the native installer hooks used by the packaged application.
    packaging = PROJECT_ROOT / "app" / "bootstrap" / "desktop_host" / "packaging"
    mac = (packaging / "macos" / "postinstall").read_text(encoding="utf-8")
    linux_install = (packaging / "linux" / "after-install.sh").read_text(
        encoding="utf-8"
    )
    linux_remove = (packaging / "linux" / "after-remove.sh").read_text(encoding="utf-8")
    windows = (packaging / "windows" / "installer.nsh").read_text(encoding="utf-8")

    # Then: each installer creates/removes only the packaged management CLI launcher.
    assert "/usr/local/bin/elfienest" in mac
    assert 'target_root="${3:-/}"' in mac
    assert 'app="${target_root%/}/Applications/ElfieNest.app"' in mac
    assert 'cli="$app/Contents/Resources/management-cli/ElfieNestCli"' in mac
    assert "LaunchServices.framework/Support/lsregister" in mac
    assert "stat -f '%Su' /dev/console" in mac
    assert "launchctl asuser" in mac
    assert "-gc" in mac
    assert '-f "$app"' in mac
    assert "install_owned_launcher" in mac
    assert 'readlink "$launcher"' in mac
    assert "Refusing to replace launcher not owned by ElfieNest" in mac
    assert "ln -sfn" not in mac
    assert "/usr/local/bin/elfienest" in linux_install
    assert 'app_root="/opt/ElfieNest"' in linux_install
    assert 'gui="$app_root/elfienest-gui"' in linux_install
    assert "install_owned_launcher" in linux_install
    assert 'readlink "$launcher"' in linux_install
    assert "Refusing to replace launcher not owned by ElfieNest" in linux_install
    assert "ln -sfn" not in linux_install
    assert "resources/management-cli/ElfieNestCli" in linux_install
    assert "/usr/bin/elfienest-gui" in linux_remove
    assert "resources/management-cli/ElfieNestCli" in linux_remove
    assert 'cli="/opt/ElfieNest/resources/management-cli/ElfieNestCli"' in linux_remove
    assert 'remove_owned_launcher "$launcher" "$cli"' in linux_remove
    assert "*/resources/management-cli/ElfieNestCli" not in linux_remove
    assert "management-cli\\ElfieNestCli.exe" in windows
    assert "customInstall" in windows
    assert "Call ElfieNestAddLauncherPath" not in windows
    assert "Function ElfieNestAddLauncherPath" not in windows
    assert "!ifndef BUILD_UNINSTALLER\n${StrStr}\n!else\n${UnStrRep}\n!endif" in windows
    assert "customUnInstall" in windows
    # Defining customRemoveFiles would bypass electron-builder's standard
    # recursive application-file cleanup.
    assert "customRemoveFiles" not in windows
    assert "Call un.ElfieNestRemoveLauncherPath" in windows
    assert "Function un.ElfieNestRemoveLauncherPath" in windows
    assert "${UnStrRep}" in windows
    assert "\n${StrRep}\n" not in windows
    assert "Call ElfieNestRemoveLauncherPath" not in windows
    assert '${StrStr} $2 $1 ";$INSTDIR\\bin;"' in windows
    assert '${UnStrRep} $2 $1 ";$INSTDIR\\bin;" ";"' in windows
    assert 'Delete "$INSTDIR\\bin\\elfienest.cmd"' in windows


def test_release_cli_only_reports_success_after_its_native_pipeline_finishes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: an otherwise native release request with a deterministic pipeline.
    artifact = tmp_path / "ElfieNest-0.1.0-mac-arm64.pkg"
    calls: list[str] = []
    monkeypatch.setattr(
        release.package_python_core, "host_target", lambda: "darwin-arm64"
    )
    monkeypatch.setattr(release, "uses_project_python", lambda: True)
    monkeypatch.setattr(
        release, "ensure_release_environment", lambda: calls.append("sync") or True
    )
    monkeypatch.setattr(release_pipeline, "default_release_steps", lambda: "steps")
    monkeypatch.setattr(
        release_pipeline,
        "run_native_release",
        lambda target, host_target, steps: calls.append(target) or artifact,
    )

    # When: the command coordinates the current host target.
    result = release.main(["--target", "darwin-arm64"])

    # Then: a built artifact is still incomplete until an installation smoke proves it.
    assert result == 3
    assert calls == ["sync", "darwin-arm64"]


def test_release_artifact_output_is_available_only_for_one_complete_native_target(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: a native build that returns one installer path.
    artifact = tmp_path / "ElfieNest.pkg"
    output = tmp_path / "artifact-path"
    monkeypatch.setattr(
        release.package_python_core, "host_target", lambda: "darwin-arm64"
    )
    monkeypatch.setattr(release, "uses_project_python", lambda: True)
    monkeypatch.setattr(release, "ensure_release_environment", lambda: True)
    monkeypatch.setattr(release_pipeline, "default_release_steps", lambda: "steps")
    monkeypatch.setattr(
        release_pipeline,
        "run_native_release",
        lambda *args, **kwargs: artifact,
    )

    # When: a caller requests a completed release artifact through its dedicated file.
    result = release.main(
        ["--target", "darwin-arm64", "--artifact-output", str(output)]
    )

    # Then: the artifact path stays unavailable until native installation smoke completes.
    assert result == 2
    assert not output.exists()


def test_release_cli_reports_a_remote_target_without_initializing_local_builds(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Given: a macOS runner asked only to coordinate a Windows release target.
    monkeypatch.setattr(
        release.package_python_core, "host_target", lambda: "darwin-arm64"
    )
    monkeypatch.setattr(
        release_pipeline,
        "default_release_steps",
        lambda: (_ for _ in ()).throw(AssertionError("local pipeline must stay idle")),
    )

    # When: no requested target belongs to this runner.
    result = release.main(["--target", "win32-x64"])

    # Then: the result is explicitly incomplete, rather than a local build failure.
    assert result == 3
    assert (
        "release-target-incomplete target=win32-x64 reason=release-runner-unavailable"
        in capsys.readouterr().out
    )


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
    assert (
        f"release-target-incomplete target={remote} reason=release-runner-unavailable"
        in result.stdout
    )
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
    # Given: a target staging root and an Electron command adapter that produces one PKG.
    build_root = tmp_path / "build"
    dist_root = tmp_path / "dist"
    resources = build_root / "staging" / "darwin-arm64" / "resources"
    resources.mkdir(parents=True)
    _create_built_desktop_interface(build_root)
    observed_environment: dict[str, str] = {}

    def run_builder(command, cwd, environment) -> None:
        observed_environment.update(environment or {})
        if not any("electron-builder" in argument for argument in command):
            return
        assert cwd == build_root / "desktop-host-app" / "darwin-arm64"
        assert (cwd / "bootstrap" / "desktop_host.mjs").is_file()
        assert (cwd / "desktop-interface" / "main.js").is_file()
        assert (cwd / "packaged-resources").is_dir()
        assert (cwd / "packaging" / "windows" / "installer.nsh").is_file()
        assert (cwd / "packaging" / "linux" / "after-install.sh").is_file()
        assert (cwd / "packaging" / "macos" / "postinstall").is_file()
        assert (cwd / "assets" / "elfienest-tray-icon.png").read_bytes() == (
            PROJECT_ROOT
            / "docs"
            / "public"
            / "assets"
            / "elfienest-logo-mark-transparent.png"
        ).read_bytes()
        output_argument = next(
            value
            for value in command
            if value.startswith("--config.directories.output=")
        )
        output = Path(output_argument.split("=", 1)[1])
        output.mkdir(parents=True)
        (output / "ElfieNest-0.1.0-mac-arm64.pkg").write_bytes(b"installer")

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
    assert artifact == dist_root / "ElfieNest-0.1.0-mac-arm64.pkg"
    assert artifact.read_bytes() == b"installer"
    assert observed_environment["ELFIENEST_TARGET"] == "darwin-arm64"
    assert observed_environment["ELFIENEST_PROJECT_ROOT"] == str(PROJECT_ROOT)
    assert not (build_root / "package-output" / "darwin-arm64").exists()
    assert not (build_root / "desktop-host-app" / "darwin-arm64").exists()


def test_windows_installer_discovery_ignores_builder_work_files(
    tmp_path: Path,
) -> None:
    # Given: electron-builder emitted one installer alongside its transient
    # uninstaller and executable files nested in the unpacked application.
    installer = tmp_path / "ElfieNest-0.1.0-beta.1-win-x64.exe"
    installer.write_bytes(b"installer")
    (tmp_path / "ElfieNest-0.1.0-beta.1-win-x64.__uninstaller.exe").write_bytes(
        b"temporary"
    )
    unpacked = tmp_path / "win-unpacked"
    unpacked.mkdir()
    (unpacked / "ElfieNest.exe").write_bytes(b"application")
    resources = unpacked / "resources" / "management-cli"
    resources.mkdir(parents=True)
    (resources / "ElfieNestCli.exe").write_bytes(b"cli")

    # When: the release pipeline discovers publishable Windows artifacts.
    artifacts = release_pipeline._installer_artifacts(tmp_path, "win32-x64")

    # Then: only the top-level final installer can be promoted into dist/.
    assert artifacts == (installer,)


def test_packager_rebuilds_the_electron_shell_before_creating_the_installer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: a staging root whose Electron shell must be rebuilt from current TypeScript.
    build_root = tmp_path / "build"
    dist_root = tmp_path / "dist"
    resources = build_root / "staging" / "darwin-arm64" / "resources"
    resources.mkdir(parents=True)
    _create_built_desktop_interface(build_root)
    commands: list[tuple[str, ...]] = []

    def run_builder(command, cwd, environment) -> None:
        commands.append(command)
        if not any("electron-builder" in argument for argument in command):
            return
        output_argument = next(
            value
            for value in command
            if value.startswith("--config.directories.output=")
        )
        output = Path(output_argument.split("=", 1)[1])
        output.mkdir(parents=True)
        (output / "ElfieNest-0.1.0-mac-arm64.pkg").write_bytes(b"installer")

    monkeypatch.setattr(release_pipeline, "BUILD_DIR", build_root)
    monkeypatch.setattr(release_pipeline, "DIST_DIR", dist_root)
    monkeypatch.setattr(release_pipeline, "_run_command", run_builder)

    # When: the package stage builds one target-native installer.
    release_pipeline._package_installer(
        "darwin-arm64",
        resources,
        {"ELFIENEST_TARGET": "darwin-arm64"},
    )

    # Then: locked dependencies, TypeScript, and the macOS-only helper precede
    # electron-builder.
    assert commands[0] == (
        "npx",
        "--yes",
        "pnpm@10.12.1",
        "install",
        "--frozen-lockfile",
    )
    assert commands[1] == ("npx", "--yes", "pnpm@10.12.1", "build")
    assert commands[2] == (
        "npx",
        "--yes",
        "pnpm@10.12.1",
        "build:macos-helper",
    )
    assert commands[3][:7] == (
        "npx",
        "--yes",
        "pnpm@10.12.1",
        "--dir",
        str(release_pipeline.DESKTOP_DIR),
        "exec",
        "electron-builder",
    )
    project_index = commands[3].index("--projectDir")
    assert commands[3][project_index + 1] == str(
        build_root / "desktop-host-app" / "darwin-arm64"
    )
    config_index = commands[3].index("--config")
    assert commands[3][config_index + 1].endswith(
        "app/bootstrap/desktop_host/electron-builder.yml"
    )


def test_packager_does_not_build_the_macos_wifi_helper_for_windows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: a Windows-native package stage.
    build_root = tmp_path / "build"
    dist_root = tmp_path / "dist"
    resources = build_root / "staging" / "win32-x64" / "resources"
    resources.mkdir(parents=True)
    _create_built_desktop_interface(build_root)
    commands: list[tuple[str, ...]] = []

    def run_builder(command, _cwd, _environment) -> None:
        commands.append(command)
        if not any("electron-builder" in argument for argument in command):
            return
        output_argument = next(
            value
            for value in command
            if value.startswith("--config.directories.output=")
        )
        output = Path(output_argument.split("=", 1)[1])
        output.mkdir(parents=True)
        (output / "ElfieNest-0.1.0-win-x64.exe").write_bytes(b"installer")

    monkeypatch.setattr(release_pipeline, "BUILD_DIR", build_root)
    monkeypatch.setattr(release_pipeline, "DIST_DIR", dist_root)
    monkeypatch.setattr(release_pipeline, "_run_command", run_builder)

    # When: the package stage creates a Windows installer.
    release_pipeline._package_installer(
        "win32-x64",
        resources,
        {"ELFIENEST_TARGET": "win32-x64"},
    )

    # Then: it never invokes the macOS-only helper compiler.
    assert not any("build:macos-helper" in command for command in commands)


def test_packager_replaces_a_previous_same_version_local_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: a completed local build for the same internal version already exists.
    build_root = tmp_path / "build"
    dist_root = tmp_path / "dist"
    resources = build_root / "staging" / "darwin-arm64" / "resources"
    resources.mkdir(parents=True)
    _create_built_desktop_interface(build_root)
    destination = dist_root / "ElfieNest-0.1.0-mac-arm64.pkg"
    destination.parent.mkdir()
    destination.write_bytes(b"previous")

    def run_builder(command, cwd, environment) -> None:
        if not any("electron-builder" in argument for argument in command):
            return
        output_argument = next(
            value
            for value in command
            if value.startswith("--config.directories.output=")
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
