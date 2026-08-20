from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from infrastructure.godot import runner
from infrastructure.godot.runner import godot_version, run_headless

_TEST_GODOT_VERSION = "9.8"
_TEST_GODOT_OUTPUT = f"{_TEST_GODOT_VERSION}.7.stable"
_FAKE_GODOT = """#!/bin/sh
if [ \"${1:-}\" = \"--version\" ]; then
    printf '%s\\n' '__TEST_GODOT_OUTPUT__'
    exit 0
fi
if [ -n \"${FAKE_GODOT_COUNT:-}\" ]; then
    printf '%s\\n' invoked >> \"$FAKE_GODOT_COUNT\"
fi
if [ \"${FAKE_GODOT_MODE:-}\" = crash ]; then
    kill -ABRT $$
fi
if [ \"${FAKE_GODOT_MODE:-}\" = timeout ]; then
    exec sleep 2
fi
printf 'Godot Engine v__TEST_GODOT_OUTPUT__\\n'
printf 'fake godot arguments: %s\\n' \"$*\"
exit 0
""".replace("__TEST_GODOT_OUTPUT__", _TEST_GODOT_OUTPUT)


def _fake_godot(tmp_path: Path) -> Path:
    binary = tmp_path / "fake-godot"
    binary.write_text(_FAKE_GODOT, encoding="utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    return binary


def _invocation_records(stderr: str) -> list[dict[str, object]]:
    prefix = "GODOT_INVOCATION "
    return [
        json.loads(line[len(prefix) :])
        for line in stderr.splitlines()
        if line.startswith(prefix)
    ]


@pytest.fixture(autouse=True)
def _allow_fake_godot_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep fake-process tests independent from the enclosing test sandbox."""

    monkeypatch.setattr(runner, "_ensure_host_execution_available", lambda: None)


def test_version_and_headless_validation_use_one_observable_process_boundary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    binary = _fake_godot(tmp_path)
    project = tmp_path / "godot_project"
    project.mkdir()

    assert godot_version(binary) == _TEST_GODOT_VERSION
    result = run_headless(
        binary,
        project,
        ("--script", "res://check.gd", "--token", "do-not-log"),
        godot_version=_TEST_GODOT_VERSION,
        purpose="test-validation",
    )

    assert result.exit_code == 0
    assert result.crashed is False
    assert result.timed_out is False
    assert result.godot_version == _TEST_GODOT_VERSION
    assert result.command[:4] == (
        str(binary),
        "--headless",
        "--path",
        str(project.resolve()),
    )
    records = _invocation_records(capsys.readouterr().err)
    assert records[-1]["status"] == "exited"
    assert records[-1]["godot_version"] == _TEST_GODOT_VERSION
    assert records[-1]["parent_pid"] == os.getpid()
    assert "do-not-log" not in json.dumps(records[-1])
    assert records[-1]["command"][-2:] == ["<redacted>", "<redacted>"]


def test_crash_is_failed_once_and_is_not_retried(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    binary = _fake_godot(tmp_path)
    project = tmp_path / "godot_project"
    project.mkdir()
    count_file = tmp_path / "invocations.txt"
    environment = dict(os.environ)
    environment.update(
        {"FAKE_GODOT_MODE": "crash", "FAKE_GODOT_COUNT": str(count_file)}
    )

    result = run_headless(
        binary,
        project,
        ("--script", "res://check.gd"),
        timeout_seconds=5,
        purpose="test-crash",
        env=environment,
    )

    assert result.exit_code == 1
    assert result.crashed is True
    assert result.timed_out is False
    assert count_file.read_text(encoding="utf-8").splitlines() == ["invoked"]
    stderr = capsys.readouterr().err
    assert "GODOT_CRASH: one invocation failed; no retry was attempted." in stderr
    assert _invocation_records(stderr)[-1]["status"] == "crashed"


def test_crash_exit_codes_skip_signals_unavailable_on_the_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: Windows does not expose the POSIX-only SIGBUS constant.
    monkeypatch.delattr(runner.signal, "SIGBUS", raising=False)

    # When: the runner derives the set of crash exit codes for this host.
    crash_exit_codes = runner._available_crash_exit_codes()

    # Then: supported crash signals remain classified without importing SIGBUS.
    assert 128 + int(runner.signal.SIGABRT) in crash_exit_codes


def test_unavailable_host_does_not_start_godot(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = _fake_godot(tmp_path)
    project = tmp_path / "godot_project"
    project.mkdir()
    count_file = tmp_path / "invocations.txt"
    environment = dict(os.environ)
    environment["FAKE_GODOT_COUNT"] = str(count_file)
    monkeypatch.setattr(
        runner,
        "_ensure_host_execution_available",
        lambda: "ps: Operation not permitted",
    )

    result = run_headless(
        binary,
        project,
        ("--script", "res://check.gd"),
        purpose="test-host-blocked",
        env=environment,
    )

    assert result.exit_code == 126
    assert result.host_blocked is True
    assert not count_file.exists()
    stderr = capsys.readouterr().err
    assert "GODOT_HOST_UNAVAILABLE" in stderr
    assert _invocation_records(stderr)[-1]["status"] == "blocked"
    assert _invocation_records(stderr)[-1]["started"] is False


def test_timeout_is_failed_without_a_second_process(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    binary = _fake_godot(tmp_path)
    project = tmp_path / "godot_project"
    project.mkdir()
    count_file = tmp_path / "invocations.txt"
    environment = dict(os.environ)
    environment.update(
        {"FAKE_GODOT_MODE": "timeout", "FAKE_GODOT_COUNT": str(count_file)}
    )

    result = run_headless(
        binary,
        project,
        ("--script", "res://check.gd"),
        timeout_seconds=0.5,
        purpose="test-timeout",
        env=environment,
    )

    assert result.exit_code == 124
    assert result.crashed is False
    assert result.timed_out is True
    assert count_file.read_text(encoding="utf-8").splitlines() == ["invoked"]
    assert _invocation_records(capsys.readouterr().err)[-1]["status"] == "timed_out"


def test_headless_runner_rejects_editor_mode(tmp_path: Path) -> None:
    binary = _fake_godot(tmp_path)
    project = tmp_path / "godot_project"
    project.mkdir()

    with pytest.raises(ValueError, match="only permits headless"):
        run_headless(binary, project, ("--editor",))


def test_version_cli_uses_the_shared_runner(tmp_path: Path, capsys) -> None:
    binary = _fake_godot(tmp_path)

    assert runner.main(["version", "--binary", str(binary)]) == 0
    assert capsys.readouterr().out.strip() == _TEST_GODOT_VERSION


def test_project_version_cli_reads_project_godot(tmp_path: Path, capsys) -> None:
    project = tmp_path / "godot_project"
    project.mkdir()
    (project / "project.godot").write_text(
        '[application]\nconfig/features=PackedStringArray("9.8", "GL Compatibility")\n',
        encoding="utf-8",
    )

    assert runner.main(["project-version", "--project", str(project)]) == 0
    assert capsys.readouterr().out.strip() == _TEST_GODOT_VERSION
