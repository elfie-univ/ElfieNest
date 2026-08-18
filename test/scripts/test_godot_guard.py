from __future__ import annotations

import importlib.util
import shlex
import sys
from pathlib import Path
from types import SimpleNamespace

GUARD_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / ".agents"
    / "skills"
    / "godot-project-operator"
    / "scripts"
    / "godot_guard.py"
)
SPEC = importlib.util.spec_from_file_location("godot_guard_test_subject", GUARD_SCRIPT)
assert SPEC is not None and SPEC.loader is not None
godot_guard = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = godot_guard
SPEC.loader.exec_module(godot_guard)


def _process(pid: int, project: Path | None):
    path_argument = "" if project is None else f" --path {shlex.quote(str(project))}"
    return godot_guard.GodotProcess(
        pid=pid,
        rss_kib=None,
        command=f"/Applications/Godot.app/Contents/MacOS/Godot{path_argument}",
    )


def test_process_project_path_is_exact_and_normalized(tmp_path: Path) -> None:
    project = (tmp_path / "worktree" / "godot_project").resolve()
    command = (
        "/Applications/Godot.app/Contents/MacOS/Godot --path "
        f"{shlex.quote(str(project))}"
    )

    assert godot_guard.process_project_path(command) == project
    assert godot_guard.process_project_path("Godot --editor") is None


def test_only_same_project_or_unknown_processes_block(tmp_path: Path) -> None:
    target = tmp_path / "target" / "godot_project"
    other = tmp_path / "other" / "godot_project"
    same_project = _process(10, target)
    other_project = _process(11, other)
    unknown_project = _process(12, None)

    assert godot_guard.blocking_processes([other_project], target) == []
    assert godot_guard.blocking_processes([same_project], target) == [same_project]
    assert godot_guard.blocking_processes([unknown_project], target) == [
        unknown_project
    ]


def test_launch_allows_a_known_different_project(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    target = tmp_path / "target" / "godot_project"
    other = _process(11, tmp_path / "other" / "godot_project")
    calls = []

    def fake_popen(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(pid=1234)

    monkeypatch.setattr(godot_guard.subprocess, "Popen", fake_popen)

    assert godot_guard.launch(Path("/godot"), target, True, [other]) == 0
    assert calls[0][0] == ["/godot", "--editor", "--path", str(target.resolve())]
    assert "Do not launch another instance for this project" in capsys.readouterr().out


def test_validate_allows_a_known_different_project(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "target" / "godot_project"
    other = _process(11, tmp_path / "other" / "godot_project")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(godot_guard.subprocess, "run", fake_run)

    assert godot_guard.validate(Path("/godot"), target, "check.gd", [other]) == 0
    assert calls[0][0] == [
        "/godot",
        "--headless",
        "--path",
        str(target.resolve()),
        "--script",
        "check.gd",
    ]
