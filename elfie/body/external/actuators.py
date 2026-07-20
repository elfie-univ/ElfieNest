"""外部身体动作命令的能力校验和传输。"""

from __future__ import annotations

from typing import Optional

from elfie.body.capabilities import BodyCapabilities
from elfie.body.external.transport import ExternalTransport
from elfie.body.types import BodyCommand, CommandResult, CommandStatus


class ExternalActuators:
    def __init__(
        self,
        capabilities: BodyCapabilities,
        transport: ExternalTransport,
    ) -> None:
        self.capabilities = capabilities
        self.transport = transport
        self.connected = False
        self._last_result: Optional[CommandResult] = None

    def execute(self, command: BodyCommand) -> CommandResult:
        if not self.connected:
            return self._remember(
                CommandResult(
                    command_id=command.command_id,
                    action=command.action,
                    status=CommandStatus.REJECTED,
                    error="ExternalBody 尚未连接",
                )
            )
        if not self.capabilities.supports_action(command.action):
            return self._remember(
                CommandResult(
                    command_id=command.command_id,
                    action=command.action,
                    status=CommandStatus.REJECTED,
                    error=f"ExternalBody 不支持动作: {command.action}",
                )
            )
        try:
            result = self.transport.send_command(command)
        except Exception as exc:
            return self._remember(
                CommandResult(
                    command_id=command.command_id,
                    action=command.action,
                    status=CommandStatus.FAILED,
                    error=f"外部身体传输失败: {exc}",
                )
            )
        if not isinstance(result, CommandResult):
            return self._invalid_result(command, "没有返回 CommandResult")
        if result.command_id != command.command_id or result.action != command.action:
            return self._invalid_result(command, "确认结果与原命令不匹配")
        return self._remember(result)

    @property
    def last_result(self) -> Optional[CommandResult]:
        return self._last_result

    def _remember(self, result: CommandResult) -> CommandResult:
        self._last_result = result
        return result

    def _invalid_result(self, command: BodyCommand, reason: str) -> CommandResult:
        return self._remember(
            CommandResult(
                command_id=command.command_id,
                action=command.action,
                status=CommandStatus.FAILED,
                error=f"外部身体返回无效结果: {reason}",
            )
        )
