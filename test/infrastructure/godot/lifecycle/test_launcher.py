"""Authority-host routing and launch contract tests."""

from __future__ import annotations

import errno
import os
import signal
from pathlib import Path
from types import SimpleNamespace

import pytest

from infrastructure.godot.lifecycle import launcher


def _source_electron(project_root: Path) -> tuple[Path, Path]:
    electron_package = project_root / "app/interfaces/desktop/node_modules/electron"
    electron = electron_package / "dist/electron-bin"
    electron.parent.mkdir(parents=True)
    electron.write_text("electron", encoding="utf-8")
    electron.chmod(0o755)
    (electron_package / "path.txt").write_text("electron-bin", encoding="utf-8")
    electron_wrapper = (
        project_root / "app/interfaces/desktop/node_modules/.bin/electron"
    )
    electron_wrapper.parent.mkdir(parents=True)
    electron_wrapper.write_text("electron wrapper", encoding="utf-8")
    electron_wrapper.chmod(0o755)
    host_main = project_root / "app/bootstrap/desktop_host/host_main.mjs"
    host_main.parent.mkdir(parents=True)
    host_main.write_text("main", encoding="utf-8")
    return electron, host_main


@pytest.mark.parametrize("platform_name", ["darwin", "win32"])
def test_graphical_source_platform_routes_to_hidden_electron_authority(
    tmp_path: Path,
    platform_name: str,
) -> None:
    # Given: a graphical source checkout has the existing Electron host artifacts.
    electron, host_main = _source_electron(tmp_path)
    request = launcher.AuthorityLaunchRequest(
        project_root=tmp_path,
        http_port=18100,
        ws_port=18101,
        nonce="generation-nonce",
    )

    # When: lifecycle resolves the authority host for macOS or Windows.
    plan = launcher.plan_godot_runtime_launch(
        request,
        platform_name=platform_name,
        environment={},
    )

    # Then: it owns the real Electron process (not the forwarding CLI wrapper)
    # and uses the same-origin Web authority URL.
    assert plan.host_kind is launcher.RuntimeHostKind.ELECTRON_AUTHORITY
    assert plan.command == (
        str(electron.resolve()),
        str(host_main.resolve()),
        "--elfienest-role=godot-authority",
    )
    environment = dict(plan.environment)
    assert environment["ELFIENEST_PROJECT_ROOT"] == str(tmp_path.resolve())
    authority_url = environment["ELFIENEST_GODOT_URL"]
    assert authority_url.startswith(
        "http://127.0.0.1:18100/runtime/godot/elfienest.html?"
    )
    assert "mode=authority" in authority_url
    assert "ws=ws%3A%2F%2F127.0.0.1%3A18101" in authority_url
    assert "nonce=generation-nonce" in authority_url
    assert "generation-nonce" not in plan.command
    assert environment["ELFIENEST_AUTHORITY_NAMESPACE"].startswith(
        "elfienest.godot-authority."
    )


def test_authority_launch_plan_passes_core_pid_to_electron(
    tmp_path: Path,
) -> None:
    electron, _host_main = _source_electron(tmp_path)
    request = launcher.AuthorityLaunchRequest(
        project_root=tmp_path,
        http_port=18101,
        ws_port=18102,
        nonce="generation-nonce",
        core_pid=12345,
    )

    plan = launcher.plan_godot_runtime_launch(
        request,
        platform_name="darwin",
        environment={},
    )

    assert plan.command[0] == str(electron.resolve())
    assert dict(plan.environment)["ELFIENEST_CORE_PID"] == "12345"


def test_corrupt_source_electron_path_is_treated_as_a_missing_artifact(
    tmp_path: Path,
) -> None:
    electron_package = tmp_path / "app/interfaces/desktop/node_modules/electron"
    electron_package.mkdir(parents=True)
    (electron_package / "path.txt").write_bytes(b"\xff")

    assert launcher._electron_command(tmp_path, {}) is None


