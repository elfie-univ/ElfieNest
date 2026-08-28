from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.internal.release import release_install_smoke
from scripts.internal.release.release_install_smoke import (
    NativePackageAdapter,
    ReleaseInstallSmokeError,
    _diagnostic_has_event,
    _is_owned_symlink,
    _service_log_tail,
    _smoke_environment,
    _start_scripted_model_server,
    _stop_scripted_model_server,
    _verify_duplicate_start,
    _wait_for_state,
    run_install_smoke,
)


def test_smoke_environment_pins_desktop_app_data_to_isolated_home(
    tmp_path: Path,
) -> None:
    home = tmp_path / "smoke-home"
    environment = _smoke_environment(home)

    assert environment["ELFIE_HOME"] == str(home.resolve())
    assert environment["ELFIENEST_DESKTOP_APP_DATA"] == str(
        (home / "desktop-app-data").resolve()
    )


def test_linux_native_adapter_uses_the_deb_install_root() -> None:
    adapter = NativePackageAdapter("linux-x64", Path("ElfieNest.deb"))

    assert adapter.install_root == release_install_smoke.LINUX_INSTALL_ROOT


def test_scripted_model_process_is_loopback_and_stops_with_summary(
    tmp_path: Path,
) -> None:
    server = _start_scripted_model_server(tmp_path / "home")
    try:
        assert server.pid > 0
        assert server.endpoint.startswith("http://127.0.0.1:")
    finally:
        summary = _stop_scripted_model_server(server)

    assert summary["request_count"] == 0
    assert server.process.poll() is not None


def test_duplicate_start_keeps_generation_and_owned_processes(tmp_path: Path) -> None:
    home = tmp_path / "home"
    receipt = home / "runtime" / "desktop.pid"
    receipt.parent.mkdir(parents=True)
    receipt.write_text("100\n", encoding="utf-8")

    class Adapter:
        def run_cli(self, arguments, environment) -> str:
            del environment
            assert arguments[0] in {"start", "status"}
            return json.dumps(
                {
                    "state": "world_ready",
                    "generation": 7,
                    "components": [
                        {"name": "core", "pid": 101},
                        {"name": "godot_authority", "pid": 102},
                    ],
                }
            )

    result = _verify_duplicate_start(
        {
            "state": "world_ready",
            "generation": 7,
            "components": [
                {"name": "core", "pid": 101},
                {"name": "godot_authority", "pid": 102},
            ],
        },
        native=Adapter(),
        environment={},
        home=home,
        monotonic=lambda: 0.0,
        sleeper=lambda _seconds: None,
        timeout_seconds=0.0,
    )

    assert result == {
        "same_generation": True,
        "generation": 7,
        "owned_pids": [100, 101, 102],
    }


def test_viewer_marker_reader_accepts_only_the_named_json_event(tmp_path: Path) -> None:
    diagnostics = tmp_path / "desktop-events.jsonl"
    diagnostics.write_text(
        "not-json\n"
        '{"event":"desktop_process_started"}\n'
        '{"event":"management_page_ready"}\n',
        encoding="utf-8",
    )

    assert _diagnostic_has_event(diagnostics, "management_page_ready")
    assert not _diagnostic_has_event(diagnostics, "renderer_error")
    assert not _diagnostic_has_event(
        tmp_path / "missing.jsonl", "management_page_ready"
    )


class FakeAdapter:
    def __init__(self, home: Path) -> None:
        self.home = home
        self.calls: list[str] = []
        self.states = ["world_ready", "offline"]

    def install(self) -> None:
        self.calls.append("install")
        self.home.mkdir(parents=True, exist_ok=True)

    def verify_installed(self) -> None:
        self.calls.append("verify-installed")

    def run_cli(self, arguments, environment) -> str:
        self.calls.append("cli:" + " ".join(arguments))
        if arguments[0] == "start":
            receipt = self.home / "runtime" / "desktop.pid"
            receipt.parent.mkdir(parents=True, exist_ok=True)
            receipt.write_text("99999999\n", encoding="utf-8")
        if arguments[0] == "stop":
            (self.home / "runtime" / "desktop.pid").unlink(missing_ok=True)
        if arguments[0] == "status":
            state = self.states.pop(0)
            if state == "world_ready":
                return (
                    '{"state":"world_ready","components":'
                    '[{"name":"core","pid":99999998},'
                    '{"name":"godot_authority","pid":99999997}]}'
                )
            return '{"state":"' + state + '"}'
        return "{}"

    def uninstall(self) -> None:
        self.calls.append("uninstall")

    def verify_uninstalled(self) -> None:
        self.calls.append("verify-uninstalled")


