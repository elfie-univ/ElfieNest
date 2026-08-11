"""Production composition for the existing cognition Runtime."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.food.resolver import MainFoodSelection
from ai_runtime.gateway.agent import RuntimeAgent
from app.bootstrap.food import build_food_service
from app.bootstrap.runtime_food import final_main_food_loader
from infrastructure.models.fallback_runtime import FallbackRuntimeAdapter
from infrastructure.models.runtime_adapter import StructuredRuntime
from infrastructure.persistence.food_catalog import SQLiteFoodPackageRepository


@dataclass(frozen=True)
class RuntimeServices:
    """Existing Runtime objects selected and assembled at the composition root."""

    runtime: StructuredRuntime
    tick_interval_sec: float
    main_food_loader: Callable[[str], MainFoodSelection] | None = None
    warmup: Callable[[], None] | None = None


def build_runtime_services(
    db_path: str,
    *,
    use_fallback: bool,
    live_reload: bool,
    resolve_main_food: bool,
) -> RuntimeServices:
    """Construct the current Runtime without starting any background thread."""
    config = LLMRuntimeConfig(ollama_host="http://localhost:11434")
    engine_config = config.system.get("engine", {})
    tick_interval_sec = float(engine_config.get("tick_interval_sec", 1.5))
    if use_fallback:
        return RuntimeServices(
            runtime=FallbackRuntimeAdapter(),
            tick_interval_sec=tick_interval_sec,
        )

    main_food_loader: Callable[[str], MainFoodSelection] | None = None
    if resolve_main_food:
        main_food_loader = final_main_food_loader(build_food_service(db_path))
    runtime = RuntimeAgent(
        config,
        live_reload=live_reload,
        main_food_loader=main_food_loader,
        food_catalog_repository=SQLiteFoodPackageRepository(db_path),
    )

    def warmup() -> None:
        runtime.ask(
            "hello",
            energy=100,
            task_complexity=1,
            allowed_skills=[],
        )

    return RuntimeServices(
        runtime=runtime,
        tick_interval_sec=tick_interval_sec,
        main_food_loader=main_food_loader,
        warmup=warmup,
    )


__all__ = ("RuntimeServices", "build_runtime_services")
