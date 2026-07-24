"""精灵巢内部事件类型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

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


NestDomainEvent: TypeAlias = Union[
    ResidentAdmittedEvent,
    HomeAssignedEvent,
    RuntimeMirrorUpdatedEvent,
]
