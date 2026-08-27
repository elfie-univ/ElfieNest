#!/usr/bin/env python3
"""Run the native install, upgrade, startup, stop, and uninstall smoke gate.

This is deliberately a release-runner tool, not a product installer.  It only
removes files that the native package owns and keeps the user's ``ELFIE_HOME``
outside the uninstall path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping, Protocol, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from infrastructure.platform.diagnostics import redact_diagnostic_text
from infrastructure.platform.lifecycle.process import DefaultProcessInspector

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
    "product_journey": 300_000,
}
SCRIPTED_MODEL_READY_TIMEOUT_SECONDS = 30.0
WINDOWS_UNINSTALL_CLEANUP_TIMEOUT_SECONDS = 30.0
GLOBAL_CLI_LAUNCHER = Path("/usr/local/bin/elfienest")
MAC_INSTALL_ROOT = Path("/Applications/ElfieNest.app")
LINUX_INSTALL_ROOT = Path("/opt/ElfieNest")
LINUX_GUI_LAUNCHER = Path("/usr/bin/elfienest-gui")


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
    product_journey: bool = False,
    candidate_sha: str | None = None,
    recovery_matrix: bool = False,
    viewer_check: bool = False,
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
    if candidate_sha is not None and not re.fullmatch(
        r"[0-9a-fA-F]{40}", candidate_sha
    ):
        raise ReleaseInstallSmokeError("release-smoke-candidate-sha-invalid")

    owned_home = smoke_home is None
    temporary_home = (
        tempfile.TemporaryDirectory(prefix="elfienest-release-smoke-")
        if owned_home
        else None
    )
    home = smoke_home or Path(temporary_home.name)  # type: ignore[union-attr]
    scripted_model: _ScriptedModelProcess | None = None
    native: SmokeAdapter | None = None
    try:
        native = adapter or NativePackageAdapter(target, artifact)
        # A rerun must start from a package-owned clean surface.  Native
        # uninstall implementations are intentionally idempotent here.
        _ignore_failure(native.uninstall)
        scripted_model_info: MutableMapping[str, object] = {}
        if product_journey:
            scripted_model = _start_scripted_model_server(home)
            scripted_model_info.update(
                {
                    "pid": scripted_model.pid,
                    "endpoint": scripted_model.endpoint,
                }
            )
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
            ready_status = _wait_for_state(
                native,
                environment,
                expected={"world_ready"},
                monotonic=monotonic,
                sleeper=sleeper,
                timeout_seconds=timeout_seconds,
            )
            reached_state = str(ready_status["state"])
            controller_pid = _desktop_controller_pid(home)
            owned_pids = _owned_runtime_pids(ready_status, controller_pid)
            phases.append(
                SmokePhase(
                    "health",
                    _duration_ms(monotonic() - health_started),
                    PHASE_BUDGETS_MS["health"],
                )
            )
            recovery = None
            if recovery_matrix:
                recovery = _verify_duplicate_start(
                    ready_status,
                    native=native,
                    environment=environment,
                    home=home,
                    monotonic=monotonic,
                    sleeper=sleeper,
                    timeout_seconds=timeout_seconds,
                )
            viewer = None
            if viewer_check and cycle == 1:
                viewer = _verify_installed_viewer(
                    native,
                    environment=environment,
                    home=home,
                    timeout_seconds=min(timeout_seconds, 60.0),
                )
            journey = None
            if scripted_model is not None:
                journey_started = monotonic()
                journey = _run_product_journey(
                    ready_status,
                    home=home,
                    model_endpoint=scripted_model.endpoint,
                    mode="initial" if cycle == 1 else "resume",
                    native=native,
                    environment=environment,
                    timeout_seconds=min(timeout_seconds, 120.0),
                )
                phases.append(
                    SmokePhase(
                        "product_journey",
                        _duration_ms(monotonic() - journey_started),
                        PHASE_BUDGETS_MS["product_journey"],
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
            _wait_for_owned_processes_stopped(
                owned_pids,
                home=home,
                monotonic=monotonic,
                sleeper=sleeper,
                timeout_seconds=min(timeout_seconds, 10.0),
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
                    "reached_state": reached_state,
                    "desktop_controller_pid": controller_pid,
                    "verified_stopped_pids": list(owned_pids),
                    **({"recovery": recovery} if recovery is not None else {}),
                    **({"viewer": viewer} if viewer is not None else {}),
                    **({"product_journey": journey} if journey is not None else {}),
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

        if scripted_model is not None:
            scripted_model_info["summary"] = _stop_scripted_model_server(scripted_model)
            scripted_model = None

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
            "schema_version": 2,
            "target": target,
            "artifact": artifact.name,
            "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            "source_commit": candidate_sha,
            "runner": _runner_identity(),
            "required_state": "world_ready",
            "cycles": cycle_records,
            "phases": phase_payloads,
            "result": "passed",
        }
        if scripted_model_info:
            evidence["scripted_model"] = dict(scripted_model_info)
        if any(not bool(phase["within_budget"]) for phase in phase_payloads):
            raise ReleaseInstallSmokeError("release-smoke-phase-budget-exceeded")
        evidence_output.parent.mkdir(parents=True, exist_ok=True)
        evidence_output.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return evidence
    except Exception as error:
        if smoke_home is not None and native is not None:
            _write_failure_diagnostics(home, target, error, native)
        raise
    finally:
        if scripted_model is not None:
            _stop_scripted_model_server(scripted_model)
        if temporary_home is not None:
            temporary_home.cleanup()


@dataclass
class _ScriptedModelProcess:
    process: subprocess.Popen
    endpoint: str
    ready_file: Path
    summary_file: Path

    @property
    def pid(self) -> int:
        return int(self.process.pid or 0)


def _start_scripted_model_server(home: Path) -> _ScriptedModelProcess:
    """Start the repository-owned deterministic model boundary on loopback."""
    script = Path(__file__).with_name("scripted_model_server.py")
    if not script.is_file():
        raise ReleaseInstallSmokeError("release-smoke-scripted-model-missing")
    runtime_dir = home / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    ready_file = runtime_dir / "scripted-model-ready.json"
    summary_file = runtime_dir / "scripted-model-summary.json"
    process = subprocess.Popen(
        (
            sys.executable,
            str(script),
            "--ready-file",
            str(ready_file),
            "--summary-file",
            str(summary_file),
        ),
        cwd=str(Path.cwd()),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + SCRIPTED_MODEL_READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ReleaseInstallSmokeError("release-smoke-scripted-model-exited")
        try:
            payload = json.loads(ready_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            time.sleep(0.1)
            continue
        endpoint = payload.get("endpoint") if isinstance(payload, dict) else None
        if isinstance(endpoint, str) and _is_loopback_model_endpoint(endpoint):
            return _ScriptedModelProcess(process, endpoint, ready_file, summary_file)
        time.sleep(0.1)
    _stop_scripted_model_server(
        _ScriptedModelProcess(process, "", ready_file, summary_file)
    )
    raise ReleaseInstallSmokeError("release-smoke-scripted-model-timeout")


def _stop_scripted_model_server(server: _ScriptedModelProcess) -> dict[str, Any]:
    """Stop only the test-owned model process and read its redacted summary."""
    if server.process.poll() is None:
        server.process.terminate()
        try:
            server.process.wait(timeout=10)
        except subprocess.TimeoutExpired as error:
            server.process.kill()
            try:
                server.process.wait(timeout=5)
            except subprocess.TimeoutExpired as kill_error:
                raise ReleaseInstallSmokeError(
                    "release-smoke-scripted-model-stop-timeout"
                ) from kill_error
            raise ReleaseInstallSmokeError(
                "release-smoke-scripted-model-stop-forced"
            ) from error
    try:
        payload = json.loads(server.summary_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"result": "summary_missing"}
    return payload if isinstance(payload, dict) else {"result": "summary_invalid"}


def _is_loopback_model_endpoint(endpoint: str) -> bool:
    parsed = urllib.parse.urlsplit(endpoint)
    return (
        parsed.scheme == "http"
        and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        and parsed.port is not None
        and 1 <= parsed.port <= 65535
        and parsed.path == "/v1"
    )


def _run_product_journey(
    ready_status: Mapping[str, object],
    *,
    home: Path,
    model_endpoint: str,
    mode: str,
    native: SmokeAdapter,
    environment: Mapping[str, str],
    timeout_seconds: float,
) -> dict[str, Any]:
    """Run Setup/adoption/chat through the installed Controller API."""
    from scripts.internal.release.installed_product_journey import (
        InstalledJourneyConfig,
        JourneyFailure,
        run_installed_product_journey,
    )

    base_url = _installed_http_base_url(ready_status)

    def read_status() -> Mapping[str, Any]:
        return _parse_status(native.run_cli(("status", "--json"), environment))

    try:
        return run_installed_product_journey(
            InstalledJourneyConfig(
                base_url=base_url,
                data_home=home.resolve(),
                model_endpoint=model_endpoint,
                timeout_seconds=timeout_seconds,
                expected_source_root=Path.cwd().resolve(),
            ),
            mode=mode,
            status_reader=read_status,
        )
    except JourneyFailure as error:
        raise ReleaseInstallSmokeError(
            "release-smoke-product-journey-failed "
            f"phase={error.phase} code={error.code}"
            + (f" detail={error.detail}" if error.detail else "")
        ) from error


def _installed_http_base_url(status: Mapping[str, object]) -> str:
    endpoints = status.get("endpoints")
    if not isinstance(endpoints, list):
        raise ReleaseInstallSmokeError("release-smoke-http-endpoint-missing")
    for endpoint in endpoints:
        if not isinstance(endpoint, dict) or endpoint.get("name") != "http":
            continue
        scheme = endpoint.get("scheme")
        host = endpoint.get("host")
        port = endpoint.get("port")
        if (
            scheme in {"http", "https"}
            and host in {"127.0.0.1", "localhost", "::1"}
            and isinstance(port, int)
            and 1 <= port <= 65535
        ):
            rendered_host = f"[{host}]" if host == "::1" else str(host)
            return f"{scheme}://{rendered_host}:{port}"
    raise ReleaseInstallSmokeError("release-smoke-http-endpoint-not-loopback")


def _verify_duplicate_start(
    ready_status: Mapping[str, object],
    *,
    native: SmokeAdapter,
    environment: Mapping[str, str],
    home: Path,
    monotonic: Callable[[], float],
    sleeper: Callable[[float], None],
    timeout_seconds: float,
) -> dict[str, object]:
    """Prove an attached start does not create a second authority generation."""
    generation = ready_status.get("generation")
    if not isinstance(generation, int) or generation < 0:
        raise ReleaseInstallSmokeError("release-smoke-recovery-generation-missing")
    controller_pid = _desktop_controller_pid(home)
    before = _owned_runtime_pids(ready_status, controller_pid)
    native.run_cli(("start", "--json", "--loopback"), environment)
    after_status = _wait_for_state(
        native,
        environment,
        expected={"world_ready"},
        monotonic=monotonic,
        sleeper=sleeper,
        timeout_seconds=timeout_seconds,
    )
    after_generation = after_status.get("generation")
    if after_generation != generation:
        raise ReleaseInstallSmokeError("release-smoke-recovery-generation-changed")
    after_controller_pid = _desktop_controller_pid(home)
    after = _owned_runtime_pids(after_status, after_controller_pid)
    if after_controller_pid != controller_pid or after != before:
        raise ReleaseInstallSmokeError("release-smoke-recovery-duplicate-authority")
    return {
        "same_generation": True,
        "generation": generation,
        "owned_pids": list(before),
    }


def _verify_installed_viewer(
    native: SmokeAdapter,
    *,
    environment: Mapping[str, str],
    home: Path,
    timeout_seconds: float,
) -> dict[str, object]:
    """Activate the packaged Viewer and require a rendered management page marker."""
    launch = getattr(native, "launch_gui", None)
    diagnostics_path = getattr(native, "desktop_diagnostics_path", None)
    if not callable(launch) or not callable(diagnostics_path):
        raise ReleaseInstallSmokeError("release-smoke-viewer-launch-unavailable")
    process = launch(environment)
    marker_path = diagnostics_path(home)
    deadline = time.monotonic() + timeout_seconds
    try:
        while time.monotonic() < deadline:
            if _diagnostic_has_event(marker_path, "management_page_ready"):
                return {"management_page_ready": True}
            time.sleep(0.25)
        detail = _diagnostic_file_tail(marker_path)
        suffix = f" diagnostics={detail}" if detail else ""
        raise ReleaseInstallSmokeError(f"release-smoke-viewer-ready-timeout{suffix}")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def _diagnostic_has_event(path: Path, event_name: str) -> bool:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return False
    for line in lines:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("event") == event_name:
            return True
    return False


def _smoke_environment(home: Path) -> MutableMapping[str, str]:
    environment = dict(os.environ)
    desktop_app_data = home / "desktop-app-data"
    environment.update(
        {
            "ELFIE_HOME": str(home.resolve()),
            "HOME": str(home.resolve()),
            "USERPROFILE": str(home.resolve()),
            "APPDATA": str((home / "AppData" / "Roaming").resolve()),
            "LOCALAPPDATA": str((home / "AppData" / "Local").resolve()),
            "XDG_CONFIG_HOME": str((home / ".config").resolve()),
            "XDG_DATA_HOME": str((home / ".local" / "share").resolve()),
            # Electron normally chooses a native OS app-data directory.  A
            # release smoke run must keep Controller IPC and diagnostics in
            # its isolated smoke home so the readiness marker is collected
            # deterministically on every runner.
            "ELFIENEST_DESKTOP_APP_DATA": str(desktop_app_data.resolve()),
            "ELFIENEST_RUNTIME_MODE": "release",
            # GitHub macOS runners can expose an unstable headless GPU/WebGL
            # stack.  The packaged smoke test must exercise the real Electron
            # authority without making hardware acceleration a prerequisite.
            "ELFIENEST_RELEASE_SMOKE": "1",
        }
    )
    return environment


def _runner_identity() -> dict[str, str]:
    """Capture only non-secret CI host identity for evidence binding."""
    names = ("RUNNER_OS", "RUNNER_ARCH", "ImageOS", "ImageVersion")
    return {name: os.environ[name] for name in names if os.environ.get(name)}


def _wait_for_state(
    adapter: SmokeAdapter,
    environment: Mapping[str, str],
    *,
    expected: set[str],
    monotonic: Callable[[], float],
    sleeper: Callable[[float], None],
    timeout_seconds: float,
) -> Mapping[str, object]:
    deadline = monotonic() + timeout_seconds
    last_state = "unknown"
    while True:
        payload = _parse_status(adapter.run_cli(("status", "--json"), environment))
        state = payload.get("state")
        if isinstance(state, str):
            last_state = state
            if state in expected:
                return payload
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


def _desktop_controller_pid(home: Path) -> int:
    receipt = home / "runtime" / "desktop.pid"
    try:
        pid = int(receipt.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, OSError, ValueError) as error:
        raise ReleaseInstallSmokeError(
            f"release-smoke-desktop-controller-receipt-missing path={receipt}"
        ) from error
    if pid <= 0:
        raise ReleaseInstallSmokeError(
            f"release-smoke-desktop-controller-receipt-invalid path={receipt}"
        )
    return pid


def _owned_runtime_pids(
    ready_status: Mapping[str, object],
    controller_pid: int,
) -> tuple[int, ...]:
    pids = {controller_pid}
    required = {"core", "godot_authority"}
    observed: set[str] = set()
    components = ready_status.get("components")
    if isinstance(components, list):
        for component in components:
            if not isinstance(component, dict):
                continue
            name = component.get("name")
            pid = component.get("pid")
            if isinstance(name, str) and isinstance(pid, int) and pid > 0:
                observed.add(name)
                pids.add(pid)
    missing = sorted(required - observed)
    if missing:
        raise ReleaseInstallSmokeError(
            "release-smoke-component-pids-missing names=" + ",".join(missing)
        )
    return tuple(sorted(pids))


def _wait_for_owned_processes_stopped(
    pids: Sequence[int],
    *,
    home: Path,
    monotonic: Callable[[], float],
    sleeper: Callable[[float], None],
    timeout_seconds: float,
) -> None:
    deadline = monotonic() + timeout_seconds
    receipt = home / "runtime" / "desktop.pid"
    while True:
        remaining = tuple(pid for pid in pids if _pid_exists(pid))
        if not remaining and not receipt.exists():
            return
        if monotonic() >= deadline:
            details = ",".join(str(pid) for pid in remaining) or "receipt"
            raise ReleaseInstallSmokeError(
                "release-smoke-owned-processes-remain "
                f"pids={details} desktop_receipt={receipt.exists()}"
            )
        sleeper(0.25)


def _pid_exists(pid: int) -> bool:
    return DefaultProcessInspector().exists(pid)


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
        detail = _service_log_tail(home, native=native)
        if detail:
            raise ReleaseInstallSmokeError(
                f"{error}; service-log-tail={detail}"
            ) from error
        raise


def _service_log_tail(home: Path, *, native: SmokeAdapter | None = None) -> str:
    """Return a bounded, redacted tail across startup-owned diagnostic logs."""
    log_dir = home / "logs"
    fragments: list[tuple[str, str]] = []
    for name in (
        "service.log",
        "core-events.jsonl",
        "service-console.log",
        "authority.log",
        "authority-console.log",
        "desktop-controller-console.log",
        "desktop-console.log",
    ):
        normalized = _diagnostic_file_tail(log_dir / name)
        if normalized:
            fragments.append((name, normalized))
    diagnostics_path = getattr(native, "desktop_diagnostics_path", None)
    if callable(diagnostics_path):
        desktop_path = diagnostics_path(home)
        desktop_tail = _diagnostic_file_tail(desktop_path)
        if desktop_tail:
            fragments.append(("desktop-events.jsonl", desktop_tail))
    if not fragments:
        return ""
    if len(fragments) == 1:
        combined = fragments[0][1]
    else:
        combined = " | ".join(f"{name}:{content}" for name, content in fragments)
    return redact_diagnostic_text(combined[-8192:])


def _diagnostic_file_tail(path: Path) -> str:
    """Read a bounded, whitespace-normalized and secret-redacted log tail."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return redact_diagnostic_text(" ".join(content[-4096:].split()))


