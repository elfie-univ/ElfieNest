"""Authority-host adapters owned by the Runtime lifecycle boundary."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from subprocess import Popen

from app.orchestration.lifecycle.process import DefaultProcessInspector
from app.orchestration.lifecycle.runtime_supervisor import (
    AuthorityProcess,
    AuthorityStarter,
    AuthorityStopper,
)
from godot_runtime.host_contract import RuntimeHostKind
from godot_runtime.launcher import (
    AUTHORITY_ROLE_ARGUMENT,
    AuthorityLaunchError,
    AuthorityLaunchRequest,
    plan_godot_runtime_launch,
    start_godot_runtime,
    stop_godot_runtime,
)


@dataclass(frozen=True)
class AuthorityLifecycleConfig:
    """Lifecycle-owned ports and credential for one Runtime generation."""

    project_root: Path
    http_port: int
    ws_port: int
    nonce: str


def _recorded_authority_matches(pid: int, request: AuthorityLaunchRequest) -> bool:
    inspector = DefaultProcessInspector()
    try:
        plan = plan_godot_runtime_launch(request)
        cwd = inspector.cwd(pid).resolve()
        command = inspector.command(pid)
    except (AuthorityLaunchError, OSError, subprocess.SubprocessError, ValueError):
        return False
    if cwd != request.project_root.resolve() or not command:
        return False
    if plan.host_kind is RuntimeHostKind.ELECTRON_AUTHORITY:
        return AUTHORITY_ROLE_ARGUMENT in command and all(
            argument in command for argument in plan.command[1:]
        )
    if plan.host_kind is RuntimeHostKind.LINUX_DEDICATED:
        try:
            return Path(command[0]).resolve() == Path(plan.command[0]).resolve()
        except OSError:
            return False
    return False


def _stop_recorded_authority(pid: int, request: AuthorityLaunchRequest) -> None:
    """Stop an authority PID only after matching its private receipt identity."""
    inspector = DefaultProcessInspector()
    if not inspector.exists(pid) or not _recorded_authority_matches(pid, request):
        return
    try:
        process_group = os.getpgid(pid)
        if process_group != pid:
            return
        os.killpg(process_group, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    deadline = time.monotonic() + 5.0
    while inspector.exists(pid):
        if time.monotonic() >= deadline:
            if _recorded_authority_matches(pid, request):
                try:
                    os.killpg(process_group, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    return
            return
        time.sleep(0.1)


def authority_lifecycle(
    config: AuthorityLifecycleConfig,
) -> tuple[AuthorityStarter, AuthorityStopper]:
    """Bind the selected exported authority host to one Runtime Supervisor."""
    request = AuthorityLaunchRequest(
        project_root=config.project_root,
        http_port=config.http_port,
        ws_port=config.ws_port,
        nonce=config.nonce,
    )

    def start() -> Popen[bytes] | None:
        return start_godot_runtime(request)

    def stop(process: AuthorityProcess) -> None:
        if isinstance(process, Popen):
            stop_godot_runtime(process)
            return
        _stop_recorded_authority(process.pid, request)

    return start, stop
