from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

from infrastructure.godot.runner import project_version as read_godot_project_version
from test.support.paths import PROJECT_ROOT


def make_executable(path: Path, content: str = "#!/bin/sh\nexit 0\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def make_project_python(project_root: Path) -> None:
    content = """#!/bin/sh
if [ "${1:-}" = "-m" ] && [ "${2:-}" = "infrastructure.godot.runner" ]; then
    command="${3:-}"
    shift 3
    case "$command" in
        version)
            binary=""
            while [ "$#" -gt 0 ]; do
                if [ "$1" = "--binary" ]; then binary="$2"; break; fi
                shift
            done
            raw_version="$("$binary" --version)" || exit $?
            version="$(printf '%s\n' "$raw_version" | awk 'match($0, /[0-9]+\\.[0-9]+/) { print substr($0, RSTART, RLENGTH); exit }')"
            [ -n "$version" ] || exit 1
            printf '%s\n' "$version"
            ;;
        project-version)
            project=""
            while [ "$#" -gt 0 ]; do
                if [ "$1" = "--project" ]; then project="$2"; break; fi
                shift
            done
            version="$(awk -F'"' '/^config\\/features=PackedStringArray/ { print $2; exit }' "$project/project.godot")" || exit $?
            [ -n "$version" ] || exit 1
            printf '%s\n' "$version"
            ;;
        *) exit 1 ;;
    esac
    exit $?
fi
exit 0
"""
    for relative_path in (".venv/bin/python3", ".venv/bin/python"):
        make_executable(project_root / relative_path, content)


def copy_bootstrap(project_root: Path) -> Path:
    scripts_dir = project_root / "scripts"
    scripts_dir.mkdir(parents=True)
    for relative_path in (
        "bootstrap.sh",
        "internal/bootstrap/report.sh",
        "internal/bootstrap/runtime_dependencies.sh",
        "architecture/install_git_hooks.sh",
        "architecture/git-hooks/pre-commit",
    ):
        destination = scripts_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PROJECT_ROOT / "scripts" / relative_path, destination)
    godot_project = project_root / "godot_project"
    godot_project.mkdir(parents=True)
    shutil.copy2(
        PROJECT_ROOT / "godot_project" / "project.godot",
        godot_project / "project.godot",
    )
    return scripts_dir


def required_godot_version(project_root: Path) -> str:
    version = read_godot_project_version(project_root / "godot_project")
    if version is None:
        raise AssertionError("test project must declare a Godot compatibility version")
    return version


def compatible_godot_version_output(project_root: Path, *, patch: int = 99) -> str:
    return f"{required_godot_version(project_root)}.{patch}.stable"


def prepare_build_runtime(project_root: Path, *, godot_web: bool = True) -> None:
    (project_root / ".python-version").write_text("3.9.25\n", encoding="utf-8")
    (project_root / "build/web").mkdir(parents=True)
    (project_root / "build/web/manifest.json").write_text("{}\n", encoding="utf-8")
    if godot_web:
        for suffix in ("html", "js", "wasm", "pck"):
            runtime_file = (
                project_root / "build/components/godot-web" / f"elfienest.{suffix}"
            )
            runtime_file.parent.mkdir(parents=True, exist_ok=True)
            runtime_file.write_text("runtime\n", encoding="utf-8")
    make_project_python(project_root)


def run_bootstrap(
    scripts_dir: Path,
    project_root: Path,
    elfie_home: Path,
    *,
    path: str | None = None,
    godot_bin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    effective_path = (
        path or f"{project_root / '.fake-bin'}:/usr/bin:/bin:/usr/sbin:/sbin"
    )
    environment = {
        **os.environ,
        "ELFIE_HOME": str(elfie_home),
        "HOME": str(elfie_home.parent / "home"),
        "PATH": effective_path,
    }
    # The fixture supplies the Godot executable through PATH. An ambient
    # GODOT_BIN would intentionally override that fixture and make the report
    # depend on the developer or CI host environment.
    environment.pop("GODOT_BIN", None)
    if godot_bin is not None:
        environment["GODOT_BIN"] = godot_bin
    return subprocess.run(
        ["bash", str(scripts_dir / "bootstrap.sh"), "report", "--tier=build"],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
