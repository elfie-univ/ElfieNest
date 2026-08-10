"""Stable public facade and models for Runtime lifecycle orchestration."""

from app.orchestration.lifecycle.commands import (
    DEFAULT_GODOT_WS_PORT,
    DEFAULT_HTTP_PORT,
    DEFAULT_MANAGEMENT_WS_PORT,
    DEFAULT_SERVICE_PORTS,
    MANAGED_START_ENV,
    command_runs_service,
    http_port_from_command,
    service_ports_from_command,
    validate_service_ports,
)
from app.orchestration.lifecycle.facade import LifecycleFacade, RuntimeLifecycle
from app.orchestration.lifecycle.ports import AuthorityHostConfig, ServicePortStatus
from app.orchestration.lifecycle.runtime_health import (
    ComponentHealth,
    RuntimeComponent,
    RuntimeHealth,
    RuntimeHealthState,
)
from app.orchestration.lifecycle.types import (
    LaunchFailedError,
    RecoveryInProgressError,
    ServiceLifecycleResult,
    ServicePortsActiveError,
)

__all__ = [
    "AuthorityHostConfig",
    "ComponentHealth",
    "DEFAULT_GODOT_WS_PORT",
    "DEFAULT_HTTP_PORT",
    "DEFAULT_MANAGEMENT_WS_PORT",
    "DEFAULT_SERVICE_PORTS",
    "LaunchFailedError",
    "LifecycleFacade",
    "MANAGED_START_ENV",
    "RecoveryInProgressError",
    "RuntimeComponent",
    "RuntimeHealth",
    "RuntimeHealthState",
    "RuntimeLifecycle",
    "ServiceLifecycleResult",
    "ServicePortStatus",
    "ServicePortsActiveError",
    "command_runs_service",
    "http_port_from_command",
    "service_ports_from_command",
    "validate_service_ports",
]
