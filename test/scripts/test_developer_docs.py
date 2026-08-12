"""Documentation preview entrypoint contracts."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from test.app.interfaces.cli.entrypoint_test_support import write_executable
from test.support.paths import PROJECT_ROOT


def test_docs_command_starts_vitepress_without_python_environment(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "ElfieNest"
    project_root.mkdir()
    shutil.copy2(PROJECT_ROOT / "developer.sh", project_root / "developer.sh")
    (project_root / "docs" / "node_modules" / ".bin").mkdir(parents=True)
    write_executable(project_root / "docs" / "node_modules" / ".bin" / "vitepress", "")

    command_log = tmp_path / "pnpm-command.log"
    fake_bin = tmp_path / "bin"
    write_executable(
        fake_bin / "pnpm",
        '#!/bin/bash\nprintf \'%s\\n\' "$*" > "$DOCS_COMMAND_LOG"\n',
    )
    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
    environment["DOCS_COMMAND_LOG"] = str(command_log)

    result = subprocess.run(
        [str(project_root / "developer.sh"), "docs", "--port", "4317"],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert command_log.read_text(encoding="utf-8").strip() == (
        "--dir docs dev --host 127.0.0.1 --open --port 4317"
    )
