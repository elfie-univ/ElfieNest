import os
import subprocess
import sys
from pathlib import Path

from scripts.serve import (
    prepare_frontend_web_runtime,
    prepare_godot_web_runtime,
    service_host,
)
from test.support.paths import PROJECT_ROOT


def test_service_host_binds_loopback_unless_lan_is_explicit() -> None:
    # Given: the developer CLI defaults and its explicit LAN option.
    # When: each mode resolves a bind host.
    # Then: only LAN chooses all IPv4 interfaces.
    assert service_host(lan=False) == "127.0.0.1"
    assert service_host(lan=True) == "0.0.0.0"


def test_prepare_godot_web_runtime_uses_ensure_for_development() -> None:
    # Given: a development launch and a successful exporter process.
    commands: list[list[str]] = []

    class Result:
        returncode = 0

    def run(command: list[str]) -> Result:
        commands.append(command)
        return Result()

    # When: preparation runs.
    # Then: it requests an incremental ensure build.
    assert prepare_godot_web_runtime("development", run) is True
    assert commands[0][-1] == "--ensure"


def test_prepare_frontend_web_runtime_only_builds_development(
    monkeypatch,
) -> None:
    modes: list[str] = []
    monkeypatch.setattr(
        "scripts.serve.ensure_frontend_build",
        lambda *, runtime_mode: modes.append(runtime_mode),
    )

    prepare_frontend_web_runtime("development")
    prepare_frontend_web_runtime("release")

    assert modes == ["development"]


def test_prepare_godot_web_runtime_checks_only_in_release() -> None:
    # Given: a release launch with a missing staged bundle.
    commands: list[list[str]] = []

    class Result:
        returncode = 1

    def run(command: list[str]) -> Result:
        commands.append(command)
        return Result()

    # When: preparation runs.
    # Then: it only validates the staged runtime and fails closed.
    assert prepare_godot_web_runtime("release", run) is False
    assert commands[0][-1] == "--check"


def test_frozen_release_core_does_not_try_to_reexecute_the_godot_build_script() -> None:
    # Given: an installed Core whose staged Godot resources have already passed package validation.
    class Result:
        returncode = 1

    def run(_command: list[str]) -> Result:
        raise AssertionError("the frozen Core must not run build_godot_web.py")

    # When: the installed release runtime starts.
    # Then: it trusts the already-validated staged bundle instead of treating itself as Python.
    assert prepare_godot_web_runtime("release", run, is_frozen=True) is True


def test_serve_parser_rejects_missing_data_home_value() -> None:
    """Given 缺少值的参数，When 运行 serve，Then argparse 在启动前拒绝。"""
    result = subprocess.run(
        [sys.executable, "scripts/serve.py", "--data-home"],
        cwd=PROJECT_ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "--data-home" in result.stderr


def test_serve_parser_rejects_file_data_home_target(tmp_path: Path) -> None:
    """Given 文件目标，When 运行 serve，Then 在创建运行状态前拒绝。"""
    target = tmp_path / "not-a-directory"
    target.write_text("x", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "scripts/serve.py", "--data-home", str(target)],
        cwd=PROJECT_ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "不是目录" in result.stderr
