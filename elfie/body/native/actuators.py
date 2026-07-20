"""Native 身体到现有 Godot WebSocket 协议的动作适配。"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from elfie.body.capabilities import BodyCapabilities
from elfie.body.native.godot_transport import GodotTransport
from elfie.body.types import BodyCommand, CommandResult, CommandStatus


class NativeActuators:
    def __init__(
        self,
        body_id: str,
        capabilities: BodyCapabilities,
        transport: GodotTransport,
    ):
        self.body_id = body_id
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
                    error="NativeBody 尚未连接",
                )
            )
        if not self.capabilities.supports_action(command.action):
            return self._remember(
                CommandResult(
                    command_id=command.command_id,
                    action=command.action,
                    status=CommandStatus.REJECTED,
                    error=f"NativeBody 不支持动作: {command.action}",
                )
            )
        if command.action == "system.emergency_stop":
            return self._remember(
                CommandResult(
                    command_id=command.command_id,
                    action=command.action,
                    status=CommandStatus.REJECTED,
                    error="当前 Godot 协议尚未实现可确认的紧急停止动作",
                )
            )

        messages = self._encode(command)
        if not messages:
            return self._remember(
                CommandResult(
                    command_id=command.command_id,
                    action=command.action,
                    status=CommandStatus.REJECTED,
                    error=f"NativeBody 无法把命令映射到现有 Godot 事件: {command.action}",
                )
            )
        for message in messages:
            self.transport.send_action(message["action"], message["payload"])
        return self._remember(
            CommandResult(
                command_id=command.command_id,
                action=command.action,
                status=CommandStatus.COMPLETED,
                output={"sent": True, "messages": messages},
            )
        )

    @property
    def last_result(self) -> Optional[CommandResult]:
        return self._last_result

    def _remember(self, result: CommandResult) -> CommandResult:
        self._last_result = result
        return result

    def _encode(self, command: BodyCommand) -> List[Dict[str, Any]]:
        parameters = dict(command.parameters)
        messages: List[Dict[str, Any]] = []

        speech = str(parameters.get("speech", ""))
        if speech:
            messages.append(
                self._message(
                    "speak_event",
                    {
                        "text": speech,
                        "audio_url": str(parameters.get("audio_url", "")),
                        "emotion": str(parameters.get("emotion", "")),
                    },
                )
            )

        target = str(parameters.get("target", ""))
        if target:
            messages.append(
                self._message(
                    "go_to",
                    {
                        "target": target,
                        "posture": str(parameters.get("posture", "standing")),
                        "animation": str(parameters.get("animation", "walk_loop")),
                    },
                )
            )

        if not self._is_transport_only(command.action):
            configured_expression = parameters.get("expression", {})
            expression_payload: Dict[str, Any] = (
                dict(configured_expression)
                if isinstance(configured_expression, Mapping)
                else {}
            )
            expression_payload.setdefault("actions", [command.action])
            expression_payload.setdefault(
                "joint_angles", dict(parameters.get("joint_angles", {}))
            )
            mutter = str(parameters.get("mutter", ""))
            if mutter:
                expression_payload["mutter"] = mutter
            messages.append(self._message("emotion_expression", expression_payload))

        return messages

    def _message(self, action: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "action": action,
            "payload": {"elfie_id": self.body_id, **dict(payload)},
        }

    @staticmethod
    def _is_transport_only(action: str) -> bool:
        return action in {"speech.say", "movement.go_to", "go_to"}
