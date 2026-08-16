"""Launch exactly one exported Godot authority host for a Runtime generation."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Final, Mapping, Optional, Protocol
from urllib.parse import urlencode

from infrastructure.godot.lifecycle.host_contract import (
    RuntimeHostKind,
    RuntimeHostSelectionContext,
    select_platform_authority_host,
)

AUTHORITY_ROLE_ARGUMENT: Final = "--elfienest-role=godot-authority"
RUNTIME_HOST_ENV: Final = "ELFIENEST_RUNTIME_HOST"
AUTHORITY_STOP_GRACE_SECONDS: Final = 1.0
AUTHORITY_STOP_FORCE_GRACE_SECONDS: Final = 1.0


class AuthorityLaunchFailureKind(str, Enum):
    """Stable machine-readable authority launch failure classes."""

    INVALID_OVERRIDE = "invalid_override"
    MISSING_ARTIFACT = "missing_artifact"
    PROCESS_LAUNCH = "process_launch"


@dataclass(frozen=True)
class AuthorityLaunchError(Exception):
    """Diagnostic authority launch failure propagated to lifecycle callers."""

    kind: AuthorityLaunchFailureKind
    detail: str
    target: Optional[Path] = None

    def __str__(self) -> str:
        target = f" ({self.target})" if self.target is not None else ""
        return f"{self.kind.value}: {self.detail}{target}"


@dataclass(frozen=True)
class AuthorityLaunchRequest:
    """Internal credentials and ports for one authority generation."""

    project_root: Path
    http_port: int
    ws_port: int
    nonce: str
    core_pid: Optional[int] = None


@dataclass(frozen=True)
class AuthorityLaunchPlan:
    """Resolved command and private environment for one owned child process."""

    host_kind: RuntimeHostKind
    command: tuple[str, ...]
    cwd: Path
    environment: tuple[tuple[str, str], ...]


class OwnedRuntimeProcess(Protocol):
    """Only the exact child handle created by this launcher may be stopped."""

    pid: int

    def poll(self) -> Optional[int]: ...

    def terminate(self) -> None: ...

    def wait(self, timeout: float) -> int: ...

    def kill(self) -> None: ...


def _executable(path: Path) -> Optional[Path]:
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        return None
    if resolved.is_file() and os.access(resolved, os.X_OK):
        return resolved
    return None


def find_runtime_binary(
    project_root: Path,
    environment: Optional[Mapping[str, str]] = None,
) -> Optional[Path]:
    """Find only an exported Dedicated/native Runtime, never a Godot editor."""
    values = os.environ if environment is None else environment
    configured = values.get("ELFIENEST_RUNTIME_BIN", "").strip()
    candidates = [Path(configured)] if configured else []
    candidates.extend(
        (
            project_root / "build/components/godot-linux-dedicated/ElfieNestRuntime",
            project_root / ".elfienest/runtime/ElfieNestRuntime",
            project_root / "runtime/bin/ElfieNestRuntime",
            project_root / "dist/ElfieNestRuntime",
        )
    )
    for candidate in candidates:
        executable = _executable(candidate)
        if executable is not None:
            return executable
    return None


def _electron_command(
    project_root: Path,
    environment: Mapping[str, str],
) -> Optional[tuple[str, ...]]:
    configured = environment.get("ELFIENEST_DESKTOP_BIN", "").strip()
    if configured:
        packaged = _executable(Path(configured))
        if packaged is not None:
            return (str(packaged), AUTHORITY_ROLE_ARGUMENT)
    electron = _executable(
        project_root / "app/interfaces/desktop/node_modules/.bin/electron"
    )
    desktop_host = project_root / "app/bootstrap/desktop_host/host_main.mjs"
    try:
        resolved_host = desktop_host.resolve()
    except OSError:
        return None
    if electron is None or not resolved_host.is_file():
        return None
    return (str(electron), str(resolved_host), AUTHORITY_ROLE_ARGUMENT)


def _requested_host(environment: Mapping[str, str]) -> Optional[RuntimeHostKind]:
    raw = environment.get(RUNTIME_HOST_ENV, "").strip()
    if not raw:
        return None
    if raw == "electron":
        return RuntimeHostKind.ELECTRON_AUTHORITY
    if raw in {"linux-dedicated", "dedicated"}:
        return RuntimeHostKind.LINUX_DEDICATED
    raise AuthorityLaunchError(
        AuthorityLaunchFailureKind.INVALID_OVERRIDE,
        f"unsupported {RUNTIME_HOST_ENV}={raw!r}",
    )


def _authority_url(request: AuthorityLaunchRequest) -> str:
    query = urlencode(
        {
            "mode": "authority",
            "ws": f"ws://127.0.0.1:{request.ws_port}",
            "nonce": request.nonce,
        }
    )
    return f"http://127.0.0.1:{request.http_port}/runtime/godot/elfienest.html?{query}"


def _authority_namespace(project_root: Path) -> str:
    """Scope Electron's single-instance lock to one resolved checkout."""
    digest = sha256(str(project_root.resolve()).encode("utf-8")).hexdigest()[:16]
    return f"elfienest.godot-authority.{digest}"


