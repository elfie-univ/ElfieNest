"""Production assembly for the live Nest Session workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Union

from ai_runtime.food.resolver import MainFoodSelection
from app.orchestration.nest_session import CorticalRuntimeFactory, ElfieNestEngine
from infrastructure.godot.nest_session import GodotNestSessionAdapter
from infrastructure.models.runtime_adapter import (
    SerializedRuntimeAdapter,
    StructuredRuntime,
)
from infrastructure.persistence import SQLiteNestStateAdapter
from infrastructure.persistence.data_home import get_elfie_workspace_dir

MainFoodLoader = Callable[[str], Optional[Union[str, MainFoodSelection]]]


@dataclass(frozen=True)
class NestSessionServices:
    """One assembled live Nest and its injected Runtime boundaries."""

    engine: ElfieNestEngine
    world_runtime: GodotNestSessionAdapter
    runtime_factory: CorticalRuntimeFactory


def build_nest_session_services(
    db_path: str,
    *,
    runtime: StructuredRuntime,
    godot_ws_port: int,
    http_port: int,
    tick_interval_sec: float,
    main_food_loader: MainFoodLoader | None = None,
) -> NestSessionServices:
    """Construct the existing Engine without starting any lifecycle-owned channel."""
    world_runtime = GodotNestSessionAdapter(
        port=godot_ws_port,
        http_port=http_port,
    )

    def runtime_factory(elfie_id: str) -> SerializedRuntimeAdapter:
        return SerializedRuntimeAdapter(
            runtime,
            food_key_resolver=lambda: (
                main_food_loader(elfie_id) if main_food_loader is not None else None
            ),
            elfie_workspace_resolver=lambda: str(get_elfie_workspace_dir(elfie_id)),
        )

    return NestSessionServices(
        engine=ElfieNestEngine(
            world_runtime,
            tick_interval_sec=tick_interval_sec,
            nest_repository=SQLiteNestStateAdapter(db_path),
        ),
        world_runtime=world_runtime,
        runtime_factory=runtime_factory,
    )


__all__ = (
    "MainFoodLoader",
    "NestSessionServices",
    "build_nest_session_services",
)