def test_electron_authority_namespace_is_scoped_to_the_checkout(
    tmp_path: Path,
) -> None:
    # Given: two source checkouts on one machine both have Electron authority artifacts.
    first = tmp_path / "first"
    second = tmp_path / "second"
    _source_electron(first)
    _source_electron(second)

    # When: each checkout resolves its authority launch plan.
    first_plan = launcher.plan_godot_runtime_launch(
        launcher.AuthorityLaunchRequest(first, 18102, 18103, "first-nonce"),
        platform_name="darwin",
        environment={},
    )
    repeated_first_plan = launcher.plan_godot_runtime_launch(
        launcher.AuthorityLaunchRequest(first, 18104, 18105, "second-nonce"),
        platform_name="darwin",
        environment={},
    )
    second_plan = launcher.plan_godot_runtime_launch(
        launcher.AuthorityLaunchRequest(second, 18106, 18107, "third-nonce"),
        platform_name="darwin",
        environment={},
    )

    # Then: Electron single-instance locks are stable per checkout, not global.
    first_namespace = dict(first_plan.environment)["ELFIENEST_AUTHORITY_NAMESPACE"]
    assert (
        first_namespace
        == dict(repeated_first_plan.environment)["ELFIENEST_AUTHORITY_NAMESPACE"]
    )
    assert (
        first_namespace
        != dict(second_plan.environment)["ELFIENEST_AUTHORITY_NAMESPACE"]
    )


def test_electron_authority_uses_runtime_scoped_user_data_when_supervised(
    tmp_path: Path,
) -> None:
    _source_electron(tmp_path)
    runtime_log = tmp_path / "smoke-home" / "logs" / "service.log"
    request = launcher.AuthorityLaunchRequest(tmp_path, 18130, 18131, "nonce")

    plan = launcher.plan_godot_runtime_launch(
        request,
        platform_name="win32",
        environment={"ELFIENEST_RUNTIME_LOG": str(runtime_log)},
    )

    assert dict(plan.environment)["ELFIENEST_AUTHORITY_USER_DATA"] == str(
        runtime_log.parent / "authority-user-data"
    )


def test_displayless_linux_routes_to_the_single_dedicated_artifact(
    tmp_path: Path,
) -> None:
    # Given: a displayless Linux host has the built Dedicated runtime.
    binary = tmp_path / "build/components/godot-linux-dedicated/ElfieNestRuntime"
    binary.parent.mkdir(parents=True)
    binary.write_text("runtime", encoding="utf-8")
    binary.chmod(0o755)
    request = launcher.AuthorityLaunchRequest(tmp_path, 18110, 18111, "linux-nonce")

    # When: no X11 or Wayland display is present.
    plan = launcher.plan_godot_runtime_launch(
        request,
        platform_name="linux",
        environment={},
    )

    # Then: only the Linux Dedicated host is selected with nonce in its environment.
    assert plan.host_kind is launcher.RuntimeHostKind.LINUX_DEDICATED
    assert plan.command == (str(binary.resolve()),)
    environment = dict(plan.environment)
    assert environment["ELFIENEST_GODOT_MODE"] == "authority"
    assert environment["ELFIENEST_GODOT_WS"] == "ws://127.0.0.1:18111"
    assert environment["ELFIENEST_GODOT_NONCE"] == "linux-nonce"


def test_graphical_linux_uses_electron_when_the_source_host_is_available(
    tmp_path: Path,
) -> None:
    # Given: Linux has a display and the source Electron host is executable.
    _source_electron(tmp_path)
    request = launcher.AuthorityLaunchRequest(tmp_path, 18120, 18121, "nonce")

    # When: authority routing observes graphical Linux.
    plan = launcher.plan_godot_runtime_launch(
        request,
        platform_name="linux",
        environment={"DISPLAY": ":99"},
    )

    # Then: it may use the existing hidden Electron authority host.
    assert plan.host_kind is launcher.RuntimeHostKind.ELECTRON_AUTHORITY


