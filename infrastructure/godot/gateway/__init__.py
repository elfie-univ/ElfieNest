"""Authenticated protocol-v3 transport for the Godot authority."""

from infrastructure.godot.gateway.bundle import (
    GodotWebBundleStatus,
    inspect_godot_web_bundle,
)
from infrastructure.godot.gateway.messages import (
    CommandName,
    EventName,
    IntentTerminalStatus,
    RuntimeCommandFrame,
    RuntimeEventFrame,
    SemanticLane,
    parse_runtime_command_frame,
    parse_runtime_event_frame,
)
from infrastructure.godot.gateway.session import (
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
    "GodotWebBundleStatus",
    "IntentTerminalStatus",
    "RuntimeAuthorityError",
    "RuntimeCommandFrame",
    "RuntimeConnection",
    "RuntimeEventFrame",
    "SemanticLane",
    "RuntimeQueueFullError",
    "RuntimeSession",
    "RuntimeSessionNotReadyError",
    "StaleRuntimeEventError",
    "inspect_godot_web_bundle",
    "parse_runtime_command_frame",
    "parse_runtime_event_frame",
]
