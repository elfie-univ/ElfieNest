"""Nest 内部状态值对象。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ResidentState:
    """精灵进入 Nest 后的空间语义状态。"""

    elfie_id: str
    posture: str = "standing"
    target_furniture: Optional[str] = None
    active: bool = True


@dataclass(frozen=True)
class FurnitureState:
    """家具占用状态和可持久化位置覆盖。"""

    furniture_id: str
    occupant_id: Optional[str] = None
    transform: Optional[str] = None
    revision: int = 0


@dataclass(frozen=True)
class GodotRuntimeState:
    """当前 Godot Runtime 会话状态。"""

    connected: bool = False
    protocol_version: Optional[str] = None