def test_smoke_runner_publishes_install_upgrade_start_stop_evidence(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "ElfieNest.pkg"
    artifact.write_bytes(b"native installer")
    home = tmp_path / "user-data"
    evidence = tmp_path / "evidence.json"
    adapter = FakeAdapter(home)

    payload = run_install_smoke(
        "darwin-arm64",
        artifact,
        evidence,
        adapter=adapter,
        smoke_home=home,
        monotonic=lambda: 0.0,
        sleeper=lambda _seconds: None,
    )

    assert payload["result"] == "passed"
    assert [phase["name"] for phase in payload["phases"]] == [
        "install",
        "start",
        "health",
        "stop",
        "upgrade",
        "uninstall",
    ]
    assert evidence.is_file()
    assert payload["cycles"][0]["reached_state"] == "world_ready"
    assert payload["cycles"][0]["desktop_controller_pid"] == 99999999
    assert payload["cycles"][0]["verified_stopped_pids"] == [
        99999997,
        99999998,
        99999999,
    ]
    assert home.is_dir()
    assert adapter.calls[0] == "uninstall"
    assert adapter.calls[-1] == "verify-uninstalled"


def test_smoke_runner_executes_each_requested_lifecycle_cycle(tmp_path: Path) -> None:
    artifact = tmp_path / "ElfieNest.deb"
    artifact.write_bytes(b"native installer")
    home = tmp_path / "user-data"
    adapter = FakeAdapter(home)
    adapter.states = ["world_ready", "offline"] * 3

    payload = run_install_smoke(
        "linux-x64",
        artifact,
        tmp_path / "evidence.json",
        cycles=3,
        adapter=adapter,
        smoke_home=home,
        monotonic=lambda: 0.0,
        sleeper=lambda _seconds: None,
    )

    assert [cycle["cycle"] for cycle in payload["cycles"]] == [1, 2, 3]
    assert adapter.calls.count("cli:start --json --loopback") == 3
    assert adapter.calls.count("cli:stop") == 3


def test_smoke_runner_uses_the_installed_desktop_controller_environment(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "ElfieNest.deb"
    artifact.write_bytes(b"native installer")
    home = tmp_path / "user-data"
    observed_environments: list[dict[str, str]] = []

    class RecordingAdapter(FakeAdapter):
        def run_cli(self, arguments, environment) -> str:
            observed_environments.append(dict(environment))
            return super().run_cli(arguments, environment)

    run_install_smoke(
        "linux-x64",
        artifact,
        tmp_path / "evidence.json",
        adapter=RecordingAdapter(home),
        smoke_home=home,
        monotonic=lambda: 0.0,
        sleeper=lambda _seconds: None,
    )

    assert observed_environments
    assert all(
        "ELFIENEST_CONTROLLER_CLIENT" not in environment
        for environment in observed_environments
    )


def test_smoke_runner_rejects_a_missing_desktop_controller_receipt(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "ElfieNest.deb"
    artifact.write_bytes(b"native installer")
    home = tmp_path / "user-data"

    class MissingControllerAdapter(FakeAdapter):
        def run_cli(self, arguments, environment) -> str:
            output = super().run_cli(arguments, environment)
            if arguments[0] == "start":
                (self.home / "runtime" / "desktop.pid").unlink(missing_ok=True)
            return output

    with pytest.raises(
        ReleaseInstallSmokeError,
        match="desktop-controller-receipt-missing",
    ):
        run_install_smoke(
            "linux-x64",
            artifact,
            tmp_path / "evidence.json",
            adapter=MissingControllerAdapter(home),
            smoke_home=home,
            monotonic=lambda: 0.0,
            sleeper=lambda _seconds: None,
        )


def test_smoke_runner_rejects_missing_core_or_godot_process_evidence(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "ElfieNest.deb"
    artifact.write_bytes(b"native installer")
    home = tmp_path / "user-data"

    class MissingGodotAdapter(FakeAdapter):
        def run_cli(self, arguments, environment) -> str:
            output = super().run_cli(arguments, environment)
            if arguments[0] == "status" and "world_ready" in output:
                return (
                    '{"state":"world_ready","components":'
                    '[{"name":"core","pid":99999998}]}'
                )
            return output

    with pytest.raises(
        ReleaseInstallSmokeError,
        match="component-pids-missing names=godot_authority",
    ):
        run_install_smoke(
            "linux-x64",
            artifact,
            tmp_path / "evidence.json",
            adapter=MissingGodotAdapter(home),
            smoke_home=home,
            monotonic=lambda: 0.0,
            sleeper=lambda _seconds: None,
        )


def test_smoke_runner_rejects_a_surviving_owned_process(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "user-data"

    monkeypatch.setattr(
        release_install_smoke,
        "_pid_exists",
        lambda pid: pid == 99999997,
    )

    clock = iter((0.0, 11.0))
    with pytest.raises(
        ReleaseInstallSmokeError,
        match="owned-processes-remain.*99999997",
    ):
        release_install_smoke._wait_for_owned_processes_stopped(
            (99999997,),
            home=home,
            monotonic=lambda: next(clock),
            sleeper=lambda _seconds: None,
            timeout_seconds=10.0,
        )


def test_pid_exists_uses_the_read_only_platform_inspector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[int] = []

    class FakeInspector:
        def exists(self, pid: int) -> bool:
            observed.append(pid)
            return False

    monkeypatch.setattr(
        release_install_smoke,
        "DefaultProcessInspector",
        FakeInspector,
    )

    assert release_install_smoke._pid_exists(12345) is False
    assert observed == [12345]


def test_smoke_runner_does_not_accept_core_ready_without_the_world() -> None:
    class CoreOnlyAdapter:
        def run_cli(self, arguments, environment) -> str:
            del arguments, environment
            return '{"state":"core_ready"}'

    with pytest.raises(
        ReleaseInstallSmokeError,
        match=r"expected=\['world_ready'\] actual=core_ready",
    ):
        _wait_for_state(
            CoreOnlyAdapter(),  # type: ignore[arg-type]
            {},
            expected={"world_ready"},
            monotonic=lambda: 0.0,
            sleeper=lambda _seconds: None,
            timeout_seconds=0.0,
        )


def test_smoke_runner_rejects_missing_artifact(tmp_path: Path) -> None:
    with pytest.raises(ReleaseInstallSmokeError, match="artifact-missing"):
        run_install_smoke(
            "linux-x64",
            tmp_path / "missing.deb",
            tmp_path / "evidence.json",
        )


def test_smoke_runner_requires_at_least_one_cycle(tmp_path: Path) -> None:
    artifact = tmp_path / "ElfieNest.deb"
    artifact.write_bytes(b"native installer")

    with pytest.raises(ReleaseInstallSmokeError, match="cycles-invalid"):
        run_install_smoke(
            "linux-x64",
            artifact,
            tmp_path / "evidence.json",
            cycles=0,
        )


def test_smoke_runner_includes_service_log_when_start_fails(tmp_path: Path) -> None:
    artifact = tmp_path / "ElfieNest.deb"
    artifact.write_bytes(b"native installer")
    home = tmp_path / "user-data"

    class FailingStartAdapter(FakeAdapter):
        def run_cli(self, arguments, environment) -> str:
            if arguments[0] == "start":
                log_path = self.home / "logs" / "service.log"
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text("core-start-failure\n", encoding="utf-8")
                raise ReleaseInstallSmokeError("start-failed")
            return super().run_cli(arguments, environment)

    with pytest.raises(
        ReleaseInstallSmokeError,
        match="service-log-tail=core-start-failure",
    ):
        run_install_smoke(
            "linux-x64",
            artifact,
            tmp_path / "evidence.json",
            adapter=FailingStartAdapter(home),
            smoke_home=home,
        )


def test_product_journey_failure_preserves_redacted_api_detail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from scripts.internal.release import installed_product_journey

    def fail(*_args, **_kwargs):
        raise installed_product_journey.JourneyFailure(
            "candidate_set_failed",
            phase="adoption",
            detail="status=503 api_code=model_unconfigured",
        )

    monkeypatch.setattr(
        installed_product_journey,
        "run_installed_product_journey",
        fail,
    )

    class Native:
        def run_cli(self, arguments, environment) -> str:
            del arguments, environment
            return "{}"

    with pytest.raises(
        ReleaseInstallSmokeError,
        match=r"phase=adoption code=candidate_set_failed detail=status=503 api_code=model_unconfigured",
    ):
        release_install_smoke._run_product_journey(
            {
                "endpoints": [
                    {
                        "name": "http",
                        "scheme": "http",
                        "host": "127.0.0.1",
                        "port": 8000,
                    }
                ]
            },
            home=tmp_path,
            model_endpoint="http://127.0.0.1:9000/v1",
            mode="initial",
            native=Native(),
            environment={},
            timeout_seconds=1.0,
        )


def test_smoke_runner_includes_raw_console_when_core_fails_before_logging(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "ElfieNest.deb"
    artifact.write_bytes(b"native installer")
    home = tmp_path / "user-data"

    class FailingStartAdapter(FakeAdapter):
        def run_cli(self, arguments, environment) -> str:
            if arguments[0] == "start":
                log_path = self.home / "logs" / "service-console.log"
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text(
                    "bootstrap failed token=do-not-publish\n",
                    encoding="utf-8",
                )
                raise ReleaseInstallSmokeError("start-failed")
            return super().run_cli(arguments, environment)

    with pytest.raises(ReleaseInstallSmokeError) as raised:
        run_install_smoke(
            "linux-x64",
            artifact,
            tmp_path / "evidence.json",
            adapter=FailingStartAdapter(home),
            smoke_home=home,
        )

    detail = str(raised.value)
    assert "bootstrap failed" in detail
    assert "do-not-publish" not in detail
    assert "<redacted>" in detail


def test_smoke_runner_includes_desktop_controller_diagnostics_on_start_failure(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "ElfieNest.deb"
    artifact.write_bytes(b"native installer")
    home = tmp_path / "user-data"

    class FailingStartAdapter(FakeAdapter):
        def desktop_diagnostics_path(self, selected_home: Path) -> Path:
            path = selected_home / "desktop-events.jsonl"
            path.write_text(
                '{"event":"desktop_start_failed","message":"controller failed"}\n',
                encoding="utf-8",
            )
            return path

        def run_cli(self, arguments, environment) -> str:
            if arguments[0] == "start":
                raise ReleaseInstallSmokeError("start-failed")
            return super().run_cli(arguments, environment)

    with pytest.raises(
        ReleaseInstallSmokeError,
        match="desktop_start_failed.*controller failed",
    ):
        run_install_smoke(
            "linux-x64",
            artifact,
            tmp_path / "evidence.json",
            adapter=FailingStartAdapter(home),
            smoke_home=home,
        )
    diagnostics = json.loads(
        (home / "failure-diagnostics.json").read_text(encoding="utf-8")
    )
    assert diagnostics["target"] == "linux-x64"
    assert "desktop_start_failed" in diagnostics["logs"]
    assert "controller failed" in diagnostics["logs"]


def test_service_log_tail_redacts_desktop_controller_diagnostics(
    tmp_path: Path,
) -> None:
    home = tmp_path / "user-data"
    path = home / "desktop-events.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"event":"desktop_start_failed","token":"do-not-publish"}\n',
        encoding="utf-8",
    )

    class Adapter:
        def desktop_diagnostics_path(self, selected_home: Path) -> Path:
            assert selected_home == home
            return path

    detail = _service_log_tail(home, native=Adapter())
    assert "desktop_start_failed" in detail
    assert "do-not-publish" not in detail
    assert "<redacted>" in detail


def test_linux_native_install_resolves_declared_deb_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact = (tmp_path / "ElfieNest.deb").resolve()
    artifact.write_bytes(b"native installer")
    commands: list[tuple[str, ...]] = []

    def fake_run_checked(command, *, environment=None) -> str:
        del environment
        normalized = tuple(command)
        commands.append(normalized)
        if normalized[:2] == ("dpkg-deb", "--field"):
            return "elfienest-desktop\n"
        return ""

    monkeypatch.setattr(
        "scripts.internal.release.release_install_smoke._run_checked", fake_run_checked
    )

    adapter = NativePackageAdapter("linux-x64", artifact)
    adapter.install()

    assert commands[0] == (
        "dpkg-deb",
        "--field",
        str(artifact),
        "Package",
    )
    assert commands[1] == (
        "sudo",
        "apt-get",
        "install",
        "--yes",
        str(artifact),
    )
    assert adapter.package_name == "elfienest-desktop"


def test_linux_native_initial_cleanup_purges_the_artifact_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact = (tmp_path / "ElfieNest.deb").resolve()
    artifact.write_bytes(b"native installer")
    commands: list[tuple[str, ...]] = []

    monkeypatch.setattr(
        "scripts.internal.release.release_install_smoke._run_checked",
        lambda command, *, environment=None: "elfienest-desktop\n",
    )
    monkeypatch.setattr(
        "scripts.internal.release.release_install_smoke._run_allow_failure",
        lambda command: commands.append(tuple(command)),
    )

    adapter = NativePackageAdapter("linux-x64", artifact)
    adapter.uninstall()

    assert adapter.package_name == "elfienest-desktop"
    assert commands == [("sudo", "dpkg", "--purge", "elfienest-desktop")]


def test_owned_symlink_requires_the_exact_packaged_target(tmp_path: Path) -> None:
    target = tmp_path / "ElfieNestCli"
    target.write_bytes(b"cli")
    launcher = tmp_path / "elfienest"
    launcher.symlink_to(target)

    assert _is_owned_symlink(launcher, target)

    launcher.unlink()
    launcher.symlink_to(tmp_path / "another-cli")
    assert not _is_owned_symlink(launcher, target)

    launcher.unlink()
    launcher.write_text("user command", encoding="utf-8")
    assert not _is_owned_symlink(launcher, target)


def test_macos_native_cleanup_preserves_an_unrelated_global_launcher(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    install_root = tmp_path / "ElfieNest.app"
    launcher = tmp_path / "elfienest"
    launcher.symlink_to(tmp_path / "another-cli")
    checked: list[tuple[str, ...]] = []

    monkeypatch.setattr(release_install_smoke, "MAC_INSTALL_ROOT", install_root)
    monkeypatch.setattr(release_install_smoke, "GLOBAL_CLI_LAUNCHER", launcher)
    monkeypatch.setattr(
        release_install_smoke,
        "_run_checked",
        lambda command, *, environment=None: checked.append(tuple(command)) or "",
    )
    monkeypatch.setattr(
        release_install_smoke, "_run_allow_failure", lambda command: None
    )

    adapter = NativePackageAdapter("darwin-arm64", tmp_path / "ElfieNest.pkg")
    adapter.uninstall()
    adapter.verify_uninstalled()

    assert checked == []
    assert launcher.is_symlink()


def test_macos_native_cleanup_removes_only_its_exact_global_launcher(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    install_root = tmp_path / "ElfieNest.app"
    cli = install_root / "Contents/Resources/management-cli/ElfieNestCli"
    launcher = tmp_path / "elfienest"
    launcher.symlink_to(cli)
    checked: list[tuple[str, ...]] = []

    monkeypatch.setattr(release_install_smoke, "MAC_INSTALL_ROOT", install_root)
    monkeypatch.setattr(release_install_smoke, "GLOBAL_CLI_LAUNCHER", launcher)
    monkeypatch.setattr(
        release_install_smoke,
        "_run_checked",
        lambda command, *, environment=None: checked.append(tuple(command)) or "",
    )
    monkeypatch.setattr(
        release_install_smoke, "_run_allow_failure", lambda command: None
    )

    NativePackageAdapter("darwin-arm64", tmp_path / "ElfieNest.pkg").uninstall()

    assert checked == [("sudo", "rm", "-f", str(launcher))]


def test_linux_native_verification_requires_the_gui_launcher(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "ElfieNest.deb"
    artifact.write_bytes(b"native installer")
    inspected: list[Path] = []
    inspected_launchers: list[tuple[Path, Path]] = []

    def record_exists(path: Path) -> bool:
        inspected.append(path)
        return True

    monkeypatch.setattr(Path, "exists", record_exists)
    monkeypatch.setattr(
        "scripts.internal.release.release_install_smoke._is_owned_symlink",
        lambda launcher, target: inspected_launchers.append((launcher, target)) or True,
    )

    NativePackageAdapter("linux-x64", artifact).verify_installed()

    assert Path("/opt/ElfieNest/elfienest-gui") in inspected
    assert (
        Path("/usr/bin/elfienest-gui"),
        Path("/opt/ElfieNest/elfienest-gui"),
    ) in inspected_launchers


def test_windows_native_uninstall_reports_a_missing_uninstaller(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "ElfieNest.exe"
    artifact.write_bytes(b"native installer")
    adapter = NativePackageAdapter("win32-x64", artifact)
    adapter.install_root = tmp_path / "install-root"

    with pytest.raises(ReleaseInstallSmokeError, match="uninstaller-missing"):
        adapter.uninstall()


def test_windows_native_uninstall_requires_a_successful_uninstaller(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "ElfieNest.exe"
    artifact.write_bytes(b"native installer")
    install_root = tmp_path / "install-root"
    install_root.mkdir()
    (install_root / "Uninstall ElfieNest.exe").write_bytes(b"uninstaller")
    adapter = NativePackageAdapter("win32-x64", artifact)
    adapter.install_root = install_root
    commands: list[tuple[str, ...]] = []

    def fake_run_checked(command, *, environment=None) -> str:
        del environment
        commands.append(tuple(command))
        (install_root / "Uninstall ElfieNest.exe").unlink()
        install_root.rmdir()
        return ""

    monkeypatch.setattr(
        "scripts.internal.release.release_install_smoke._run_checked", fake_run_checked
    )

    adapter.uninstall()

    assert commands == [(str(install_root / "Uninstall ElfieNest.exe"), "/S")]


def test_windows_native_uninstall_waits_for_async_root_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "ElfieNest.exe"
    artifact.write_bytes(b"native installer")
    install_root = tmp_path / "install-root"
    install_root.mkdir()
    uninstaller = install_root / "Uninstall ElfieNest.exe"
    uninstaller.write_bytes(b"uninstaller")
    adapter = NativePackageAdapter("win32-x64", artifact)
    adapter.install_root = install_root
    commands: list[tuple[str, ...]] = []
    sleeps = 0

    def fake_run_checked(command, *, environment=None) -> str:
        del environment
        commands.append(tuple(command))
        return ""

    def fake_sleep(_seconds: float) -> None:
        nonlocal sleeps
        sleeps += 1
        if sleeps == 2:
            uninstaller.unlink()
            install_root.rmdir()

    monkeypatch.setattr(
        "scripts.internal.release.release_install_smoke._run_checked", fake_run_checked
    )
    monkeypatch.setattr(release_install_smoke.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(release_install_smoke.time, "sleep", fake_sleep)

    adapter.uninstall()

    assert sleeps == 2
    assert commands == [(str(uninstaller), "/S")]
