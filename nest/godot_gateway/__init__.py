"""Nest 与 Godot Runtime 的协议和会话适配。"""

from nest.godot_gateway.api import GodotAPIServer
from nest.godot_gateway.bundle import GodotWebBundleStatus, inspect_godot_web_bundle
from nest.godot_gateway.messages import (
    CommandName,
    EventName,
    IntentTerminalStatus,
    RuntimeCommandFrame,
    RuntimeEventFrame,
    parse_runtime_command_frame,
    parse_runtime_event_frame,
)
from nest.godot_gateway.session import (
    RuntimeAuthorityError,
    RuntimeConnection,
    RuntimeQueueFullError,
    RuntimeSession,
    RuntimeSessionNotReadyError,
    StaleRuntimeEventError,
)

__all__ = [
    "CommandName",
    "EventName",
    "GodotAPIServer",
    "GodotWebBundleStatus",
    "IntentTerminalStatus",
    "RuntimeCommandFrame",
    "RuntimeAuthorityError",
    "RuntimeConnection",
    "RuntimeEventFrame",
    "RuntimeQueueFullError",
    "RuntimeSession",
    "RuntimeSessionNotReadyError",
    "StaleRuntimeEventError",
    "inspect_godot_web_bundle",
    "parse_runtime_command_frame",
    "parse_runtime_event_frame",
]