def plan_godot_runtime_launch(
    request: AuthorityLaunchRequest,
    *,
    platform_name: Optional[str] = None,
    environment: Optional[Mapping[str, str]] = None,
) -> AuthorityLaunchPlan:
    """Resolve the authority host without spawning a child process."""
    values = os.environ if environment is None else environment
    root = request.project_root.resolve()
    electron_command = _electron_command(root, values)
    host = select_platform_authority_host(
        RuntimeHostSelectionContext(
            platform_name=sys.platform if platform_name is None else platform_name,
            display_available=bool(
                values.get("DISPLAY", "") or values.get("WAYLAND_DISPLAY", "")
            ),
            electron_available=electron_command is not None,
            dedicated_override=bool(values.get("ELFIENEST_RUNTIME_BIN", "").strip()),
            requested_kind=_requested_host(values),
        )
    )
    additions: tuple[tuple[str, str], ...]
    command: tuple[str, ...]
    if host.kind is RuntimeHostKind.ELECTRON_AUTHORITY:
        if electron_command is None:
            raise AuthorityLaunchError(
                AuthorityLaunchFailureKind.MISSING_ARTIFACT,
                "Electron authority host is not built or executable",
            )
        additions = (
            ("ELFIENEST_PROJECT_ROOT", str(root)),
            ("ELFIENEST_GODOT_URL", _authority_url(request)),
            ("ELFIENEST_AUTHORITY_NAMESPACE", _authority_namespace(root)),
        )
        command = electron_command
    elif host.kind is RuntimeHostKind.LINUX_DEDICATED:
        binary = find_runtime_binary(root, values)
        if binary is None:
            configured = values.get("ELFIENEST_RUNTIME_BIN", "").strip()
            target = Path(configured).expanduser() if configured else None
            raise AuthorityLaunchError(
                AuthorityLaunchFailureKind.MISSING_ARTIFACT,
                "Dedicated authority Runtime is not built or executable",
                target,
            )
        additions = (
            ("ELFIENEST_GODOT_MODE", "authority"),
            ("ELFIENEST_GODOT_WS", f"ws://127.0.0.1:{request.ws_port}"),
            ("ELFIENEST_GODOT_NONCE", request.nonce),
        )
        command = (str(binary),)
    else:
        raise AuthorityLaunchError(
            AuthorityLaunchFailureKind.INVALID_OVERRIDE,
            "Web authority requires the managed Electron host",
        )
    if request.core_pid is not None:
        additions = (*additions, ("ELFIENEST_CORE_PID", str(request.core_pid)))
    return AuthorityLaunchPlan(host.kind, command, root, additions)


def start_godot_runtime(
    request: AuthorityLaunchRequest,
    *,
    platform_name: Optional[str] = None,
    environment: Optional[Mapping[str, str]] = None,
) -> Optional[subprocess.Popen[bytes]]:
    """Start one owned hidden Electron or Dedicated authority process."""
    values = os.environ if environment is None else environment
    if values.get("ELFIENEST_DISABLE_GODOT_AUTOSTART") == "1":
        return None
    plan = plan_godot_runtime_launch(
        request,
        platform_name=platform_name,
        environment=values,
    )
    child_environment = dict(values)
    child_environment.update(plan.environment)
    try:
        return subprocess.Popen(
            plan.command,
            cwd=str(plan.cwd),
            env=child_environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as error:
        raise AuthorityLaunchError(
            AuthorityLaunchFailureKind.PROCESS_LAUNCH,
            str(error),
            Path(plan.command[0]),
        ) from error


def stop_godot_runtime(process: Optional[OwnedRuntimeProcess]) -> None:
    """Stop only the exact authority child handle owned by this Supervisor."""
    if process is None or process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.terminate()
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=AUTHORITY_STOP_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            process.kill()
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=AUTHORITY_STOP_FORCE_GRACE_SECONDS)
    except (OSError, ProcessLookupError):
        return
