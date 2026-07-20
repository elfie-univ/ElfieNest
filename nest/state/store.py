"""Nest 运行状态存储。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Iterable, Optional

from nest.state.config import NestConfig
from nest.state.models import FurnitureState, GodotRuntimeState, ResidentState


@dataclass(frozen=True)
class NestFullError(Exception):
    """Nest 已达到允许的居民容量。"""

    current: int
    maximum: int

    def __str__(self) -> str:
        return f"精灵巢已满 ({self.current}/{self.maximum})"


class NestState:  # noqa: MUTABLE_OK - 这是单个 Nest 的运行中状态容器。
    """维护居民、家具和 Godot 会话状态，不持有精灵实例。"""

    def __init__(self, config: NestConfig) -> None:
        self.config = config
        self.residents: Dict[str, ResidentState] = {}
        self.furniture: Dict[str, FurnitureState] = {}
        self.godot = GodotRuntimeState()
        self.elapsed_seconds = 0.0

    def register_resident(self, elfie_id: str) -> None:
        if elfie_id in self.residents:
            return
        maximum = self.config.max_residents
        if maximum is not None and len(self.residents) >= maximum:
            raise NestFullError(len(self.residents), maximum)
        self.residents[elfie_id] = ResidentState(elfie_id=elfie_id)

    def remove_resident(self, elfie_id: str) -> None:
        self.residents.pop(elfie_id, None)
        for furniture_id, state in tuple(self.furniture.items()):
            if state.occupant_id == elfie_id:
                self.furniture[furniture_id] = replace(state, occupant_id=None)

    def register_furniture(self, furniture_ids: Iterable[str]) -> None:
        self.furniture = {
            furniture_id: self.furniture.get(
                furniture_id,
                FurnitureState(furniture_id=furniture_id),
            )
            for furniture_id in furniture_ids
        }

    def update_resident(
        self,
        elfie_id: str,
        posture: str,
        target_furniture: Optional[str] = None,
    ) -> None:
        current = self.residents.get(elfie_id)
        if current is None:
            return
        if current.target_furniture in self.furniture:
            old = self.furniture[current.target_furniture]
            if old.occupant_id == elfie_id:
                self.furniture[current.target_furniture] = replace(old, occupant_id=None)
        if target_furniture in self.furniture:
            target = self.furniture[target_furniture]
            self.furniture[target_furniture] = replace(target, occupant_id=elfie_id)
        self.residents[elfie_id] = replace(
            current,
            posture=posture,
            target_furniture=target_furniture,
        )
