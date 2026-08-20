import os
import subprocess
import sys
from pathlib import Path

from scripts import serve
from scripts.serve import (
    _delegate_direct_source_invocation,
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


def test_console_output_is_utf8_safe_for_frozen_windows_core(monkeypatch) -> None:
    # Given: a frozen Windows Core whose console stream defaults to cp1252.
    class Stream:
        def __init__(self) -> None:
            self.calls: list[dict[str, str]] = []

        def reconfigure(self, **kwargs: str) -> None:
            self.calls.append(kwargs)

    stdout = Stream()
    stderr = Stream()
    monkeypatch.setattr(serve.sys, "stdout", stdout)
    monkeypatch.setattr(serve.sys, "stderr", stderr)

    # When: the service configures its startup streams.
    serve._configure_console_encoding()

    # Then: Unicode startup diagnostics cannot crash on the Windows code page.
    expected = {"encoding": "utf-8", "errors": "backslashreplace"}
    assert stdout.calls == [expected]
    assert stderr.calls == [expected]


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


def test_direct_source_core_delegates_to_the_public_foreground_lifecycle(
    monkeypatch,
) -> None:
    # Given: a developer invokes the Core entrypoint directly.
    calls: list[tuple[str, list[str]]] = []
    monkeypatch.delenv("ELFIENEST_MANAGED_START", raising=False)
    monkeypatch.setattr(
        serve.sys,
        "argv",
        ["scripts/serve.py", "--port", "8123", "--runtime-mode", "release"],
    )
    monkeypatch.setattr(
        serve.os,
        "execv",
        lambda executable, arguments: calls.append((executable, arguments)),
    )

    # When
    _delegate_direct_source_invocation()

    # Then: the same Supervisor entrypoint owns the generation, and the
    # runtime-mode choice is preserved for preflight.
    assert calls == [
        (
            serve.sys.executable,
            [
                serve.sys.executable,
                str(PROJECT_ROOT / "scripts" / "elfienest.py"),
                "serve",
                "--port",
                "8123",
                "--runtime-mode",
                "release",
            ],
        )
    ]
    assert os.environ["ELFIENEST_RUNTIME_MODE"] == "release"