def _write_failure_diagnostics(
    home: Path,
    target: str,
    error: Exception,
    native: SmokeAdapter,
) -> None:
    """Persist only bounded, redacted failure evidence for CI artifact upload."""
    payload = {
        "schema_version": 1,
        "target": target,
        "result": "failed",
        "error": redact_diagnostic_text(str(error))[-4096:],
        "logs": _service_log_tail(home, native=native),
        "runtime_snapshot": _diagnostic_file_tail(home / "runtime" / "runtime.json"),
        "lifecycle_history": _diagnostic_file_tail(
            home / "logs" / "lifecycle-history.jsonl"
        ),
    }
    try:
        home.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = home / "failure-diagnostics.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if os.name != "nt":
            path.chmod(0o600)
    except OSError:
        return


def _duration_ms(duration_seconds: float) -> int:
    return max(0, int(duration_seconds * 1000))


def _ignore_failure(operation: Callable[[], None]) -> None:
    try:
        operation()
    except (OSError, ReleaseInstallSmokeError, subprocess.SubprocessError):
        return


def _is_owned_symlink(launcher: Path, expected_target: Path) -> bool:
    """Return whether a launcher is the exact symlink created by our package."""
    if not launcher.is_symlink():
        return False
    try:
        return os.readlink(launcher) == str(expected_target)
    except OSError:
        return False


