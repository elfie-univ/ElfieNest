from __future__ import annotations

from pathlib import Path

import pytest

from scripts.internal.release import release_install_smoke
from scripts.internal.release.release_install_smoke import (
    NativePackageAdapter,
    ReleaseInstallSmokeError,
    _is_owned_symlink,
    _wait_for_state,
    run_install_smoke,
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
        if arguments[0] == "status":
            return '{"state":"' + self.states.pop(0) + '"}'
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
    assert home.is_dir()
    assert adapter.calls[0] == "uninstall"
    assert adapter.calls[-1] == "verify-uninstalled"


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
        return ""

    monkeypatch.setattr(
        "scripts.internal.release.release_install_smoke._run_checked", fake_run_checked
    )

    adapter.uninstall()

    assert commands == [(str(install_root / "Uninstall ElfieNest.exe"), "/S")]
