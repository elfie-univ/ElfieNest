"""Baseline and final contracts for ElfieNest runtime installation boundaries."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from app.interfaces.cli import packaged_runtime
from test.support.paths import PROJECT_ROOT


def _write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def test_packaged_runtime_baseline_uses_only_the_app_resource_sibling(
    tmp_path: Path,
) -> None:
    # Given: a standalone installed macOS app layout and no source checkout.
    resources = tmp_path / "ElfieNest.app" / "Contents" / "Resources"
    cli = resources / "management-cli" / "ElfieNestCli"
    core = resources / "python-core" / "ElfieNestCore"
    cli.parent.mkdir(parents=True)
    core.parent.mkdir(parents=True)
    cli.write_bytes(b"cli")
    core.write_bytes(b"core")
    environment: dict[str, str] = {}

    # When: the packaged management CLI discovers its Core runtime.
    packaged_runtime.configure_frozen_cli_runtime(cli, "darwin", environment)

    # Then: it resolves the complete app resource set without a checkout path.
    assert environment == {
        "ELFIENEST_CORE_BIN": str(core),
        "ELFIENEST_WEB_BUILD_DIR": str(resources / "web"),
        "ELFIENEST_GODOT_WEB_DIR": str(resources / "godot-web"),
        "ELFIENEST_BUNDLED_CONFIG_DIR": str(resources / "config"),
        "ELFIENEST_RUNTIME_MODE": "release",
        "ELFIENEST_PROJECT_ROOT": str(resources.parent.parent),
        "ELFIENEST_DESKTOP_BIN": str(resources.parent / "MacOS" / "ElfieNest"),
        "PYINSTALLER_RESET_ENVIRONMENT": "1",
    }


def test_packaged_runtime_reports_a_damaged_install_without_bootstrapping(
    tmp_path: Path,
) -> None:
    # Given: an installed CLI whose packaged Core resource is absent.
    cli = (
        tmp_path
        / "ElfieNest.app"
        / "Contents"
        / "Resources"
        / "management-cli"
        / "ElfieNestCli"
    )
    cli.parent.mkdir(parents=True)
    cli.write_bytes(b"cli")
    environment: dict[str, str] = {}

    # When: the installed CLI resolves its sibling Core runtime.
    with pytest.raises(packaged_runtime.PackagedCliRuntimeError) as error:
        packaged_runtime.configure_frozen_cli_runtime(cli, "darwin", environment)

    # Then: it reports a damaged installation without changing the environment.
    assert "packaged-cli-core-missing" in str(error.value)
    assert environment == {}


def test_linux_packaged_runtime_rejects_a_missing_world_authority(
    tmp_path: Path,
) -> None:
    # Given: a Linux install with Core present but no dedicated Godot executable.
    resources = tmp_path / "opt" / "ElfieNest" / "resources"
    cli = resources / "management-cli" / "ElfieNestCli"
    core = resources / "python-core" / "ElfieNestCore"
    cli.parent.mkdir(parents=True)
    core.parent.mkdir(parents=True)
    cli.write_bytes(b"cli")
    core.write_bytes(b"core")
    environment: dict[str, str] = {}

    # When/Then: startup reports the damaged package before mutating its environment.
    with pytest.raises(
        packaged_runtime.PackagedCliRuntimeError,
        match="packaged-cli-world-runtime-missing",
    ):
        packaged_runtime.configure_frozen_cli_runtime(cli, "linux", environment)
    assert environment == {}


def test_runtime_state_contract_allows_only_source_and_installed_runtime() -> None:
    # Given: the public runtime-state contract.
    expected_states = ("source_development", "installed_runtime")

    # When: its allowed values are enumerated and parsed.
    observed_states = tuple(state.value for state in packaged_runtime.RuntimeState)

    # Then: source development remains separate from installed execution.
    assert observed_states == expected_states
    assert (
        packaged_runtime.parse_runtime_state("source_development")
        is packaged_runtime.RuntimeState.SOURCE_DEVELOPMENT
    )
    assert (
        packaged_runtime.parse_runtime_state("installed_runtime")
        is packaged_runtime.RuntimeState.INSTALLED_RUNTIME
    )


@pytest.mark.parametrize(
    "invalid_runtime_state",
    ("manual_native_package",),
)
def test_runtime_state_contract_rejects_install_methods(
    invalid_runtime_state: str,
) -> None:
    # Given: an install-method value supplied where a runtime state is required.

    # When: the value crosses the runtime-state contract boundary.
    with pytest.raises(packaged_runtime.RuntimeInstallContractError):
        packaged_runtime.parse_runtime_state(invalid_runtime_state)

    # Then: no installation provenance can become a runtime mode.


def test_install_method_contract_allows_only_native_app_packages() -> None:
    # Given: the public application-installation provenance contract.
    expected_methods = ("manual_native_package",)

    # When: its allowed values are enumerated and parsed.
    observed_methods = tuple(method.value for method in packaged_runtime.InstallMethod)

    # Then: development is not counted as an installation method.
    assert observed_methods == expected_methods
    assert (
        packaged_runtime.parse_install_method("manual_native_package")
        is packaged_runtime.InstallMethod.MANUAL_NATIVE_PACKAGE
    )


def test_install_method_contract_rejects_source_development_runtime() -> None:
    # Given: a source-development state supplied where installation provenance is required.

    # When: the value crosses the installation-method contract boundary.
    with pytest.raises(packaged_runtime.RuntimeInstallContractError):
        packaged_runtime.parse_install_method("source_development")

    # Then: development cannot be silently reclassified as an installation path.


def test_source_development_entrypoint_bootstraps_before_dispatch(
    tmp_path: Path,
) -> None:
    # Given: a source checkout with a deterministic bootstrap and CLI fixture.
    checkout = tmp_path / "ElfieNest"
    checkout.mkdir()
    entrypoint = checkout / "elfienest.sh"
    entrypoint.write_bytes((PROJECT_ROOT / "elfienest.sh").read_bytes())
    entrypoint.chmod(0o755)
    bootstrap_log = tmp_path / "bootstrap.log"
    command_log = tmp_path / "command.log"
    _write_executable(
        checkout / "scripts" / "bootstrap.sh",
        (
            "#!/bin/bash\n"
            'printf \'%s\\n\' "$*" >> "$BOOTSTRAP_LOG"\n'
            'if [ "$1" = "report" ]; then\n'
            "  exit 1\n"
            "fi\n"
        ),
    )
    (checkout / "scripts" / "serve.py").write_text("", encoding="utf-8")
    _write_executable(
        checkout / ".venv" / "bin" / "python3",
        '#!/bin/bash\nprintf \'%s\\n\' "$*" > "$COMMAND_LOG"\n',
    )
    environment = os.environ.copy()
    environment.update(
        {
            "BOOTSTRAP_LOG": str(bootstrap_log),
            "COMMAND_LOG": str(command_log),
        }
    )

    # When: the source entrypoint is asked to run a management command.
    result = subprocess.run(
        [str(entrypoint), "version"],
        cwd=checkout,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: it prepares development dependencies before dispatching the checkout CLI.
    assert result.returncode == 0, result.stdout + result.stderr
    # Bootstrap does silent check first, only ensure if missing
    assert bootstrap_log.read_text(encoding="utf-8") == "check --tier=dev\n"
    assert command_log.read_text(encoding="utf-8") == "scripts/elfienest.py version\n"


def test_entrypoint_uses_final_runtime_state_names_not_legacy_mode_names() -> None:
    # Given: the source and installed runtime state contract.
    entrypoint = (PROJECT_ROOT / "elfienest.sh").read_text(encoding="utf-8")

    # When: runtime detection and dispatch are inspected as one executable contract.
    source_state_is_exposed = 'echo "source_development"' in entrypoint
    installed_state_is_exposed = 'echo "installed_runtime"' in entrypoint

    # Then: the shell contract uses the same state names as the typed contract.
    assert source_state_is_exposed
    assert installed_state_is_exposed


@pytest.mark.parametrize(
    ("target", "expected_root", "expected_cli_relative_path"),
    (
        (
            "darwin-arm64",
            Path("/Applications/ElfieNest.app"),
            Path("Contents/Resources/management-cli/ElfieNestCli"),
        ),
        (
            "darwin-x64",
            Path("/Applications/ElfieNest.app"),
            Path("Contents/Resources/management-cli/ElfieNestCli"),
        ),
        (
            "win32-x64",
            Path("C:/Users/Elfie/AppData/Local/Programs/ElfieNest"),
            Path("resources/management-cli/ElfieNestCli.exe"),
        ),
        (
            "linux-x64",
            Path("/home/elfie/.local/opt/ElfieNest"),
            Path("resources/management-cli/ElfieNestCli"),
        ),
    ),
)
def test_canonical_installed_layout_has_one_root_and_app_internal_cli(
    target: str,
    expected_root: Path,
    expected_cli_relative_path: Path,
) -> None:
    # Given: stable home and local-app-data roots for each release target.

    # When: the canonical installed layout is resolved.
    layout = packaged_runtime.canonical_installed_layout(
        packaged_runtime.NativeTarget(target),
        home_directory=Path("/home/elfie"),
        local_app_data=Path("C:/Users/Elfie/AppData/Local"),
    )

    # Then: every target uses its one application root and an in-app CLI path.
    assert layout.application_root == expected_root
    assert layout.management_cli == expected_root / expected_cli_relative_path


def test_native_package_records_the_installed_runtime() -> None:
    # Given: the supported native application installation provenance.

    # When: its completed runtime record is formed.
    record = packaged_runtime.installed_runtime_record(
        packaged_runtime.InstallMethod.MANUAL_NATIVE_PACKAGE
    )

    # Then: the native package enters installed runtime.
    assert record.runtime_state is packaged_runtime.RuntimeState.INSTALLED_RUNTIME
    assert record.install_method is packaged_runtime.InstallMethod.MANUAL_NATIVE_PACKAGE


def test_native_package_exposes_the_installed_manifest_and_setup_surface() -> None:
    # Given: the supported native package for a macOS target.

    # When: its installed runtime surface is formed.
    surface = packaged_runtime.installed_runtime_surface(
        install_method=packaged_runtime.InstallMethod.MANUAL_NATIVE_PACKAGE,
        target=packaged_runtime.NativeTarget.DARWIN_X64,
        home_directory=Path("/home/elfie"),
        local_app_data=Path("C:/Users/Elfie/AppData/Local"),
    )

    # Then: the package enters the app manifest and first-run Setup surface.
    assert surface.manifest_path == Path(
        "/Applications/ElfieNest.app/Contents/Resources/manifest.json"
    )
    assert surface.setup_path == "/setup"
    assert (
        surface.record.runtime_state is packaged_runtime.RuntimeState.INSTALLED_RUNTIME
    )
    assert (
        surface.record.install_method
        is packaged_runtime.InstallMethod.MANUAL_NATIVE_PACKAGE
    )
