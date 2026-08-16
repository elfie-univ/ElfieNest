"""Typed full-health contract for the authoritative Runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


class RuntimeComponent(str, Enum):
    """Processes and capabilities required by one ElfieNest Runtime."""

    CORE = "core"
    GATEWAY = "gateway"
    GODOT_AUTHORITY = "godot_authority"
    OLLAMA = "ollama"


class RuntimeHealthState(str, Enum):
    """Closed lifecycle states shared by source and installed commands."""

    STARTING = "starting"
    READY = "ready"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class RuntimeProgressPhase(str, Enum):
    """Transient phases emitted while a Runtime is becoming usable."""

    STARTING = "starting"
    CORE_READY = "core_ready"
    AUTHORITY_STARTING = "authority_starting"
    READY = "ready"
    STOPPING = "stopping"
    FAILED = "failed"


@dataclass(frozen=True)
class OwnerLease:
    """Identifies the client that created one Runtime generation."""

    owner_id: str
    generation: int


@dataclass(frozen=True)
class ComponentHealth:
    """Health of one named Runtime component."""

    component: RuntimeComponent
    state: RuntimeHealthState
    detail: str = ""
    pid: Optional[int] = None


@dataclass(frozen=True)
class RuntimeHealth:
    """Full component graph and ownership state for a Runtime generation."""

    state: RuntimeHealthState
    generation: int
    owner_lease: Optional[OwnerLease]
    components: Tuple[ComponentHealth, ...]
    startup_owner_id: Optional[str] = None

    def component(self, component: RuntimeComponent) -> ComponentHealth:
        """Return one component health from the closed Runtime graph."""
        for item in self.components:
            if item.component is component:
                return item
        raise LookupError(f"Runtime component missing from health graph: {component}")
