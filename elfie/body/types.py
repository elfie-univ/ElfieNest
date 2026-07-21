"""所有身体实现共享的输入、输出和状态类型。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Mapping
from uuid import uuid4

from elfie.body.capabilities import BodyCapabilities
from elfie.body.contracts import (
    BodyCommand as TypedBodyCommand,
)
from elfie.body.contracts import (
    BodyId,
    BodySensorEvent,
    BodySnapshot,
    CommandReceipt,
    EmergencyStopCommand,
    EnvironmentSample,
    ExpressionCommand,
    MotionCommand,
    ProprioceptionSample,
    SpeechCommand,
    TactileImpact,
    UtteranceFinal,
    VisionChange,
    VisionSample,
)
from elfie.body.contracts import (
    CommandStatus as ReceiptStatus,
)


class BodyMode(str, Enum):
    HEADLESS = "headless"
    NATIVE = "native"
    EXTERNAL = "external"


class CommandStatus(str, Enum):
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass(frozen=True)
class BodyEvent:
    """身体传给神经系统的一次传感器事件。"""

    sensor: str
    payload: Mapping[str, Any]
    source: str
    event_id: str = field(default_factory=lambda: f"event_{uuid4().hex[:12]}")
    timestamp: float = field(default_factory=time.time)

    def to_sensor_data(self) -> Dict[str, Any]:
        return dict(self.payload)


@dataclass(frozen=True)
class BodyCommand:
    """神经系统发给当前身体的一次语义动作命令。"""

    action: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    command_id: str = field(default_factory=lambda: f"command_{uuid4().hex[:12]}")


@dataclass(frozen=True)
class CommandResult:
    command_id: str
    action: str
    status: CommandStatus
    output: Mapping[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_id": self.command_id,
            "action": self.action,
            "status": self.status.value,
            "output": dict(self.output),
            "error": self.error,
        }


@dataclass(frozen=True)
class BodyDescriptor:
    body_id: str
    mode: BodyMode
    display_name: str
    capabilities: BodyCapabilities

    def to_dict(self) -> Dict[str, Any]:
        return {
            "body_id": self.body_id,
            "mode": self.mode.value,
            "display_name": self.display_name,
            "capabilities": self.capabilities.to_dict(),
        }


@dataclass(frozen=True)
class BodyState:
    body_id: str
    connected: bool
    pending_event_count: int = 0
    last_action: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "body_id": self.body_id,
            "connected": self.connected,
            "pending_event_count": self.pending_event_count,
            "last_action": self.last_action,
            "metadata": dict(self.metadata),
        }


# Explicit compatibility names remain until the Task 14 caller migration.
LegacyBodyEvent = BodyEvent
LegacyBodyCommand = BodyCommand
LegacyCommandResult = CommandResult
LegacyCommandStatus = CommandStatus


__all__ = (
    "BodyCommand",
    "BodyDescriptor",
    "BodyEvent",
    "BodyId",
    "BodyMode",
    "BodySensorEvent",
    "BodySnapshot",
    "BodyState",
    "CommandReceipt",
    "CommandResult",
    "CommandStatus",
    "EmergencyStopCommand",
    "EnvironmentSample",
    "ExpressionCommand",
    "LegacyBodyCommand",
    "LegacyBodyEvent",
    "LegacyCommandResult",
    "LegacyCommandStatus",
    "MotionCommand",
    "ProprioceptionSample",
    "ReceiptStatus",
    "SpeechCommand",
    "TactileImpact",
    "TypedBodyCommand",
    "UtteranceFinal",
    "VisionChange",
    "VisionSample",
)
