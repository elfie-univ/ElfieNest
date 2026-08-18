"""Authoritative, versioned Runtime lifecycle snapshots.

The lifecycle layer persists :class:`RuntimeSnapshotV1`.  Public clients receive
the deliberately smaller :class:`RuntimeProjectionV1`; neither object exposes
the process supervisor or a local control secret.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple


class RuntimeComponent(str, Enum):
    """Technical components observed by the lifecycle authority."""

    CORE = "core"
    GATEWAY = "gateway"
    GODOT_AUTHORITY = "godot_authority"
    OLLAMA = "ollama"


class ComponentState(str, Enum):
    """State of one component; this is not the Runtime stable tier."""

    ABSENT = "absent"
    STARTING = "starting"
    READY = "ready"
    DEGRADED = "degraded"
    FAILED = "failed"
    STOPPING = "stopping"
    UNKNOWN = "unknown"


class BackendTier(str, Enum):
    """The only stable backend states exposed to product clients."""

    OFFLINE = "offline"
    CORE_READY = "core_ready"
    WORLD_READY = "world_ready"


class RuntimePhase(str, Enum):
    """Transient lifecycle phase, independent from the stable backend tier."""

    OFFLINE = "offline"
    PREFLIGHT = "preflight"
    CORE_STARTING = "core_starting"
    CORE_READY = "core_ready"
    WORLD_STARTING = "world_starting"
    WORLD_READY = "world_ready"
    MODEL_PROJECTING = "model_projecting"
    LOCAL_MODEL_STARTING = "local_model_starting"
    QUIESCING = "quiescing"
    WORLD_STOPPING = "world_stopping"
    MODEL_LEASE_RELEASING = "model_lease_releasing"
    CORE_STOPPING = "core_stopping"
    RECOVERY_REQUIRED = "recovery_required"
    FAILED = "failed"


class RuntimeTarget(str, Enum):
    """Background convergence target and caller wait target."""

    CORE = "core"
    WORLD = "world"
    NORMAL = "normal"

    @property
    def rank(self) -> int:
        return {RuntimeTarget.CORE: 1, RuntimeTarget.WORLD: 2, RuntimeTarget.NORMAL: 3}[
            self
        ]


class ModelOverallState(str, Enum):
    """Independent model-service projection consumed by lifecycle."""

    UNCONFIGURED = "unconfigured"
    READY = "ready"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ModelHealthProjection:
    """Versioned model-capability input consumed by lifecycle."""

    state: ModelOverallState = ModelOverallState.UNCONFIGURED
    common_state: ModelOverallState = ModelOverallState.UNCONFIGURED
    emergency_state: ModelOverallState = ModelOverallState.UNCONFIGURED
    revision: Optional[int] = None


@dataclass(frozen=True)
class OwnerLease:
    """The authenticated writer lease for one Runtime generation."""

    owner_id: str
    generation: int


@dataclass(frozen=True)
class ComponentSnapshot:
    """Sanitized component evidence persisted in the Runtime snapshot."""

    component: RuntimeComponent
    state: ComponentState
    detail: str = ""
    pid: Optional[int] = None
    executable: Optional[str] = None
    birth_identity: Optional[str] = None
    cwd: Optional[str] = None


@dataclass(frozen=True)
class EndpointSnapshot:
    """One endpoint published by the current generation after atomic bind."""

    name: str
    scheme: str
    host: str
    port: int
    protocol_version: str = ""


@dataclass(frozen=True)
class FailureSnapshot:
    """Stable, user-actionable failure evidence."""

    code: str
    detail: str
    phase: str = ""


@dataclass(frozen=True)
class TimingSnapshot:
    """Completed duration or current elapsed duration for one phase."""

    phase: str
    duration_ms: Optional[int] = None
    elapsed_ms: Optional[int] = None


@dataclass(frozen=True)
class RuntimeObservation:
    """Ephemeral probe result; it is converted into the authoritative snapshot."""

    components: Tuple[ComponentSnapshot, ...] = ()
    endpoints: Tuple[EndpointSnapshot, ...] = ()
    model_state: ModelOverallState = ModelOverallState.UNCONFIGURED
    model_common_state: ModelOverallState = ModelOverallState.UNCONFIGURED
    model_emergency_state: ModelOverallState = ModelOverallState.UNCONFIGURED
    model_revision: Optional[int] = None
    failures: Tuple[FailureSnapshot, ...] = ()
    timings: Tuple[TimingSnapshot, ...] = ()
    protocol_versions: Tuple[str, ...] = ()

    def component(self, component: RuntimeComponent) -> ComponentSnapshot:
        for item in self.components:
            if item.component is component:
                return item
        return ComponentSnapshot(component, ComponentState.ABSENT)

    @property
    def core_ready(self) -> bool:
        return all(
            self.component(component).state is ComponentState.READY
            for component in (RuntimeComponent.CORE, RuntimeComponent.GATEWAY)
        )

    @property
    def world_ready(self) -> bool:
        return self.core_ready and (
            self.component(RuntimeComponent.GODOT_AUTHORITY).state
            is ComponentState.READY
        )


@dataclass(frozen=True)
class RuntimeSnapshotV1:
    """The one durable lifecycle fact for a canonical data root."""

    schema_version: int = 1
    instance_id: str = "uninitialized"
    generation: int = 0
    revision: int = 0
    tier: BackendTier = BackendTier.OFFLINE
    phase: RuntimePhase = RuntimePhase.OFFLINE
    subphase: str = ""
    desired_target: RuntimeTarget = RuntimeTarget.CORE
    reached_target: Optional[RuntimeTarget] = None
    components: Tuple[ComponentSnapshot, ...] = ()
    endpoints: Tuple[EndpointSnapshot, ...] = ()
    model_state: ModelOverallState = ModelOverallState.UNCONFIGURED
    model_common_state: ModelOverallState = ModelOverallState.UNCONFIGURED
    model_emergency_state: ModelOverallState = ModelOverallState.UNCONFIGURED
    model_revision: Optional[int] = None
    failures: Tuple[FailureSnapshot, ...] = ()
    correlation_id: Optional[str] = None
    timings: Tuple[TimingSnapshot, ...] = ()
    protocol_versions: Tuple[str, ...] = ()
    owner_lease: Optional[OwnerLease] = None
    startup_owner_id: Optional[str] = None
    # Hash only; the raw handoff token is passed to the managed Core through
    # its private environment and is never exposed in the public projection.
    writer_credential_digest: Optional[str] = None

    def component(self, component: RuntimeComponent) -> ComponentSnapshot:
        for item in self.components:
            if item.component is component:
                return item
        return ComponentSnapshot(component, ComponentState.ABSENT)

    def projection(self) -> RuntimeProjectionV1:
        """Return the sanitized client projection."""
        return RuntimeProjectionV1(
            schema_version=self.schema_version,
            instance_id=self.instance_id,
            generation=self.generation,
            revision=self.revision,
            tier=self.tier,
            phase=self.phase,
            subphase=self.subphase,
            desired_target=self.desired_target,
            reached_target=self.reached_target,
            components=self.components,
            endpoints=self.endpoints,
            model_state=self.model_state,
            model_common_state=self.model_common_state,
            model_emergency_state=self.model_emergency_state,
            model_revision=self.model_revision,
            failures=self.failures,
            correlation_id=self.correlation_id,
            timings=self.timings,
            protocol_versions=self.protocol_versions,
            owner_lease=self.owner_lease,
            startup_owner_id=self.startup_owner_id,
        )


@dataclass(frozen=True)
class RuntimeProjectionV1:
    """Stable read-only lifecycle projection for CLI, Desktop and API."""

    schema_version: int
    instance_id: str
    generation: int
    revision: int
    tier: BackendTier
    phase: RuntimePhase
    subphase: str
    desired_target: RuntimeTarget
    reached_target: Optional[RuntimeTarget]
    components: Tuple[ComponentSnapshot, ...] = field(default_factory=tuple)
    endpoints: Tuple[EndpointSnapshot, ...] = field(default_factory=tuple)
    model_state: ModelOverallState = ModelOverallState.UNCONFIGURED
    model_common_state: ModelOverallState = ModelOverallState.UNCONFIGURED
    model_emergency_state: ModelOverallState = ModelOverallState.UNCONFIGURED
    model_revision: Optional[int] = None
    failures: Tuple[FailureSnapshot, ...] = field(default_factory=tuple)
    correlation_id: Optional[str] = None
    timings: Tuple[TimingSnapshot, ...] = field(default_factory=tuple)
    protocol_versions: Tuple[str, ...] = field(default_factory=tuple)
    owner_lease: Optional[OwnerLease] = None
    startup_owner_id: Optional[str] = None

    def component(self, component: RuntimeComponent) -> ComponentSnapshot:
        for item in self.components:
            if item.component is component:
                return item
        return ComponentSnapshot(component, ComponentState.ABSENT)


class RuntimeProgressPhase(str, Enum):
    """Small progress vocabulary used by existing human/JSON clients."""

    STARTING = "starting"
    CORE_READY = "core_ready"
    AUTHORITY_STARTING = "authority_starting"
    WORLD_READY = "world_ready"
    STOPPING = "stopping"
    FAILED = "failed"