def test_explicit_runtime_binary_is_a_dedicated_override_and_launch_error_is_typed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a caller explicitly supplies a native Runtime that the OS cannot execute.
    binary = tmp_path / "ElfieNestRuntime"
    binary.write_text("linux-elf", encoding="utf-8")
    binary.chmod(0o755)
    request = launcher.AuthorityLaunchRequest(tmp_path, 18130, 18131, "nonce")

    def fail_exec(*_args, **_kwargs):
        raise OSError(errno.ENOEXEC, os.strerror(errno.ENOEXEC), str(binary))

    monkeypatch.setattr(launcher.subprocess, "Popen", fail_exec)

    # When / Then: the override never falls back to Electron or disappears as None.
    with pytest.raises(launcher.AuthorityLaunchError) as captured:
        launcher.start_godot_runtime(
            request,
            platform_name="darwin",
            environment={"ELFIENEST_RUNTIME_BIN": str(binary)},
        )
    assert captured.value.kind is launcher.AuthorityLaunchFailureKind.PROCESS_LAUNCH
    assert captured.value.target == binary.resolve()
    assert "Exec format" in str(captured.value)


def test_explicit_packaged_electron_host_override_is_scoped_to_authority(
    tmp_path: Path,
) -> None:
    # Given: an installed runtime exposes its packaged Electron executable explicitly.
    desktop = tmp_path / "ElfieNest"
    desktop.write_text("desktop", encoding="utf-8")
    desktop.chmod(0o755)
    request = launcher.AuthorityLaunchRequest(tmp_path, 18140, 18141, "nonce")

    # When: the narrow runtime-host override selects Electron authority.
    plan = launcher.plan_godot_runtime_launch(
        request,
        platform_name="linux",
        environment={
            "ELFIENEST_RUNTIME_HOST": "electron",
            "ELFIENEST_DESKTOP_BIN": str(desktop),
        },
    )

    # Then: the packaged host receives only the internal authority role.
    assert plan.command == (
        str(desktop.resolve()),
        "--elfienest-role=godot-authority",
    )


def test_authority_output_is_persisted_in_its_own_rotated_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source_electron(tmp_path)
    log_dir = tmp_path / "data" / "logs"
    log_dir.mkdir(parents=True)
    authority_log = log_dir / "authority.log"
    authority_console_log = log_dir / "authority-console.log"
    authority_console_log.write_bytes(b"old authority failure")
    calls: list[dict[str, object]] = []

    class Process:
        pid = 18155

    def popen(_command, **kwargs):
        calls.append(kwargs)
        return Process()

    monkeypatch.setattr(launcher, "AUTHORITY_LOG_MAX_BYTES", 4)
    monkeypatch.setattr(launcher.subprocess, "Popen", popen)

    process_handle = launcher.start_godot_runtime(
        launcher.AuthorityLaunchRequest(tmp_path, 18150, 18151, "nonce"),
        platform_name="darwin",
        environment={
            "ELFIENEST_RUNTIME_LOG": str(log_dir / "service.log"),
            "ELFIENEST_AUTHORITY_LOG": str(tmp_path / "outside.log"),
        },
    )

    assert process_handle is not None
    assert calls[0]["stdout"] is calls[0]["stderr"]
    assert Path(calls[0]["stdout"].name) == authority_console_log
    assert dict(calls[0]["env"])["ELFIENEST_AUTHORITY_LOG"] == str(authority_log)
    assert authority_console_log.with_name("authority-console.log.1").read_bytes() == (
        b"old authority failure"
    )
    assert authority_console_log.stat().st_mode & 0o777 == 0o600


