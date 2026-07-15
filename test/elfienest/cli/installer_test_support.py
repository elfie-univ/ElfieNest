from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def copy_installer_project(destination: Path) -> None:
    destination.mkdir(parents=True)
    relative_paths = (
        Path("install.sh"),
        Path("elfienest.sh"),
        Path(".python-version"),
        Path("uv.lock"),
        Path("scripts/elfienest_install_helpers.sh"),
    )
    for relative_path in relative_paths:
        source = PROJECT_ROOT / relative_path
        if not source.exists():
            continue
        target = destination / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def write_fake_uv(fake_bin: Path) -> Path:
    uv_path = fake_bin / "uv"
    write_executable(
        uv_path,
        """#!/bin/bash
set -eu
printf '%s\n' "$*" >> "$FAKE_UV_LOG"
if [ "${1:-}" = "--version" ]; then
    echo "uv 0.9.26"
    exit 0
fi
if [ "${1:-}" = "python" ] && [ "${2:-}" = "install" ]; then
    [ "${FAKE_UV_FAIL_PYTHON_INSTALL:-0}" != "1" ] || exit 41
    exit 0
fi
if [ "${1:-}" = "sync" ]; then
    [ "${FAKE_UV_FAIL_SYNC:-0}" != "1" ] || exit 42
    venv_dir="${UV_PROJECT_ENVIRONMENT:-.venv}"
    mkdir -p "$venv_dir/bin"
    cat > "$venv_dir/bin/python3" <<'PYTHON'
#!/bin/bash
exit 0
PYTHON
    chmod +x "$venv_dir/bin/python3"
    exit 0
fi
exit 0
""",
    )
    return uv_path


def installer_environment(
    home: Path,
    fake_bin: Path,
    uv_log: Path,
    *,
    path: str | None = None,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "FAKE_UV_LOG": str(uv_log),
            "HOME": str(home),
            "PATH": path
            or f"{fake_bin}:{home / '.local' / 'bin'}:{home / 'bin'}:/usr/bin:/bin",
            "SHELL": "/bin/bash",
        }
    )
    if extra is not None:
        environment.update(extra)
    return environment


def run_installer(
    project_root: Path,
    environment: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(project_root / "install.sh")],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
