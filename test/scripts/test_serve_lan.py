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
    calls: list[tuple[str, bool]] = []

    class Lifecycle:
        def prepare_godot_web(self, mode: str, *, is_frozen: bool) -> bool:
            calls.append((mode, is_frozen))
            return True

    assert prepare_godot_web_runtime(Lifecycle(), "development") is True
    assert calls == [("development", False)]


def test_prepare_frontend_web_runtime_only_builds_development() -> None:
    modes: list[str] = []

    class Lifecycle:
        def prepare_frontend(self, runtime_mode: str) -> None:
            modes.append(runtime_mode)

    prepare_frontend_web_runtime(Lifecycle(), "development")
    prepare_frontend_web_runtime(Lifecycle(), "release")

    assert modes == ["development"]


def test_prepare_godot_web_runtime_checks_only_in_release() -> None:
    calls: list[tuple[str, bool]] = []

    class Lifecycle:
        def prepare_godot_web(self, mode: str, *, is_frozen: bool) -> bool:
            calls.append((mode, is_frozen))
            return False

    assert prepare_godot_web_runtime(Lifecycle(), "release") is False
    assert calls == [("release", False)]


def test_frozen_release_core_does_not_try_to_reexecute_the_godot_build_script() -> None:
    class Lifecycle:
        def prepare_godot_web(self, mode: str, *, is_frozen: bool) -> bool:
            assert mode == "release"
            assert is_frozen is True
            return True

    assert prepare_godot_web_runtime(Lifecycle(), "release", is_frozen=True) is True


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