def test_missing_selected_host_is_a_diagnostic_failure(tmp_path: Path) -> None:
    # Given: displayless Linux has no Dedicated artifact.
    request = launcher.AuthorityLaunchRequest(tmp_path, 18150, 18151, "nonce")

    # When / Then: selection reports a typed missing-artifact cause.
    with pytest.raises(launcher.AuthorityLaunchError) as captured:
        launcher.plan_godot_runtime_launch(
            request,
            platform_name="linux",
            environment={},
        )
    assert captured.value.kind is launcher.AuthorityLaunchFailureKind.MISSING_ARTIFACT


def test_stop_targets_only_the_process_started_by_this_launcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: one owned child process is live.
    calls: list[tuple[str, float | None]] = []

    class OwnedProcess:
        pid = 18161

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            calls.append(("terminate", None))

        def wait(self, timeout: float) -> int:
            calls.append(("wait", timeout))
            return 0

        def kill(self) -> None:
            calls.append(("kill", None))

    groups: list[tuple[int, int]] = []
    monkeypatch.setattr(
        launcher.os,
        "killpg",
        lambda pid, sig: groups.append((pid, sig)),
    )
    monkeypatch.setattr(launcher.os, "name", "posix")

    # When: lifecycle stops its authority handle.
    launcher.stop_godot_runtime(OwnedProcess())

    # Then: only that owned start_new_session process group is terminated.
    assert groups == [(18161, signal.SIGTERM)]
    assert calls == [("wait", launcher.AUTHORITY_STOP_GRACE_SECONDS)]


def test_stop_force_kills_the_owned_process_group_after_grace_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, float | None]] = []

    class OwnedProcess:
        pid = 18162
        wait_count = 0

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            raise AssertionError("POSIX cleanup must target the owned process group")

        def wait(self, timeout: float) -> int:
            calls.append(("wait", timeout))
            self.wait_count += 1
            if self.wait_count == 1:
                raise launcher.subprocess.TimeoutExpired("authority", timeout)
            return -signal.SIGKILL

        def kill(self) -> None:
            raise AssertionError("forced cleanup must include descendants")

    groups: list[tuple[int, int]] = []
    monkeypatch.setattr(
        launcher.os,
        "killpg",
        lambda pid, sig: groups.append((pid, sig)),
    )
    monkeypatch.setattr(launcher.os, "name", "posix")

    launcher.stop_godot_runtime(OwnedProcess())

    assert groups == [
        (18162, signal.SIGTERM),
        (18162, signal.SIGKILL),
    ]
    assert calls == [
        ("wait", launcher.AUTHORITY_STOP_GRACE_SECONDS),
        ("wait", launcher.AUTHORITY_STOP_FORCE_GRACE_SECONDS),
    ]


def test_stop_uses_windows_process_tree_for_owned_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    class OwnedProcess:
        pid = 18162

        def poll(self) -> None:
            return None

        def wait(self, timeout: float) -> int:
            calls.append((("wait",), {"timeout": timeout}))
            return 0

        def terminate(self) -> None:
            raise AssertionError("Windows cleanup must include descendants")

        def kill(self) -> None:
            raise AssertionError("Windows cleanup must include descendants")

    def run(command, **kwargs):
        calls.append((tuple(command), kwargs))
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(launcher, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(launcher.subprocess, "run", run)

    launcher.stop_godot_runtime(OwnedProcess())

    assert calls[0][0] == ("taskkill", "/PID", "18162", "/T")
    assert calls[1][0] == ("wait",)


def test_windows_authority_job_is_closed_when_process_already_exited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class Job:
        def close(self) -> None:
            calls.append("close")

    class OwnedProcess:
        pid = 18163

        def poll(self) -> int:
            return 0

    monkeypatch.setattr(launcher, "os", SimpleNamespace(name="nt"))
    launcher._WINDOWS_AUTHORITY_JOBS[18163] = Job()

    launcher.stop_godot_runtime(OwnedProcess())

    assert calls == ["close"]
    assert 18163 not in launcher._WINDOWS_AUTHORITY_JOBS
