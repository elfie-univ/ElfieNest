"""Godot authority-host process adapter for App lifecycle orchestration."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path
from subprocess import Popen

from app.orchestration.lifecycle.ports import (
    AuthorityHostConfig,
    AuthorityProcess,
    ProcessInspectorPort,
)
from app.orchestration.lifecycle.types import AuthorityHostError
from infrastructure.godot.lifecycle.host_contract import RuntimeHostKind
from infrastructure.godot.lifecycle.launcher import (
    AUTHORITY_ROLE_ARGUMENT,
    AuthorityLaunchError,
    AuthorityLaunchRequest,
    plan_godot_runtime_launch,
    start_godot_runtime,
    stop_godot_runtime,
)


class GodotAuthorityHostAdapter:
    """Bind one exported Godot authority host to a Runtime generation."""

    def __init__(
        self,
        config: AuthorityHostConfig,
        *,
        inspector: ProcessInspectorPort,
        stop_timeout_seconds: float = 1.0,
    ) -> None:
        self._config = config
        self._request = AuthorityLaunchRequest(
            project_root=config.project_root,
            http_port=config.http_port,
            ws_port=config.ws_port,
            nonce=config.nonce,
        )
        self._inspector = inspector
        self._stop_timeout_seconds = stop_timeout_seconds

    def start(self) -> Popen[bytes] | None:
        try:
            return start_godot_runtime(self._launch_request())
        except (AuthorityLaunchError, AuthorityHostError) as error:
            raise AuthorityHostError(str(error)) from error

    def _launch_request(self) -> AuthorityLaunchRequest:
        core_pid_file = self._config.core_pid_file
        if core_pid_file is None:
            return self._request
        try:
            raw_pid = core_pid_file.read_text(encoding="utf-8").strip()
            core_pid = int(raw_pid)
        except FileNotFoundError as error:
            raise AuthorityHostError("Core PID receipt is missing") from error
        except (OSError, ValueError) as error:
            raise AuthorityHostError("Core PID receipt is invalid") from error
        if core_pid <= 0:
            raise AuthorityHostError("Core PID receipt is invalid")
        return AuthorityLaunchRequest(
            project_root=self._request.project_root,
            http_port=self._request.http_port,
            ws_port=self._request.ws_port,
            nonce=self._request.nonce,
            core_pid=core_pid,
        )

    def stop(self, process: AuthorityProcess) -> None:
        if isinstance(process, Popen):
            stop_godot_runtime(process)
            return
        self._stop_recorded(process.pid)

    def _recorded_matches(self, pid: int) -> bool:
        try:
            plan = plan_godot_runtime_launch(self._request)
            cwd = self._inspector.cwd(pid).resolve()
            command = self._inspector.command(pid)
        except (AuthorityLaunchError, OSError, subprocess.SubprocessError, ValueError):
            return False
        if cwd != self._request.project_root.resolve() or not command:
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

    def _stop_recorded(self, pid: int) -> None:
        if not self._inspector.exists(pid) or not self._recorded_matches(pid):
            return
        try:
            process_group = os.getpgid(pid)
            if process_group != pid:
                return
            os.killpg(process_group, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            return
        deadline = time.monotonic() + self._stop_timeout_seconds
        while self._inspector.exists(pid):
            if time.monotonic() >= deadline:
                if self._recorded_matches(pid):
                    try:
                        os.killpg(process_group, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        return
                return
            time.sleep(0.1)
