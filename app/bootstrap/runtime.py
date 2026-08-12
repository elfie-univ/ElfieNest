"""Production composition for the existing cognition Runtime."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial

from app.bootstrap.app_wiring.food import (
    build_food_evidence,
    build_food_service,
    build_report_repository,
)
from app.bootstrap.runtime_food import final_main_food_loader
from app.bootstrap.system_wiring.runtime import build_runtime_agent_ports
from elfie.public import MainFoodSelection
from infrastructure.models.fallback_runtime import FallbackRuntimeAdapter
from infrastructure.models.inference.token_usage import get_token_tracker
from infrastructure.models.runtime_adapter import StructuredRuntime
from infrastructure.models.runtime_agent import RuntimeAgent
from infrastructure.models.runtime_observations import get_runtime_observer
from infrastructure.persistence.configuration.secrets import resolve_secret
from infrastructure.persistence.food import SQLiteFoodAdapter
from infrastructure.persistence.layout.data_home import (
    data_home_from_db_path,
    get_elfie_workspace_dir,
)
from infrastructure.persistence.layout.data_layout import final_root_layout
from infrastructure.persistence.report_storage import ReportStorageAdapter
from infrastructure.persistence.runtime_config import load_runtime_config
from infrastructure.persistence.token_usage import FileTokenUsageWriter
from infrastructure.tools import ToolPortAdapter
from infrastructure.tools.execution.config import load_tool_configs


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
    if db_path != ":memory:":
        get_token_tracker(
            FileTokenUsageWriter(
                final_root_layout(data_home_from_db_path(db_path)).token_usage_log
            )
        )
    config = load_runtime_config()
    raw_engine_config = config.system.get("engine", {})
    engine_config = raw_engine_config if isinstance(raw_engine_config, Mapping) else {}
    raw_tick_interval = engine_config.get("tick_interval_sec", 1.5)
    tick_interval_sec = (
        float(raw_tick_interval)
        if isinstance(raw_tick_interval, (int, float))
        and not isinstance(raw_tick_interval, bool)
        else 1.5
    )
    if use_fallback:
        return RuntimeServices(
            runtime=FallbackRuntimeAdapter(),
            tick_interval_sec=tick_interval_sec,
        )

    main_food_loader: Callable[[str], MainFoodSelection] | None = None
    if resolve_main_food:
        main_food_loader = final_main_food_loader(build_food_service(db_path))
    tool_port = ToolPortAdapter.from_runtime_config(
        config,
        observation_port=get_runtime_observer(),
        tool_config_loader=partial(load_tool_configs, secret_resolver=resolve_secret),
        workspace_resolver=(
            lambda elfie_id: (
                get_elfie_workspace_dir(elfie_id) if elfie_id is not None else None
            )
        ),
    )
    runtime = RuntimeAgent(
        config,
        ports=build_runtime_agent_ports(
            model_evidence_source=lambda: {
                item.reference: item
                for item in build_food_evidence(db_path).list_model_evidence()
            },
            report_writer=ReportStorageAdapter(build_report_repository(db_path)),
        ),
        live_reload=live_reload,
        main_food_loader=main_food_loader,
        food_catalog_repository=SQLiteFoodAdapter(db_path),
        tool_port=tool_port,
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
