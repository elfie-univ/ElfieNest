from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from test.scripts.bootstrap_test_support import (
    copy_bootstrap,
    make_executable,
    make_project_python,
    prepare_build_runtime,
    run_bootstrap,
)
from test.support.paths import PROJECT_ROOT


def test_bootstrap_ensure_build_fails_when_godot_web_runtime_is_missing(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    scripts_dir = copy_bootstrap(project_root)
    prepare_build_runtime(project_root, godot_web=False)
    elfie_home = tmp_path / "elfie-home"
    elfie_home.mkdir()

    result = subprocess.run(
        ["bash", str(scripts_dir / "bootstrap.sh"), "ensure", "--tier=build"],
        cwd=project_root,
        env={
            **os.environ,
            "ELFIE_HOME": str(elfie_home),
            "HOME": str(tmp_path / "home"),
            "PATH": f"{project_root / '.fake-bin'}:/usr/bin:/bin:/usr/sbin:/sbin",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Godot Web Runtime missing" in result.stderr
    assert "full product cannot start" in result.stderr


def test_bootstrap_report_completes_in_isolated_home(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    scripts_dir = copy_bootstrap(project_root)
    prepare_build_runtime(project_root)
    elfie_home = tmp_path / "elfie-home"
    elfie_home.mkdir()

    result = run_bootstrap(scripts_dir, project_root, elfie_home)

    assert result.returncode == 0, result.stderr
    assert result.stdout


def test_bootstrap_report_marks_missing_godot_as_required_failure(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    scripts_dir = copy_bootstrap(project_root)
    prepare_build_runtime(project_root, godot_web=False)
    elfie_home = tmp_path / "elfie-home"
    elfie_home.mkdir()

    result = run_bootstrap(scripts_dir, project_root, elfie_home)

    assert result.returncode == 1, result.stderr
    report = json.loads(result.stdout)
    assert report["overall_state"] == "failed"
    assert report["components"]["godot_web"] == {
        "required": True,
        "state": "missing",
    }


def test_bootstrap_dev_report_requires_electron_authority_host(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    scripts_dir = copy_bootstrap(project_root)
    prepare_build_runtime(project_root)
    elfie_home = tmp_path / "elfie-home"
    elfie_home.mkdir()
    make_executable(
        project_root / ".fake-bin/node",
        "#!/bin/sh\nprintf 'v20.12.0\\n'\n",
    )
    make_executable(project_root / "app/interfaces/desktop/node_modules/.bin/electron")

    result = subprocess.run(
        ["bash", str(scripts_dir / "bootstrap.sh"), "report", "--tier=dev"],
        cwd=project_root,
        env={
            **os.environ,
            "ELFIE_HOME": str(elfie_home),
            "HOME": str(tmp_path / "home"),
            "PATH": f"{project_root / '.fake-bin'}:/usr/bin:/bin:/usr/sbin:/sbin",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["overall_state"] == "failed"
    assert report["components"]["electron"] == {
        "required": True,
        "state": "missing",
    }


def test_bootstrap_ensure_dev_builds_electron_authority_host(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    scripts_dir = copy_bootstrap(project_root)
    prepare_build_runtime(project_root)
    elfie_home = tmp_path / "elfie-home"
    elfie_home.mkdir()
    desktop_dir = project_root / "app/interfaces/desktop"
    desktop_dir.mkdir(parents=True)
    (desktop_dir / "package.json").write_text("{}\n", encoding="utf-8")
    for relative_path in (
        "app/bootstrap/desktop_host/host_main.mjs",
        "infrastructure/godot/lifecycle/electron/authority_main.mjs",
    ):
        destination = project_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PROJECT_ROOT / relative_path, destination)
    make_executable(
        project_root / ".fake-bin/node",
        "#!/bin/sh\nprintf 'v20.12.0\\n'\n",
    )
    make_executable(
        project_root / ".fake-bin/pnpm",
        "#!/bin/sh\n"
        'if [ "$1" = "--version" ]; then printf "10.12.1\\n"; exit 0; fi\n'
        'if [ "$1" = "install" ]; then mkdir -p node_modules/.bin; '
        'printf "#!/bin/sh\\nexit 0\\n" > node_modules/.bin/electron; '
        "chmod +x node_modules/.bin/electron; exit 0; fi\n"
        'if [ "$1" = "rebuild" ] && [ "$2" = "electron" ]; then exit 0; fi\n'
        'if [ "$1" = "build" ]; then mkdir -p ../../../build/components/desktop-interface; '
        'printf "built\\n" > ../../../build/components/desktop-interface/main.js; exit 0; fi\n'
        "exit 1\n",
    )

    result = subprocess.run(
        ["bash", str(scripts_dir / "bootstrap.sh"), "ensure", "--tier=dev"],
        cwd=project_root,
        env={
            **os.environ,
            "ELFIE_HOME": str(elfie_home),
            "HOME": str(tmp_path / "home"),
            "PATH": f"{project_root / '.fake-bin'}:/usr/bin:/bin:/usr/sbin:/sbin",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (project_root / "build/components/desktop-interface/main.js").is_file()
    assert "Electron authority host is ready" in result.stdout


def test_bootstrap_report_requires_the_godot_editor_even_when_web_output_exists(
    tmp_path: Path,
) -> None:
    # Given: stale pre-exported Web files without the required source toolchain.
    project_root = tmp_path / "project"
    scripts_dir = copy_bootstrap(project_root)
    prepare_build_runtime(project_root)
    elfie_home = tmp_path / "elfie-home"
    elfie_home.mkdir()
    # When: source development checks dependencies from a PATH without Godot.
    result = run_bootstrap(
        scripts_dir,
        project_root,
        elfie_home,
        path="/usr/bin:/bin:/usr/sbin:/sbin",
        godot_bin=str(tmp_path / "missing-godot"),
    )

    # Then: it refuses to enter the source workflow as though the build tool existed.
    assert result.returncode == 1, result.stderr
    assert json.loads(result.stdout)["components"]["godot_toolchain"] == {
        "required": True,
        "state": "missing",
    }


def test_bootstrap_report_marks_absent_ollama_as_optional_missing(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    scripts_dir = copy_bootstrap(project_root)
    prepare_build_runtime(project_root)
    elfie_home = tmp_path / "elfie-home"
    elfie_home.mkdir()

    result = run_bootstrap(scripts_dir, project_root, elfie_home)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["components"]["ollama"] == {
        "required": False,
        "state": "optional_missing",
    }


def test_bootstrap_report_ignores_unrelated_project_private_ollama(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    scripts_dir = copy_bootstrap(project_root)
    prepare_build_runtime(project_root)
    make_executable(project_root / "legacy-private/setup/bin/ollama")
    elfie_home = tmp_path / "elfie-home"
    elfie_home.mkdir()

    result = run_bootstrap(scripts_dir, project_root, elfie_home)

    assert result.returncode == 0, result.stderr
    assert (
        json.loads(result.stdout)["components"]["ollama"]["state"] == "optional_missing"
    )


def test_bootstrap_report_marks_healthy_path_ollama_as_external(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    scripts_dir = copy_bootstrap(project_root)
    prepare_build_runtime(project_root)
    fake_bin = tmp_path / "fake-bin"
    make_executable(fake_bin / "ollama")
    make_executable(
        fake_bin / "godot4",
        "#!/bin/sh\necho '4.7.1.stable'\n",
    )
    elfie_home = tmp_path / "elfie-home"
    elfie_home.mkdir()

    result = run_bootstrap(
        scripts_dir,
        project_root,
        elfie_home,
        path=f"{fake_bin}:/usr/bin:/bin:/usr/sbin:/sbin",
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["components"]["ollama"]["state"] == "external"


def test_bootstrap_pnpm_preparation_uses_repository_pinned_version() -> None:
    bootstrap_source = (PROJECT_ROOT / "scripts/bootstrap.sh").read_text(
        encoding="utf-8"
    )
    runtime_source = (
        PROJECT_ROOT / "scripts/bootstrap_runtime_dependencies.sh"
    ).read_text(encoding="utf-8")

    assert 'PNPM_VERSION="10.12.1"' in runtime_source
    assert "pnpm@${PNPM_VERSION}" in runtime_source
    assert "pnpm@latest" not in bootstrap_source + runtime_source


def test_bootstrap_creates_data_home_through_root_infrastructure() -> None:
    bootstrap_source = (PROJECT_ROOT / "scripts/bootstrap.sh").read_text(
        encoding="utf-8"
    )

    assert "from app.bootstrap.system_wiring.entrypoints import ensure_elfie_home" in (
        bootstrap_source
    )
    assert "ai_runtime.storage.data_home" not in bootstrap_source


def test_bootstrap_accepts_only_dev_and_build_tiers(tmp_path: Path) -> None:
    # Given: a bootstrap checkout that formerly accepted a production tier.
    project_root = tmp_path / "project"
    scripts_dir = copy_bootstrap(project_root)
    prepare_build_runtime(project_root)

    # When: the obsolete tier is requested.
    result = subprocess.run(
        ["bash", str(scripts_dir / "bootstrap.sh"), "report", "--tier=prod"],
        cwd=project_root,
        env={**os.environ, "HOME": str(tmp_path / "home"), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: it is rejected instead of selecting an installed-runtime dependency path.
    assert result.returncode != 0
    assert "dev or build" in result.stderr


def test_bootstrap_pins_the_official_godot_toolchain_for_source_builds() -> None:
    # Given: the source-build bootstrap dependency contract.
    runtime_source = (
        PROJECT_ROOT / "scripts" / "bootstrap_runtime_dependencies.sh"
    ).read_text(encoding="utf-8")

    # When: Godot prerequisites are inspected before a Web runtime export.
    accepts_any_47x = 'GODOT_PROJECT_VERSION="4.7"' in runtime_source
    default_download = 'GODOT_DEFAULT_DOWNLOAD_VERSION="4.7.1"' in runtime_source
    uses_official_download = "https://downloads.godotengine.org/" in runtime_source
    requires_templates = "Web Export Templates" in runtime_source
    refuses_noninteractive_download = (
        "Non-interactive environment cannot confirm Godot installation"
        in runtime_source
    )

    # Then: only an explicit developer confirmation can initiate the fixed toolchain.
    assert accepts_any_47x
    assert default_download
    assert uses_official_download
    assert requires_templates
    assert refuses_noninteractive_download
    assert 'rm -rf -- "$root"' not in runtime_source
    assert "godot_managed_root_is_safe" in runtime_source


def test_bootstrap_reuses_a_matching_managed_godot_toolchain(tmp_path: Path) -> None:
    # Given: a previously installed managed Godot editor in the developer-only root.
    project_root = tmp_path / "project"
    scripts_dir = copy_bootstrap(project_root)
    make_project_python(project_root)
    developer_home = tmp_path / "elfienest-dev"
    managed_godot = developer_home / "toolchains" / "godot" / "4.7" / "Godot"
    make_executable(managed_godot, "#!/bin/bash\necho '4.7.1.stable'\n")

    # When: the bootstrap helper resolves its Godot toolchain a second time.
    result = subprocess.run(
        [
            "bash",
            "-c",
            'PROJECT_ROOT="$1"; source "$2"; ensure_godot_toolchain; printf "%s|%s\\n" "$GODOT_RESOLVED_BIN" "$GODOT_RESOLVED_USER_HOME"',
            "bootstrap-godot",
            str(project_root),
            str(scripts_dir / "bootstrap_runtime_dependencies.sh"),
        ],
        env={
            **os.environ,
            "ELFIE_DEV_HOME": str(developer_home),
            "HOME": str(tmp_path / "home"),
            "PATH": "/usr/bin:/bin",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: it reuses the fixed toolchain and its matching template root.
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        f"{managed_godot}|{developer_home / 'godot-user-home'}"
    )


def test_godot_toolchain_install_recovers_cleanly_after_a_failed_download(
    tmp_path: Path,
) -> None:
    # Given: controlled official-download stand-ins and an empty developer toolchain.
    project_root = tmp_path / "project"
    scripts_dir = copy_bootstrap(project_root)
    make_project_python(project_root)
    fake_bin = tmp_path / "fake-bin"
    make_executable(
        fake_bin / "curl",
        "#!/bin/sh\n"
        'if [ "${FAKE_GODOT_DOWNLOAD_FAIL:-0}" = "1" ]; then exit 22; fi\n'
        'output=""\n'
        'url=""\n'
        'while [ "$#" -gt 0 ]; do\n'
        '  if [ "$1" = "--output" ]; then output="$2"; shift 2; continue; fi\n'
        '  url="$1"; shift\n'
        "done\n"
        'printf "%s\\n" "$url" > "$output"\n',
    )
    make_executable(
        fake_bin / "unzip",
        "#!/bin/sh\n"
        'archive="$2"\n'
        'destination="$4"\n'
        'if grep -q "platform=templates" "$archive"; then\n'
        '  mkdir -p "$destination/templates"\n'
        '  printf template > "$destination/templates/web_release.zip"\n'
        "else\n"
        '  mkdir -p "$destination/Godot.app/Contents/MacOS"\n'
        '  printf "#!/bin/sh\\necho 4.7.1.stable\\n" > "$destination/Godot.app/Contents/MacOS/Godot"\n'
        '  chmod +x "$destination/Godot.app/Contents/MacOS/Godot"\n'
        "fi\n",
    )
    developer_home = tmp_path / "elfienest-dev"
    command = (
        'PROJECT_ROOT="$1"; source "$2"; install_official_godot_toolchain; '
        'printf "%s|%s\\n" "$GODOT_RESOLVED_BIN" "$GODOT_RESOLVED_USER_HOME"'
    )
    environment = {
        **os.environ,
        "ELFIE_DEV_HOME": str(developer_home),
        "HOME": str(tmp_path / "home"),
        "PATH": f"{fake_bin}:/usr/bin:/bin:/usr/sbin:/sbin",
    }

    # When: the first transfer fails, then the user explicitly retries.
    failed = subprocess.run(
        [
            "bash",
            "-c",
            'PROJECT_ROOT="$1"; source "$2"; install_official_godot_toolchain',
            "bootstrap-godot",
            str(project_root),
            str(scripts_dir / "bootstrap_runtime_dependencies.sh"),
        ],
        env={**environment, "FAKE_GODOT_DOWNLOAD_FAIL": "1"},
        capture_output=True,
        text=True,
        check=False,
    )
    # Then: no partial managed directory survives the first failed transfer.
    managed_root = developer_home / "toolchains" / "godot" / "4.7"
    assert failed.returncode == 1
    assert not managed_root.exists()

    # And: an explicit retry installs the editor and matching templates.
    succeeded = subprocess.run(
        [
            "bash",
            "-c",
            command,
            "bootstrap-godot",
            str(project_root),
            str(scripts_dir / "bootstrap_runtime_dependencies.sh"),
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert succeeded.returncode == 0, succeeded.stderr
    assert "Godot.app/Contents/MacOS/Godot" in succeeded.stdout
    assert (
        developer_home
        / "godot-user-home/export_templates/4.7.1.stable/templates/web_release.zip"
    ).is_file()
