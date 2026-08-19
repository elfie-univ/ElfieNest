"""One-shot, observable process boundary for Godot toolchain validation.

This module is intentionally limited to developer/build-time Godot invocations.
The running Godot authority remains owned by ``infrastructure.godot.lifecycle``.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Sequence, Tuple

_ENGINE_VERSION_PATTERN = re.compile(r"(?i)\bgodot(?: engine)?\s+v(\d+\.\d+)")
_VERSION_LINE_PATTERN = re.compile(r"^v?\d+\.\d+(?:\.\d+)?(?:[._-][A-Za-z0-9]+)*$")
_SENSITIVE_ARGUMENT_PATTERN = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|authorization)"
)
_CRASH_EXIT_CODES = frozenset(
    128 + value
    for value in (signal.SIGABRT, signal.SIGBUS, signal.SIGILL, signal.SIGSEGV)
)
_HOST_UNAVAILABLE_EXIT_CODE = 126


def _extract_version(output: str) -> Optional[str]:
    for line in output.splitlines():
        engine_match = _ENGINE_VERSION_PATTERN.search(line)
        if engine_match:
            return engine_match.group(1)
        if _VERSION_LINE_PATTERN.fullmatch(line.strip()):
            version_match = re.match(r"v?(\d+\.\d+)", line.strip())
            if version_match:
                return version_match.group(1)
    return None


@dataclass(frozen=True)
class GodotExecutionResult:
    """The single process result plus enough evidence to diagnose a failure."""

    returncode: int
    stdout: str
    stderr: str
    command: Tuple[str, ...]
    project: Optional[Path]
    godot_version: Optional[str]
    parent_pid: int
    parent_command: str
    duration_ms: int
    crashed: bool
    timed_out: bool
    host_blocked: bool = False

    @property
    def exit_code(self) -> int:
        """Return a stable positive process code for callers and shell gates."""

        if self.host_blocked:
            return _HOST_UNAVAILABLE_EXIT_CODE
        if self.crashed:
            return 1
        if self.timed_out:
            return 124
        return self.returncode


def find_godot(explicit: Optional[Path] = None) -> Optional[Path]:
    """Resolve one executable without launching it."""

    candidates = []
    if explicit is not None:
        candidates.append(explicit.expanduser())
    configured = os.environ.get("GODOT_BIN", "").strip()
    if configured:
        candidates.append(Path(configured).expanduser())
    for name in ("godot4", "godot", "Godot", "godot4.exe", "godot.exe"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    if platform.system() == "Darwin":
        candidates.extend(
            (
                Path("/Applications/Godot.app/Contents/MacOS/Godot"),
                Path.home() / "Applications/Godot.app/Contents/MacOS/Godot",
                Path.home() / "Downloads/Godot.app/Contents/MacOS/Godot",
            )
        )
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.is_file() and os.access(resolved, os.X_OK):
            return resolved
    return None


def project_version(project: Path) -> Optional[str]:
    """Read the project's declared major/minor Godot version."""

    project_file = project / "project.godot"
    if not project_file.is_file():
        return None
    match = re.search(
        r'config/features=PackedStringArray\("(\d+\.\d+)"',
        project_file.read_text(encoding="utf-8"),
    )
    return match.group(1) if match else None


def godot_version(
    binary: Path,
    *,
    timeout_seconds: float = 15.0,
) -> Optional[str]:
    """Probe the executable version through the same observable process boundary."""

    result = _run_once(
        (str(binary), "--version"),
        project=None,
        godot_version=None,
        timeout_seconds=timeout_seconds,
        purpose="version-probe",
        env=None,
    )
    if result.exit_code != 0:
        return None
    return _extract_version(result.stdout + result.stderr)


def run_headless(
    binary: Path,
    project: Path,
    arguments: Sequence[str] = (),
    *,
    timeout_seconds: float = 120.0,
    godot_version: Optional[str] = None,
    purpose: str = "headless-validation",
    env: Optional[Mapping[str, str]] = None,
) -> GodotExecutionResult:
    """Run exactly one synchronous headless Godot process.

    There is deliberately no retry, background process, editor mode, or implicit
    second invocation in this function. A crash is returned as a failed result and
    its evidence is emitted before the caller receives control.
    """

    if any(argument == "--editor" for argument in arguments):
        raise ValueError("the controlled Godot runner only permits headless mode")
    resolved_project = project.expanduser().resolve()
    command = (
        str(binary),
        "--headless",
        "--path",
        str(resolved_project),
        *tuple(str(argument) for argument in arguments),
    )
    return _run_once(
        command,
        project=resolved_project,
        godot_version=godot_version,
        timeout_seconds=timeout_seconds,
        purpose=purpose,
        env=env,
    )


def forward_output(result: GodotExecutionResult) -> None:
    """Preserve the existing build-script output behavior after capture."""

    if result.stdout:
        sys.stdout.write(result.stdout)
        sys.stdout.flush()
    if result.stderr:
        sys.stderr.write(result.stderr)
        sys.stderr.flush()


