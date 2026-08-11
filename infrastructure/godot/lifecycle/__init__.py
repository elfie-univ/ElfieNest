"""Godot authority-host selection, launch, and lifecycle adapters."""

from infrastructure.godot.lifecycle.host_contract import (
    RuntimeDisplayMode,
    RuntimeHostDescriptor,
    RuntimeHostKind,
    RuntimeHostSelectionContext,
    select_authority_host,
    select_platform_authority_host,
)
from infrastructure.godot.lifecycle.launcher import (
    AuthorityLaunchError,
    AuthorityLaunchFailureKind,
    AuthorityLaunchPlan,
    AuthorityLaunchRequest,
    find_runtime_binary,
    start_godot_runtime,
    stop_godot_runtime,
)

__all__ = (
    "AuthorityLaunchError",
    "AuthorityLaunchFailureKind",
    "AuthorityLaunchPlan",
    "AuthorityLaunchRequest",
    "RuntimeDisplayMode",
    "RuntimeHostDescriptor",
    "RuntimeHostKind",
    "RuntimeHostSelectionContext",
    "find_runtime_binary",
    "select_authority_host",
    "select_platform_authority_host",
    "start_godot_runtime",
    "stop_godot_runtime",
)
