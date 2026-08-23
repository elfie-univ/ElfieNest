from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import yaml

from test.support.paths import PROJECT_ROOT


def _make_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_precommit_is_staged_only_and_keeps_broad_quality_manual() -> None:
    config = yaml.safe_load(
        (PROJECT_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    )
    local_repository = next(
        repository for repository in config["repos"] if repository["repo"] == "local"
    )
    hooks = {hook["id"]: hook for hook in local_repository["hooks"]}

    assert config["default_stages"] == ["pre-commit"]
    assert set(hooks) == {
        "quality-baseline",
        "staged-diff-check",
        "staged-python-ruff-check",
        "staged-python-ruff-format",
    }
    assert hooks["staged-diff-check"]["entry"] == "git diff --cached --check --"
    assert hooks["staged-python-ruff-check"]["entry"] == ".venv/bin/ruff check"
    assert (
        hooks["staged-python-ruff-format"]["entry"] == ".venv/bin/ruff format --check"
    )
    assert hooks["quality-baseline"]["stages"] == ["manual"]

    commit_entries = "\n".join(
        hook["entry"]
        for hook in hooks.values()
        if hook.get("stages", config["default_stages"]) == ["pre-commit"]
    )
    for forbidden in ("pytest", "mypy", "pnpm", "godot", "git fetch", "stage push"):
        assert forbidden not in commit_entries.lower()


def test_hook_installer_backs_up_legacy_hook_and_is_idempotent(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    (project / "scripts/quality/hooks").mkdir(parents=True)
    shutil.copy2(
        PROJECT_ROOT / "scripts/quality/hooks/install.sh",
        project / "scripts/quality/hooks/install.sh",
    )
    hook_template = project / "scripts/quality/hooks/pre-commit"
    shutil.copy2(
        PROJECT_ROOT / "scripts/quality/hooks/pre-commit",
        hook_template,
    )
    (project / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")

    log_path = project / "pre-commit-calls.log"
    fake_pre_commit = project / ".venv/bin/pre-commit"
    _make_executable(
        fake_pre_commit,
        """#!/bin/bash
set -eu
printf '%s\\n' "$*" >> "$ELFIENEST_HOOK_TEST_LOG"
""",
    )

    hooks_dir = Path(
        subprocess.check_output(
            [
                "git",
                "-C",
                str(project),
                "rev-parse",
                "--path-format=absolute",
                "--git-path",
                "hooks",
            ],
            text=True,
        ).strip()
    )
    legacy_hook = hooks_dir / "pre-commit"
    _make_executable(legacy_hook, "#!/bin/bash\necho legacy\n")
    environment = {**os.environ, "ELFIENEST_HOOK_TEST_LOG": str(log_path)}

    for _ in range(2):
        result = subprocess.run(
            ["bash", str(project / "scripts/quality/hooks/install.sh")],
            cwd=project,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    assert (hooks_dir / "pre-commit.elfienest-legacy-backup").read_text(
        encoding="utf-8"
    ) == "#!/bin/bash\necho legacy\n"
    calls = log_path.read_text(encoding="utf-8").splitlines()
    assert calls == [
        "validate-config .pre-commit-config.yaml",
        "install-hooks",
        "validate-config .pre-commit-config.yaml",
        "install-hooks",
    ]
    assert not (hooks_dir / "pre-push").exists()


def test_managed_hook_resolves_the_current_worktree_environment() -> None:
    source = (PROJECT_ROOT / "scripts/quality/hooks/pre-commit").read_text(
        encoding="utf-8"
    )

    assert 'PROJECT_ROOT="$(git rev-parse --show-toplevel)"' in source
    assert 'PRE_COMMIT_PYTHON="$PROJECT_ROOT/.venv/bin/python"' in source
    assert str(PROJECT_ROOT) not in source