class NativePackageAdapter:
    """Target-native package operations used by release runners."""

    def __init__(self, target: str, artifact: Path) -> None:
        self.target = target
        self.artifact = artifact
        self.install_root = Path(tempfile.gettempdir()) / "elfienest-release-installed"
        self.package_name: str | None = None
        if target == "win32-x64":
            self.install_root = self.install_root.with_suffix(".windows")
        elif target == "linux-x64":
            # Debian installs the GUI and its resources under the fixed
            # system root.  Keep all native operations (including the real
            # Viewer launch) pointed at the same installed tree that
            # verify_installed() checks.
            self.install_root = LINUX_INSTALL_ROOT
        elif target == "darwin-arm64" or target == "darwin-x64":
            self.install_root = MAC_INSTALL_ROOT

    def _linux_package_name(self) -> str:
        if self.package_name is None:
            self.package_name = _run_checked(
                ("dpkg-deb", "--field", str(self.artifact), "Package")
            ).strip()
        if not self.package_name:
            raise ReleaseInstallSmokeError("release-smoke-linux-package-name-missing")
        return self.package_name

    def install(self) -> None:
        if self.target.startswith("darwin"):
            _run_checked(
                ("sudo", "installer", "-pkg", str(self.artifact), "-target", "/")
            )
            return
        if self.target == "linux-x64":
            self._linux_package_name()
            _run_checked(("sudo", "apt-get", "install", "--yes", str(self.artifact)))
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
                LINUX_INSTALL_ROOT / "elfienest-gui",
                LINUX_INSTALL_ROOT / "resources/management-cli/ElfieNestCli",
                LINUX_INSTALL_ROOT / "resources/manifest.json",
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
        expected_launchers: Sequence[tuple[Path, Path]]
        if self.target.startswith("darwin"):
            expected_launchers = (
                (
                    GLOBAL_CLI_LAUNCHER,
                    self.install_root
                    / "Contents/Resources/management-cli/ElfieNestCli",
                ),
            )
        elif self.target == "linux-x64":
            expected_launchers = (
                (LINUX_GUI_LAUNCHER, LINUX_INSTALL_ROOT / "elfienest-gui"),
                (
                    GLOBAL_CLI_LAUNCHER,
                    LINUX_INSTALL_ROOT / "resources/management-cli/ElfieNestCli",
                ),
            )
        else:
            expected_launchers = ()
        wrong_launchers = tuple(
            str(launcher)
            for launcher, target in expected_launchers
            if not _is_owned_symlink(launcher, target)
        )
        if wrong_launchers:
            raise ReleaseInstallSmokeError(
                "release-smoke-owned-launcher-invalid "
                f"paths={','.join(wrong_launchers)}"
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

    def launch_gui(self, environment: Mapping[str, str]) -> subprocess.Popen:
        if self.target.startswith("darwin"):
            command = (str(self.install_root / "Contents/MacOS/ElfieNest"),)
        elif self.target == "linux-x64":
            command = (str(self.install_root / "elfienest-gui"),)
        else:
            command = (str(self.install_root / "ElfieNest.exe"),)
        smoke_home = environment.get("ELFIE_HOME")
        if smoke_home:
            console_path = Path(smoke_home) / "logs" / "desktop-console.log"
            try:
                console_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                with console_path.open("ab") as console:
                    return subprocess.Popen(
                        command,
                        env=dict(environment),
                        stdout=console,
                        stderr=subprocess.STDOUT,
                    )
            except OSError as error:
                raise ReleaseInstallSmokeError(
                    "release-smoke-viewer-launch-failed"
                ) from error
        try:
            return subprocess.Popen(
                command,
                env=dict(environment),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as error:
            raise ReleaseInstallSmokeError(
                "release-smoke-viewer-launch-failed"
            ) from error

    def desktop_diagnostics_path(self, home: Path) -> Path:
        app_data = home / "desktop-app-data"
        return (
            app_data
            / "ElfieNest"
            / "elfienest.desktop-ui"
            / "logs"
            / "desktop-events.jsonl"
        )

    def uninstall(self) -> None:
        if self.target.startswith("darwin"):
            _run_allow_failure(("sudo", "pkgutil", "--forget", "com.elfienest.desktop"))
            cli_target = (
                self.install_root / "Contents/Resources/management-cli/ElfieNestCli"
            )
            if _is_owned_symlink(GLOBAL_CLI_LAUNCHER, cli_target):
                _run_checked(("sudo", "rm", "-f", str(GLOBAL_CLI_LAUNCHER)))
            _run_allow_failure(("sudo", "rm", "-rf", str(self.install_root)))
            return
        if self.target == "linux-x64":
            _run_allow_failure(("sudo", "dpkg", "--purge", self._linux_package_name()))
            return
        uninstaller = self.install_root / "Uninstall ElfieNest.exe"
        if not uninstaller.is_file():
            raise ReleaseInstallSmokeError(
                f"release-smoke-uninstaller-missing path={uninstaller}"
            )
        _run_checked((str(uninstaller), "/S"))

        launcher = self.install_root / "bin/elfienest.cmd"
        deadline = time.monotonic() + WINDOWS_UNINSTALL_CLEANUP_TIMEOUT_SECONDS
        while launcher.exists() or launcher.is_symlink() or self.install_root.exists():
            if time.monotonic() >= deadline:
                remaining: list[str] = []
                if launcher.exists() or launcher.is_symlink():
                    remaining.append(str(launcher))
                if self.install_root.exists():
                    remaining.append(str(self.install_root))
                raise ReleaseInstallSmokeError(
                    f"release-smoke-uninstall-timeout paths={','.join(remaining)}"
                )
            time.sleep(0.25)

    def verify_uninstalled(self) -> None:
        owned_launchers: Sequence[tuple[Path, Path]]
        owned_roots: Sequence[Path]
        if self.target.startswith("darwin"):
            owned_launchers = (
                (
                    GLOBAL_CLI_LAUNCHER,
                    self.install_root
                    / "Contents/Resources/management-cli/ElfieNestCli",
                ),
            )
            owned_roots = (self.install_root,)
        elif self.target == "linux-x64":
            owned_launchers = (
                (LINUX_GUI_LAUNCHER, LINUX_INSTALL_ROOT / "elfienest-gui"),
                (
                    GLOBAL_CLI_LAUNCHER,
                    LINUX_INSTALL_ROOT / "resources/management-cli/ElfieNestCli",
                ),
            )
            owned_roots = (LINUX_INSTALL_ROOT,)
        else:
            owned_launchers = ()
            owned_roots = (self.install_root,)
        remaining = tuple(
            str(launcher)
            for launcher, target in owned_launchers
            if _is_owned_symlink(launcher, target)
        ) + tuple(str(root) for root in owned_roots if root.exists())
        if remaining:
            raise ReleaseInstallSmokeError(
                f"release-smoke-owned-files-remain paths={','.join(remaining)}"
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