def _ensure_host_execution_available() -> Optional[str]:
    """Refuse to launch Godot when the host cannot inspect its processes.

    Codex's restricted sandbox can resolve the Godot binary but cannot inspect
    the process table.  A direct build/bootstrap caller must fail closed too;
    otherwise it could bypass ``godot_guard`` and launch the native engine in
    the sandbox.  This probe never starts Godot.
    """

    command: Tuple[str, ...]
    if os.name == "nt":
        command = ("tasklist", "/fo", "csv", "/nh")
    else:
        command = ("ps", "-axo", "pid=,rss=,command=")
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        return f"cannot inspect the host process table: {error}"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        return detail or "cannot inspect the host process table"
    return None


def _run_once(
    command: Tuple[str, ...],
    *,
    project: Optional[Path],
    godot_version: Optional[str],
    timeout_seconds: float,
    purpose: str,
    env: Optional[Mapping[str, str]],
) -> GodotExecutionResult:
    parent_pid = os.getpid()
    parent_command = _parent_command()
    started = time.monotonic()

    host_error = _ensure_host_execution_available()
    if host_error is not None:
        result = GodotExecutionResult(
            returncode=_HOST_UNAVAILABLE_EXIT_CODE,
            stdout="",
            stderr=host_error,
            command=command,
            project=project,
            godot_version=godot_version,
            parent_pid=parent_pid,
            parent_command=parent_command,
            duration_ms=int((time.monotonic() - started) * 1000),
            crashed=False,
            timed_out=False,
            host_blocked=True,
        )
        _emit_evidence(result, purpose=purpose)
        print(
            "GODOT_HOST_UNAVAILABLE: no Godot process was started; "
            f"run this validation from an authorized host Terminal ({host_error}).",
            file=sys.stderr,
        )
        return result

    stdout = ""
    stderr = ""
    timed_out = False
    try:
        completed = subprocess.run(
            command,
            cwd=str(project) if project is not None else None,
            env=dict(env) if env is not None else None,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
        returncode = completed.returncode
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
    except subprocess.TimeoutExpired as error:
        returncode = 124
        timed_out = True
        stdout = _decode_output(error.stdout)
        stderr = _decode_output(error.stderr)
        timeout_message = f"Godot process timed out after {timeout_seconds:.1f}s"
        stderr = f"{stderr}\n{timeout_message}\n" if stderr else f"{timeout_message}\n"
    except OSError as error:
        returncode = 127
        stderr = str(error)

    crashed = not timed_out and (returncode < 0 or returncode in _CRASH_EXIT_CODES)
    recorded_version = godot_version or _extract_version(stdout + stderr)
    result = GodotExecutionResult(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        command=command,
        project=project,
        godot_version=recorded_version,
        parent_pid=parent_pid,
        parent_command=parent_command,
        duration_ms=int((time.monotonic() - started) * 1000),
        crashed=crashed,
        timed_out=timed_out,
    )
    _emit_evidence(result, purpose=purpose)
    return result


def _emit_evidence(result: GodotExecutionResult, *, purpose: str) -> None:
    if result.host_blocked:
        status = "blocked"
    elif result.crashed:
        status = "crashed"
    elif result.timed_out:
        status = "timed_out"
    else:
        status = "exited"
    payload = {
        "event": "godot_invocation",
        "purpose": purpose,
        "command": list(_redact_command(result.command)),
        "project": str(result.project) if result.project is not None else None,
        "godot_version": result.godot_version or "unknown",
        "parent_pid": result.parent_pid,
        "parent_command": result.parent_command,
        "exit_code": result.returncode,
        "status": status,
        "started": not result.host_blocked,
        "duration_ms": result.duration_ms,
    }
    print(
        "GODOT_INVOCATION " + json.dumps(payload, ensure_ascii=False), file=sys.stderr
    )
    if result.crashed:
        print(
            "GODOT_CRASH: one invocation failed; no retry was attempted.",
            file=sys.stderr,
        )


def _parent_command() -> str:
    command = (sys.executable, *sys.argv)
    return shlex.join(_redact_command(command))


def _redact_argument(argument: str) -> str:
    return "<redacted>" if _SENSITIVE_ARGUMENT_PATTERN.search(argument) else argument


def _redact_command(command: Sequence[str]) -> Tuple[str, ...]:
    redacted: list[str] = []
    redact_next = False
    for argument in command:
        if redact_next:
            redacted.append("<redacted>")
            redact_next = False
            continue
        redacted_argument = _redact_argument(argument)
        redacted.append(redacted_argument)
        if (
            redacted_argument == "<redacted>"
            and argument.startswith("-")
            and "=" not in argument
        ):
            redact_next = True
    return tuple(redacted)


def _decode_output(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Expose the shared version probe to shell toolchain callers."""

    parser = argparse.ArgumentParser(description="Run a controlled Godot probe.")
    parser.add_argument("command", choices=("version",))
    parser.add_argument("--binary", required=True, type=Path)
    args = parser.parse_args(argv)

    version = godot_version(args.binary)
    if version is None:
        return 1
    print(version)
    return 0


__all__ = (
    "GodotExecutionResult",
    "find_godot",
    "forward_output",
    "godot_version",
    "main",
    "project_version",
    "run_headless",
)


if __name__ == "__main__":
    raise SystemExit(main())
