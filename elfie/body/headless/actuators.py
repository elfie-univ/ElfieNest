"""Headless 身体的动作记录器。"""

from __future__ import annotations

from threading import Lock
from typing import List, Optional

from elfie.body.capabilities import BodyCapabilities
from elfie.body.types import BodyCommand, CommandResult, CommandStatus


class HeadlessActuators:
    def __init__(self, capabilities: BodyCapabilities):
        self.capabilities = capabilities
        self._results: List[CommandResult] = []
        self._lock = Lock()

    def execute(self, command: BodyCommand) -> CommandResult:
        if not self.capabilities.supports_action(command.action):
            result = CommandResult(
                command_id=command.command_id,
                action=command.action,
                status=CommandStatus.REJECTED,
                error=f"HeadlessBody 不支持动作: {command.action}",
            )
        else:
            result = CommandResult(
                command_id=command.command_id,
                action=command.action,
                status=CommandStatus.COMPLETED,
                output={"recorded": True, **dict(command.parameters)},
            )
        with self._lock:
            self._results.append(result)
        return result

    @property
    def last_result(self) -> Optional[CommandResult]:
        with self._lock:
            return self._results[-1] if self._results else None

    @property
    def results(self) -> List[CommandResult]:
        with self._lock:
            return list(self._results)
