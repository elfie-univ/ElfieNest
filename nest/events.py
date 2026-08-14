"""精灵巢内部事件类型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Union

from typing_extensions import TypeAlias


@dataclass(frozen=True)
class ResidentAdmittedEvent:
    """居民被加入 Nest membership。"""

    elfie_id: str


@dataclass(frozen=True)
class HomeAssignedEvent:
    """居民获得长期语义住处。"""

    elfie_id: str
    home_zone_id: str
    home_anchor_id: str


@dataclass(frozen=True)
class RuntimeMirrorUpdatedEvent:
    """Runtime 镜像状态更新，不代表长期持久事实。"""

    elfie_id: str
    current_zone_id: str | None
    posture: str
    active_command_id: str | None = None


@dataclass(frozen=True)
class HeardUtterance:
    """One targeted virtual-hearing fact emitted by Nest."""

    utterance_id: str
    sender_id: str
    text: str
    emotion: str | None = None


@dataclass(frozen=True)
class SemanticVisualEntity:
    """One stable semantic referent resolved by Nest for an Elfie."""

    semantic_id: str
    kind: Literal["actor", "anchor", "facility"]
    zone_id: str
    label: str
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class SemanticVisualScene:
    """A bounded, actor-targeted semantic scene with no geometry or media."""

    observation_id: str
    observer_id: str
    zone_id: str
    entities: tuple[SemanticVisualEntity, ...]


@dataclass(frozen=True)
class SemanticActionResult:
    """Nest correlation for one semantic target resolved into a Body action."""

    command_id: str
    actor_id: str
    target: str
    resolved_anchor_id: str
    status: Literal["completed", "failed", "cancelled", "timed_out"]
    reason: str | None = None


@dataclass(frozen=True)
class NestEventEnvelope:
    """Common event metadata for facts crossing Nest-owned boundaries."""

    event_id: str
    owner: str
    cause_id: str
    target_ids: tuple[str, ...]
    occurred_at: datetime
    payload: NestDomainEvent
    runtime_id: str | None = None
    runtime_generation: int | None = None
    world_revision: int | None = None


NestDomainEvent: TypeAlias = Union[
    ResidentAdmittedEvent,
    HomeAssignedEvent,
    RuntimeMirrorUpdatedEvent,
    HeardUtterance,
    SemanticVisualScene,
    SemanticActionResult,
]
