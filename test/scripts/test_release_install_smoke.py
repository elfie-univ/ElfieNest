from __future__ import annotations

from pathlib import Path

import pytest

from scripts.release_install_smoke import (
    NativePackageAdapter,
    ReleaseInstallSmokeError,
    run_install_smoke,
)


class FakeAdapter:
    def __init__(self, home: Path) -> None:
        self.home = home
        self.calls: list[str] = []
        self.states = ["core_ready", "offline"]

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
    assert home.is_dir()
    assert adapter.calls[0] == "uninstall"
    assert adapter.calls[-1] == "verify-uninstalled"


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

    monkeypatch.setattr("scripts.release_install_smoke._run_checked", fake_run_checked)

    adapter = NativePackageAdapter("linux-x64", artifact)
    adapter.install()

    assert commands[0] == (
        "sudo",
        "apt-get",
        "install",
        "--yes",
        str(artifact),
    )
    assert adapter.package_name == "elfienest-desktop"


def test_linux_native_verification_requires_the_gui_launcher(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "ElfieNest.deb"
    artifact.write_bytes(b"native installer")
    inspected: list[Path] = []

    def record_exists(path: Path) -> bool:
        inspected.append(path)
        return True

    monkeypatch.setattr(Path, "exists", record_exists)

    NativePackageAdapter("linux-x64", artifact).verify_installed()

    assert Path("/usr/bin/elfienest-gui") in inspected
