"""现有精灵运行对象与稳定动态状态之间的转换。"""

from __future__ import annotations

from typing import Any

from .models import ElfieState


def capture_elfie_state(elfie: Any) -> ElfieState:
    """读取现有子系统的公开状态，不复制其内部算法。"""
    return ElfieState(
        energy=float(elfie.hypothalamus.energy),
        fatigue=float(elfie.hypothalamus.fatigue),
        is_sleeping=bool(elfie.hypothalamus.is_sleeping),
        emotions={
            str(name): float(value) for name, value in elfie.amygdala.emotions.items()
        },
        elapsed_time=float(elfie.elapsed_time),
        current_body_id=elfie.body_binding.current_body_id,
    )


def restore_elfie_state(
    elfie: Any,
    state: ElfieState,
    *,
    restore_body: bool = True,
) -> bool:
    """恢复动态值；目标身体未注册时保留当前绑定并返回 False。"""
    state.validate()
    elfie.hypothalamus.energy = min(state.energy, elfie.hypothalamus.max_energy)
    elfie.hypothalamus.fatigue = min(
        state.fatigue, elfie.hypothalamus.max_fatigue
    )
    elfie.hypothalamus.is_sleeping = state.is_sleeping
    elfie._was_sleeping = state.is_sleeping
    elfie.amygdala.emotions.update(state.emotions)
    elfie.elapsed_time = state.elapsed_time

    if not restore_body:
        return True
    if state.current_body_id is None:
        if elfie.body_binding.current is not None:
            elfie.unbind_body()
        return True
    if elfie.body_registry.get(state.current_body_id) is None:
        return False
    elfie.bind_body(state.current_body_id)
    return True
