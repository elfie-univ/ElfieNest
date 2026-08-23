from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from test.scripts.bootstrap_test_support import (
    compatible_godot_version_output,
    copy_bootstrap,
    make_executable,
    make_project_python,
    prepare_build_runtime,
    required_godot_version,
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


def test_bootstrap_report_marks_missing_godot_web_as_required_failure(
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
    subprocess.run(["git", "init", "-q", str(project_root)], check=True)
    (project_root / ".pre-commit-config.yaml").write_text(
        "repos: []\n", encoding="utf-8"
    )
    make_executable(
        project_root / ".fake-bin/uv",
        "#!/bin/sh\n"
        'if [ "$1" = "python" ] && [ "$2" = "install" ]; then exit 0; fi\n'
        'if [ "$1" = "sync" ]; then\n'
        "  mkdir -p .venv/bin\n"
        "  for tool in pre-commit ruff; do\n"
        "    printf '#!/bin/sh\\nexit 0\\n' > .venv/bin/$tool\n"
        "    chmod +x .venv/bin/$tool\n"
        "  done\n"
        "  exit 0\n"
        "fi\n"
        "exit 1\n",
    )
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
    hooks_dir = Path(
        subprocess.check_output(
            [
                "git",
                "-C",
                str(project_root),
                "rev-parse",
                "--path-format=absolute",
                "--git-path",
                "hooks",
            ],
            text=True,
        ).strip()
    )
    assert "ElfieNest managed pre-commit hook" in (hooks_dir / "pre-commit").read_text(
        encoding="utf-8"
    )
    assert not (hooks_dir / "pre-push").exists()
    assert "Electron authority host is ready" in result.stdout


def test_bootstrap_hooks_action_only_installs_the_repository_hook(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    scripts_dir = copy_bootstrap(project_root)
    prepare_build_runtime(project_root)
    subprocess.run(["git", "init", "-q", str(project_root)], check=True)
    (project_root / ".pre-commit-config.yaml").write_text(
        "repos: []\n", encoding="utf-8"
    )
    make_executable(
        project_root / ".venv/bin/pre-commit",
        "#!/bin/sh\nexit 0\n",
    )

    result = subprocess.run(
        ["bash", str(scripts_dir / "bootstrap.sh"), "hooks"],
        cwd=project_root,
        env={
            **os.environ,
            "HOME": str(tmp_path / "home"),
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "ElfieNest fast pre-commit hook is ready" in result.stdout
    assert "dependency check" not in result.stdout


def test_bootstrap_dev_check_detects_and_ensure_repairs_a_missing_hook(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    scripts_dir = copy_bootstrap(project_root)
    prepare_build_runtime(project_root)
    subprocess.run(["git", "init", "-q", str(project_root)], check=True)
    (project_root / ".pre-commit-config.yaml").write_text(
        "repos: []\n", encoding="utf-8"
    )
    make_executable(project_root / ".venv/bin/pre-commit")
    make_executable(project_root / ".venv/bin/ruff")
    make_executable(
        project_root / ".fake-bin/node",
        "#!/bin/sh\n"
        'if [ "${1:-}" = "--version" ]; then printf "v20.12.0\\n"; fi\n'
        "exit 0\n",
    )
    make_executable(project_root / "app/interfaces/desktop/node_modules/.bin/electron")
    for relative_path in (
        "build/components/desktop-interface/main.js",
        "app/bootstrap/desktop_host/host_main.mjs",
        "infrastructure/godot/lifecycle/electron/authority_main.mjs",
    ):
        destination = project_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("ready\n", encoding="utf-8")
    environment = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "PATH": f"{project_root / '.fake-bin'}:/usr/bin:/bin:/usr/sbin:/sbin",
    }

    missing = subprocess.run(
        ["bash", str(scripts_dir / "bootstrap.sh"), "check", "--tier=dev"],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert missing.returncode == 1
    assert "managed pre-commit hook is missing" in missing.stderr

    repaired = subprocess.run(
        ["bash", str(scripts_dir / "bootstrap.sh"), "ensure", "--tier=dev"],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    healthy = subprocess.run(
        ["bash", str(scripts_dir / "bootstrap.sh"), "check", "--tier=dev"],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert repaired.returncode == 0, repaired.stderr
    assert healthy.returncode == 0, healthy.stderr
    assert "managed pre-commit hook is ready" in healthy.stdout


def test_bootstrap_report_treats_the_editor_as_optional_when_web_output_exists(
    tmp_path: Path,
) -> None:
    # Given: an exported Web Runtime without a source editor on the machine.
    project_root = tmp_path / "project"
    scripts_dir = copy_bootstrap(project_root)
    prepare_build_runtime(project_root)
    elfie_home = tmp_path / "elfie-home"
    elfie_home.mkdir()
    # When: dependency status is reported from a PATH without Godot.
    result = run_bootstrap(
        scripts_dir,
        project_root,
        elfie_home,
        path="/usr/bin:/bin:/usr/sbin:/sbin",
        godot_bin=str(tmp_path / "missing-godot"),
    )

    # Then: the exported Runtime remains the hard dependency and the editor is
    # only an observable source-build capability.
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["components"]["godot_toolchain"] == {
        "required": False,
        "state": "missing",
    }


def test_bootstrap_check_does_not_require_godot_when_web_output_exists(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    scripts_dir = copy_bootstrap(project_root)
    prepare_build_runtime(project_root)

    result = subprocess.run(
        ["bash", str(scripts_dir / "bootstrap.sh"), "check", "--tier=build"],
        cwd=project_root,
        env={
            **os.environ,
            "HOME": str(tmp_path / "home"),
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Godot source build toolchain" not in result.stdout


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
        f"#!/bin/sh\necho '{compatible_godot_version_output(project_root)}'\n",
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
        PROJECT_ROOT / "scripts/internal/bootstrap/runtime_dependencies.sh"
    ).read_text(encoding="utf-8")

    assert 'PNPM_VERSION="10.12.1"' in runtime_source
    assert "pnpm@${PNPM_VERSION}" in runtime_source
    assert "pnpm@latest" not in bootstrap_source + runtime_source


def test_bootstrap_dev_tier_syncs_locked_development_dependencies() -> None:
    bootstrap_source = (PROJECT_ROOT / "scripts/bootstrap.sh").read_text(
        encoding="utf-8"
    )

    assert 'sync_args="$sync_args --extra dev"' in bootstrap_source
    assert 'sync_args="$sync_args --no-dev --extra release"' in bootstrap_source
    assert 'UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/elfienest-uv-cache}"' in bootstrap_source


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


def test_bootstrap_derives_the_official_godot_toolchain_for_source_builds() -> None:
    # Given: the source-build bootstrap dependency contract.
    runtime_source = (
        PROJECT_ROOT / "scripts/internal/bootstrap/runtime_dependencies.sh"
    ).read_text(encoding="utf-8")

    # When: Godot prerequisites are inspected before a Web runtime export.
    reads_project_version = "project-version" in runtime_source
    uses_official_download = "https://downloads.godotengine.org/" in runtime_source
    requires_templates = "Web Export Templates" in runtime_source
    refuses_noninteractive_download = (
        "Non-interactive environment cannot confirm Godot installation"
        in runtime_source
    )

    # Then: project.godot is the only maintained version input and only an
    # explicit developer confirmation can initiate the derived toolchain install.
    assert reads_project_version
    assert 'GODOT_PROJECT_VERSION=""' in runtime_source
    assert 'GODOT_PROJECT_VERSION="4.' not in runtime_source
    assert "GODOT_DEFAULT_DOWNLOAD_VERSION" not in runtime_source
    assert uses_official_download
    assert requires_templates
    assert refuses_noninteractive_download
    assert "[y/N/path]" in runtime_source
    assert "${choice:-Y}" not in runtime_source
    assert 'rm -rf -- "$root"' not in runtime_source
    assert "godot_managed_root_is_safe" in runtime_source


def test_bootstrap_reuses_a_matching_managed_godot_toolchain(tmp_path: Path) -> None:
    # Given: a previously installed managed Godot editor in the developer-only root.
    project_root = tmp_path / "project"
    scripts_dir = copy_bootstrap(project_root)
    make_project_python(project_root)
    developer_home = tmp_path / "elfienest-dev"
    required_version = required_godot_version(project_root)
    version_log = tmp_path / "godot-version.log"
    managed_godot = developer_home / "toolchains" / "godot" / required_version / "Godot"
    managed_root = managed_godot.parent
    managed_editor_data = managed_root / "editor_data"
    make_executable(
        managed_godot,
        "#!/bin/bash\n"
        'printf \'%s\\n\' "$*" >> "$GODOT_VERSION_LOG"\n'
        f"echo '{compatible_godot_version_output(project_root)}'\n",
    )
    (managed_root / "_sc_").touch()
    managed_template = (
        managed_editor_data
        / "export_templates"
        / compatible_godot_version_output(project_root)
        / "web_release.zip"
    )
    managed_template.parent.mkdir(parents=True)
    managed_template.write_bytes(b"template")

    # When: the bootstrap helper resolves its Godot toolchain a second time.
    result = subprocess.run(
        [
            "bash",
            "-c",
            'PROJECT_ROOT="$1"; source "$2"; ensure_godot_toolchain; printf "%s|%s\\n" "$GODOT_RESOLVED_BIN" "$GODOT_RESOLVED_EDITOR_DATA"',
            "bootstrap-godot",
            str(project_root),
            str(scripts_dir / "internal/bootstrap/runtime_dependencies.sh"),
        ],
        env={
            **os.environ,
            "ELFIE_DEV_HOME": str(developer_home),
            "GODOT_VERSION_LOG": str(version_log),
            "HOME": str(tmp_path / "home"),
            "PATH": "/usr/bin:/bin",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: it reuses the derived toolchain and its matching template root.
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"{managed_godot}|{managed_editor_data}"
    assert version_log.read_text(encoding="utf-8").splitlines() == ["--version"]


def test_bootstrap_reuses_a_matching_system_godot_binary(tmp_path: Path) -> None:
    # Given: a matching patch release from the declared compatibility line on PATH.
    project_root = tmp_path / "project"
    scripts_dir = copy_bootstrap(project_root)
    make_project_python(project_root)
    fake_bin = tmp_path / "fake-bin"
    system_godot = fake_bin / "godot4"
    make_executable(
        system_godot,
        f"#!/bin/sh\necho '{compatible_godot_version_output(project_root)}'\n",
    )

    # When: the bootstrap helper resolves the source-build toolchain.
    result = subprocess.run(
        [
            "bash",
            "-c",
            'PROJECT_ROOT="$1"; source "$2"; ensure_godot_toolchain; printf "%s|%s\\n" "$GODOT_RESOLVED_BIN" "$GODOT_RESOLVED_EDITOR_DATA"',
            "bootstrap-godot",
            str(project_root),
            str(scripts_dir / "internal/bootstrap/runtime_dependencies.sh"),
        ],
        env={
            **os.environ,
            "GODOT_BIN": "",
            "HOME": str(tmp_path / "home"),
            "PATH": f"{fake_bin}:/usr/bin:/bin",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: the existing binary is reused and the installer is never entered.
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"{system_godot}|"
    assert "Install from official Godot source now?" not in result.stderr


def test_bootstrap_rejects_a_different_godot_compatibility_line(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    scripts_dir = copy_bootstrap(project_root)
    make_project_python(project_root)
    major, minor = required_godot_version(project_root).split(".", maxsplit=1)
    incompatible_output = f"{major}.{int(minor) + 1}.stable"
    fake_bin = tmp_path / "fake-bin"
    make_executable(fake_bin / "godot4", f"#!/bin/sh\necho '{incompatible_output}'\n")

    result = subprocess.run(
        [
            "bash",
            "-c",
            'PROJECT_ROOT="$1"; source "$2"; ensure_godot_toolchain',
            "bootstrap-godot",
            str(project_root),
            str(scripts_dir / "internal/bootstrap/runtime_dependencies.sh"),
        ],
        env={
            **os.environ,
            "GODOT_BIN": str(fake_bin / "godot4"),
            "HOME": str(tmp_path / "home"),
            "PATH": f"{fake_bin}:/usr/bin:/bin",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Non-interactive environment cannot confirm Godot installation" in (
        result.stderr
    )


def test_godot_toolchain_install_recovers_cleanly_after_a_failed_download(
    tmp_path: Path,
) -> None:
    # Given: controlled official-download stand-ins and an empty developer toolchain.
    project_root = tmp_path / "project"
    scripts_dir = copy_bootstrap(project_root)
    make_project_python(project_root)
    required_version = required_godot_version(project_root)
    downloaded_version = compatible_godot_version_output(project_root)
    fake_bin = tmp_path / "fake-bin"
    make_executable(
        fake_bin / "curl",
        "#!/bin/sh\n"
        'printf "%s\\n" "$*" >> "$FAKE_GODOT_CURL_ARGS_LOG"\n'
        'if [ "${FAKE_GODOT_DOWNLOAD_FAIL:-0}" = "1" ]; then exit 22; fi\n'
        'output=""\n'
        'url=""\n'
        'while [ "$#" -gt 0 ]; do\n'
        '  if [ "$1" = "--output" ]; then output="$2"; shift 2; continue; fi\n'
        '  url="$1"; shift\n'
        "done\n"
        'printf "%s\\n" "$url" >> "$FAKE_GODOT_URL_LOG"\n'
        'printf "%s\\n" "$url" > "$output"\n',
    )
    make_executable(
        fake_bin / "unzip",
        "#!/bin/sh\n"
        'archive="$2"\n'
        'destination="$4"\n'
        'if grep -q "platform=templates" "$archive"; then\n'
        '  mkdir -p "$destination/templates"\n'
        f'  printf "%s\\n" "{downloaded_version}" > "$destination/templates/version.txt"\n'
        '  printf template > "$destination/templates/web_release.zip"\n'
        "else\n"
        '  mkdir -p "$destination/Godot.app/Contents/MacOS"\n'
        f'  printf "#!/bin/sh\\necho {downloaded_version}\\n" > "$destination/Godot.app/Contents/MacOS/Godot"\n'
        '  chmod +x "$destination/Godot.app/Contents/MacOS/Godot"\n'
        "fi\n",
    )
    developer_home = tmp_path / "elfienest-dev"
    url_log = tmp_path / "godot-download-urls.log"
    curl_args_log = tmp_path / "godot-curl-args.log"
    command = (
        'PROJECT_ROOT="$1"; source "$2"; install_official_godot_toolchain; '
        'printf "%s|%s\\n" "$GODOT_RESOLVED_BIN" "$GODOT_RESOLVED_EDITOR_DATA"'
    )
    environment = {
        **os.environ,
        "ELFIE_DEV_HOME": str(developer_home),
        "FAKE_GODOT_CURL_ARGS_LOG": str(curl_args_log),
        "FAKE_GODOT_URL_LOG": str(url_log),
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
            str(scripts_dir / "internal/bootstrap/runtime_dependencies.sh"),
        ],
        env={**environment, "FAKE_GODOT_DOWNLOAD_FAIL": "1"},
        capture_output=True,
        text=True,
        check=False,
    )
    # Then: no partial managed directory survives the first failed transfer.
    managed_root = developer_home / "toolchains" / "godot" / required_version
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
            str(scripts_dir / "internal/bootstrap/runtime_dependencies.sh"),
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert succeeded.returncode == 0, succeeded.stderr
    assert "Godot.app/Contents/MacOS/Godot" in succeeded.stdout
    managed_root = developer_home / "toolchains" / "godot" / required_version
    assert (managed_root / "_sc_").is_file()
    assert (
        managed_root
        / f"editor_data/export_templates/{downloaded_version}/web_release.zip"
    ).is_file()
    download_urls = url_log.read_text(encoding="utf-8").splitlines()
    assert len(download_urls) == 2
    assert all(url.endswith(f"version={required_version}") for url in download_urls)
    curl_invocations = curl_args_log.read_text(encoding="utf-8").splitlines()
    assert len(curl_invocations) == 3
    for invocation in curl_invocations:
        assert "--http1.1" in invocation
        assert "--retry 5" in invocation
        assert "--retry-all-errors" in invocation
        assert "--retry-delay 2" in invocation
        assert "--continue-at -" in invocation


def test_godot_toolchain_paths_and_downloads_follow_project_godot(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    scripts_dir = copy_bootstrap(project_root)
    make_project_python(project_root)
    declared_version = "9.8"
    (project_root / "godot_project/project.godot").write_text(
        '[application]\nconfig/features=PackedStringArray("9.8", "GL Compatibility")\n',
        encoding="utf-8",
    )
    developer_home = tmp_path / "elfienest-dev"

    result = subprocess.run(
        [
            "bash",
            "-c",
            'PROJECT_ROOT="$1"; source "$2"; load_godot_project_version; '
            'printf "%s|%s\\n" "$(godot_toolchain_root)" '
            '"$(godot_download_url templates export_templates.tpz)"',
            "bootstrap-godot",
            str(project_root),
            str(scripts_dir / "internal/bootstrap/runtime_dependencies.sh"),
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

    assert result.returncode == 0, result.stderr
    managed_root, download_url = result.stdout.strip().split("|", maxsplit=1)
    assert managed_root == str(
        developer_home / "toolchains" / "godot" / declared_version
    )
    assert download_url.endswith(f"version={declared_version}")
