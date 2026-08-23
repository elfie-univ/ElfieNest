#!/usr/bin/env python3
"""Run the native install, upgrade, startup, stop, and uninstall smoke gate.

This is deliberately a release-runner tool, not a product installer.  It only
removes files that the native package owns and keeps the user's ``ELFIE_HOME``
outside the uninstall path.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, MutableMapping, Protocol, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


SUPPORTED_TARGETS = {
    "darwin-arm64",
    "darwin-x64",
    "win32-x64",
    "linux-x64",
}
PHASE_BUDGETS_MS = {
    "install": 180_000,
    "start": 120_000,
    "health": 120_000,
    "stop": 60_000,
    "upgrade": 180_000,
    "uninstall": 120_000,
}


class ReleaseInstallSmokeError(RuntimeError):
    """Raised when a native release cannot prove a clean install lifecycle."""


class SmokeAdapter(Protocol):
    """Native package operations used by the platform-neutral smoke runner."""

    def install(self) -> None: ...

    def verify_installed(self) -> None: ...

    def run_cli(
        self, arguments: Sequence[str], environment: Mapping[str, str]
    ) -> str: ...

    def uninstall(self) -> None: ...

    def verify_uninstalled(self) -> None: ...


@dataclass(frozen=True)
class SmokePhase:
    """One typed timing result published in the release evidence."""

    name: str
    duration_ms: int
    budget_ms: int


def run_install_smoke(
    target: str,
    artifact: Path,
    evidence_output: Path,
    *,
    cycles: int = 1,
    adapter: SmokeAdapter | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    timeout_seconds: float = 120.0,
    smoke_home: Path | None = None,
) -> dict[str, object]:
    """Execute bounded native lifecycle cycles and write machine-readable evidence."""
    if target not in SUPPORTED_TARGETS:
        raise ReleaseInstallSmokeError(
            f"release-smoke-target-unsupported target={target}"
        )
    artifact = artifact.resolve()
    if not artifact.is_file():
        raise ReleaseInstallSmokeError(
            f"release-smoke-artifact-missing path={artifact}"
        )
    if cycles < 1:
        raise ReleaseInstallSmokeError("release-smoke-cycles-invalid")

    owned_home = smoke_home is None
    temporary_home = (
        tempfile.TemporaryDirectory(prefix="elfienest-release-smoke-")
        if owned_home
        else None
    )
    home = smoke_home or Path(temporary_home.name)  # type: ignore[union-attr]
    try:
        native = adapter or NativePackageAdapter(target, artifact)
        # A rerun must start from a package-owned clean surface.  Native
        # uninstall implementations are intentionally idempotent here.
        _ignore_failure(native.uninstall)
        phases: list[SmokePhase] = []
        cycle_records: list[dict[str, object]] = []
        environment = _smoke_environment(home)

        for cycle in range(1, cycles + 1):
            cycle_start = len(phases)
            phases.append(_measure("install", native.install, monotonic))
            native.verify_installed()

            phases.append(
                _measure(
                    "start",
                    lambda: _start_native_service(native, environment, home),
                    monotonic,
                )
            )
            health_started = monotonic()
            _wait_for_state(
                native,
                environment,
                expected={"core_ready", "world_ready"},
                monotonic=monotonic,
                sleeper=sleeper,
                timeout_seconds=timeout_seconds,
            )
            phases.append(
                SmokePhase(
                    "health",
                    _duration_ms(monotonic() - health_started),
                    PHASE_BUDGETS_MS["health"],
                )
            )

            stop_started = monotonic()
            native.run_cli(("stop",), environment)
            _wait_for_state(
                native,
                environment,
                expected={"offline"},
                monotonic=monotonic,
                sleeper=sleeper,
                timeout_seconds=timeout_seconds,
            )
            phases.append(
                SmokePhase(
                    "stop",
                    _duration_ms(monotonic() - stop_started),
                    PHASE_BUDGETS_MS["stop"],
                )
            )
            native.verify_installed()

            upgrade_started = monotonic()
            native.install()
            native.verify_installed()
            phases.append(
                SmokePhase(
                    "upgrade",
                    _duration_ms(monotonic() - upgrade_started),
                    PHASE_BUDGETS_MS["upgrade"],
                )
            )
            cycle_records.append(
                {
                    "cycle": cycle,
                    "phase_count": len(phases) - cycle_start,
                    "result": "passed",
                }
            )

        uninstall_started = monotonic()
        native.uninstall()
        native.verify_uninstalled()
        phases.append(
            SmokePhase(
                "uninstall",
                _duration_ms(monotonic() - uninstall_started),
                PHASE_BUDGETS_MS["uninstall"],
            )
        )
        if not home.exists():
            raise ReleaseInstallSmokeError("release-smoke-uninstall-removed-user-data")

        phase_payloads: list[dict[str, object]] = [
            {
                "name": phase.name,
                "duration_ms": phase.duration_ms,
                "budget_ms": phase.budget_ms,
                "within_budget": phase.duration_ms <= phase.budget_ms,
            }
            for phase in phases
        ]
        evidence = {
            "schema_version": 1,
            "target": target,
            "artifact": artifact.name,
            "cycles": cycle_records,
            "phases": phase_payloads,
            "result": "passed",
        }
        if any(not bool(phase["within_budget"]) for phase in phase_payloads):
            raise ReleaseInstallSmokeError("release-smoke-phase-budget-exceeded")
        evidence_output.parent.mkdir(parents=True, exist_ok=True)
        evidence_output.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return evidence
    finally:
        if temporary_home is not None:
            temporary_home.cleanup()


def _smoke_environment(home: Path) -> MutableMapping[str, str]:
    environment = dict(os.environ)
    environment.update(
        {
            "ELFIE_HOME": str(home.resolve()),
            "HOME": str(home.resolve()),
            "USERPROFILE": str(home.resolve()),
            "ELFIENEST_CONTROLLER_CLIENT": "1",
            "ELFIENEST_RUNTIME_MODE": "release",
        }
    )
    return environment


def _wait_for_state(
    adapter: SmokeAdapter,
    environment: Mapping[str, str],
    *,
    expected: set[str],
    monotonic: Callable[[], float],
    sleeper: Callable[[float], None],
    timeout_seconds: float,
) -> None:
    deadline = monotonic() + timeout_seconds
    last_state = "unknown"
    while True:
        payload = _parse_status(adapter.run_cli(("status", "--json"), environment))
        state = payload.get("state")
        if isinstance(state, str):
            last_state = state
            if state in expected:
                return
        if monotonic() >= deadline:
            raise ReleaseInstallSmokeError(
                f"release-smoke-state-timeout expected={sorted(expected)} actual={last_state}"
            )
        sleeper(0.5)


def _parse_status(output: str) -> Mapping[str, object]:
    for line in reversed(output.splitlines()):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ReleaseInstallSmokeError("release-smoke-status-not-json")


def _measure(
    name: str,
    operation: Callable[[], object],
    monotonic: Callable[[], float],
) -> SmokePhase:
    started = monotonic()
    try:
        operation()
    except ReleaseInstallSmokeError:
        raise
    except Exception as error:  # noqa: BLE001 - annotate native runner failures
        raise ReleaseInstallSmokeError(
            f"release-smoke-phase-failed phase={name} cause={error}"
        ) from error
    return SmokePhase(name, _duration_ms(monotonic() - started), PHASE_BUDGETS_MS[name])


def _start_native_service(
    native: SmokeAdapter,
    environment: Mapping[str, str],
    home: Path,
) -> None:
    """Start the installed service and preserve its diagnostic tail on failure."""
    try:
        native.run_cli(("start", "--json", "--loopback"), environment)
    except Exception as error:  # noqa: BLE001 - attach native failure evidence
        detail = _service_log_tail(home)
        if detail:
            raise ReleaseInstallSmokeError(
                f"{error}; service-log-tail={detail}"
            ) from error
        raise


def _service_log_tail(home: Path) -> str:
    """Return a bounded, single-line tail of the selected smoke service log."""
    path = home / "logs" / "service.log"
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return " ".join(content[-8192:].split())


def _duration_ms(duration_seconds: float) -> int:
    return max(0, int(duration_seconds * 1000))


def _ignore_failure(operation: Callable[[], None]) -> None:
    try:
        operation()
    except (OSError, ReleaseInstallSmokeError, subprocess.SubprocessError):
        return


class NativePackageAdapter:
    """Target-native package operations used by release runners."""

    def __init__(self, target: str, artifact: Path) -> None:
        self.target = target
        self.artifact = artifact
        self.install_root = Path(tempfile.gettempdir()) / "elfienest-release-installed"
        self.package_name: str | None = None
        if target == "win32-x64":
            self.install_root = self.install_root.with_suffix(".windows")
        elif target == "darwin-arm64" or target == "darwin-x64":
            self.install_root = Path("/Applications/ElfieNest.app")

    def install(self) -> None:
        if self.target.startswith("darwin"):
            _run_checked(
                ("sudo", "installer", "-pkg", str(self.artifact), "-target", "/")
            )
            return
        if self.target == "linux-x64":
            _run_checked(("sudo", "apt-get", "install", "--yes", str(self.artifact)))
            self.package_name = _run_checked(
                ("dpkg-deb", "--field", str(self.artifact), "Package")
            ).strip()
            return
        _run_checked(
            (
                str(self.artifact),
                "/S",
                f"/D={self.install_root}",
            )
        )

    def verify_installed(self) -> None:
        if self.target.startswith("darwin"):
            required: Sequence[Path] = (
                self.install_root / "Contents/MacOS/ElfieNest",
                self.install_root / "Contents/Resources/management-cli/ElfieNestCli",
                self.install_root / "Contents/Resources/manifest.json",
                Path("/usr/local/bin/elfienest"),
            )
        elif self.target == "linux-x64":
            required = (
                Path("/opt/ElfieNest/elfienest-gui"),
                Path("/opt/ElfieNest/resources/management-cli/ElfieNestCli"),
                Path("/opt/ElfieNest/resources/manifest.json"),
                Path("/usr/bin/elfienest-gui"),
                Path("/usr/local/bin/elfienest"),
            )
        else:
            required = (
                self.install_root / "ElfieNest.exe",
                self.install_root / "resources/management-cli/ElfieNestCli.exe",
                self.install_root / "resources/manifest.json",
                self.install_root / "bin/elfienest.cmd",
            )
        missing = tuple(str(path) for path in required if not path.exists())
        if missing:
            raise ReleaseInstallSmokeError(
                f"release-smoke-installed-files-missing paths={','.join(missing)}"
            )

    def run_cli(self, arguments: Sequence[str], environment: Mapping[str, str]) -> str:
        if self.target.startswith("darwin") or self.target == "linux-x64":
            command = ("/usr/local/bin/elfienest", *arguments)
        else:
            command = (
                "cmd.exe",
                "/d",
                "/c",
                str(self.install_root / "bin/elfienest.cmd"),
                *arguments,
            )
        return _run_checked(command, environment=environment)

    def uninstall(self) -> None:
        if self.target.startswith("darwin"):
            _run_allow_failure(("sudo", "pkgutil", "--forget", "com.elfienest.desktop"))
            if Path("/usr/local/bin/elfienest").is_symlink():
                _run_checked(("sudo", "rm", "-f", "/usr/local/bin/elfienest"))
            _run_allow_failure(("sudo", "rm", "-rf", str(self.install_root)))
            return
        if self.target == "linux-x64":
            if self.package_name:
                _run_allow_failure(("sudo", "dpkg", "--purge", self.package_name))
            _run_allow_failure(("sudo", "rm", "-f", "/usr/local/bin/elfienest"))
            return
        uninstaller = self.install_root / "Uninstall ElfieNest.exe"
        if not uninstaller.is_file():
            raise ReleaseInstallSmokeError(
                f"release-smoke-uninstaller-missing path={uninstaller}"
            )
        _run_checked((str(uninstaller), "/S"))

        launcher = self.install_root / "bin/elfienest.cmd"
        deadline = time.monotonic() + 10.0
        while launcher.exists() or launcher.is_symlink():
            if time.monotonic() >= deadline:
                raise ReleaseInstallSmokeError(
                    f"release-smoke-uninstall-timeout path={launcher}"
                )
            time.sleep(0.25)

    def verify_uninstalled(self) -> None:
        launcher = (
            Path("/usr/local/bin/elfienest")
            if self.target != "win32-x64"
            else self.install_root / "bin/elfienest.cmd"
        )
        if launcher.exists() or launcher.is_symlink():
            raise ReleaseInstallSmokeError(
                f"release-smoke-owned-launcher-remains path={launcher}"
            )


def _run_checked(
    command: Sequence[str],
    *,
    environment: Mapping[str, str] | None = None,
) -> str:
    try:
        result = subprocess.run(
            tuple(command),
            check=False,
            capture_output=True,
            text=True,
            env=None if environment is None else dict(environment),
            timeout=300,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ReleaseInstallSmokeError(
            f"release-smoke-command-failed command={command[0]} cause={error}"
        ) from error
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().replace("\n", " ")
        raise ReleaseInstallSmokeError(
            f"release-smoke-command-exit code={result.returncode} command={command[0]} detail={detail}"
        )
    return result.stdout


def _run_allow_failure(command: Sequence[str]) -> None:
    try:
        subprocess.run(
            tuple(command),
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=sorted(SUPPORTED_TARGETS))
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--evidence-output", type=Path, required=True)
    parser.add_argument("--cycles", type=int, default=1)
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_args(arguments)
    try:
        run_install_smoke(
            args.target,
            args.artifact,
            args.evidence_output,
            cycles=args.cycles,
        )
    except ReleaseInstallSmokeError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(f"release-smoke-passed target={args.target} evidence={args.evidence_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
