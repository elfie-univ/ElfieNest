"""Typed selection of the process that hosts Godot authority."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class RuntimeDisplayMode(str, Enum):
    """Whether an authority host requires a visible graphics display."""

    GRAPHICAL = "graphical"
    DISPLAYLESS = "displayless"


class RuntimeHostKind(str, Enum):
    """Closed set of authority-host implementations."""

    WEB_AUTHORITY = "web_authority"
    ELECTRON_AUTHORITY = "electron_authority"
    LINUX_DEDICATED = "linux_dedicated"


@dataclass(frozen=True)
class RuntimeHostDescriptor:
    """Host selection without Nest state, scene data, or protocol credentials."""

    kind: RuntimeHostKind
    display_mode: RuntimeDisplayMode


@dataclass(frozen=True)
class RuntimeHostSelectionContext:
    """Platform facts used to select exactly one authority host."""

    platform_name: str
    display_available: bool
    electron_available: bool
    dedicated_override: bool = False
    requested_kind: Optional[RuntimeHostKind] = None


def select_authority_host(kind: RuntimeHostKind) -> RuntimeHostDescriptor:
    """Describe the requested host without launching a Godot process."""
    display_modes = {
        RuntimeHostKind.WEB_AUTHORITY: RuntimeDisplayMode.GRAPHICAL,
        RuntimeHostKind.ELECTRON_AUTHORITY: RuntimeDisplayMode.GRAPHICAL,
        RuntimeHostKind.LINUX_DEDICATED: RuntimeDisplayMode.DISPLAYLESS,
    }
    return RuntimeHostDescriptor(kind, display_modes[kind])


def select_platform_authority_host(
    context: RuntimeHostSelectionContext,
) -> RuntimeHostDescriptor:
    """Select the locked Electron-versus-Dedicated authority policy."""
    if context.dedicated_override:
        return select_authority_host(RuntimeHostKind.LINUX_DEDICATED)
    if context.requested_kind is not None:
        return select_authority_host(context.requested_kind)
    if context.platform_name in {"darwin", "win32"}:
        return select_authority_host(RuntimeHostKind.ELECTRON_AUTHORITY)
    if (
        context.platform_name.startswith("linux")
        and context.display_available
        and context.electron_available
    ):
        return select_authority_host(RuntimeHostKind.ELECTRON_AUTHORITY)
    return select_authority_host(RuntimeHostKind.LINUX_DEDICATED)
