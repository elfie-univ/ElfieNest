"""Production composition for the HTTP application."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Mapping, Optional

from fastapi import FastAPI

from app.features.adoption import (
    CandidatePortraitPort,
    SpeciesRuntimeReadinessPort,
)
from app.interfaces.api.app import create_http_application
from app.interfaces.api.runtime_capability import RuntimeCapabilityGate
from app.interfaces.api.service_access import ServiceAccessPolicy
from app.interfaces.web.build_discovery import (
    WebBuild,
    WebBuildManifestMalformedError,
    WebBuildManifestMissingError,
    discover_web_build,
)
from infrastructure.godot.gateway.bundle import (
    configured_godot_web_directory,
    godot_web_bundle_present,
)
from infrastructure.models.model_execution_adapter import StructuredModelExecution
from infrastructure.persistence.configuration.bundled_defaults import load_nest_config
from infrastructure.persistence.layout.data_home import get_db_path
from infrastructure.persistence.nest_db.nest_state import SQLiteNestStateAdapter

from .app_wiring.storage import (
    ensure_application_storage,
)
from .container import build_application_container


def create_app(
    engine: Any = None,
    db_path: Optional[str] = None,
    http_port: int = 8000,
    service_mode: str = "loopback",
    web_build_dir: Optional[Path] = None,
    model_execution: StructuredModelExecution | None = None,
    portraits: CandidatePortraitPort | None = None,
    runtime_capability_gate: RuntimeCapabilityGate | None = None,
    runtime_projection: Callable[[], Mapping[str, object]] | None = None,
    species_runtime: SpeciesRuntimeReadinessPort | None = None,
) -> FastAPI:
    selected_db_path = db_path or str(get_db_path())
    ensure_application_storage(selected_db_path)
    if engine is not None and not engine.session.has_state_store:
        engine.session.attach_state_store(
            SQLiteNestStateAdapter(
                selected_db_path,
                nest_config=load_nest_config(),
            )
        )
    container = build_application_container(
        selected_db_path,
        nest_session=None if engine is None else engine.session,
        model_execution=model_execution,
        portraits=portraits,
        species_runtime=species_runtime,
    )
    build_dir = _web_build_directory(web_build_dir)
    web_build, web_build_error = _discover_web_build(build_dir)
    service_access = ServiceAccessPolicy.create(service_mode, http_port)

    @asynccontextmanager
    async def application_lifespan(_app: FastAPI) -> AsyncIterator[None]:
        container.setup_installation.recover()
        container.provider_scheduler.start()
        core_validation_started = False
        runtime_started = False
        try:
            if engine is not None and container.core_validation_worker is not None:
                container.core_validation_worker.start()
                core_validation_started = True
            container.runtime_lifecycle.start()
            runtime_started = True
            yield
        finally:
            if runtime_started:
                container.runtime_lifecycle.stop()
            if core_validation_started and container.core_validation_worker is not None:
                container.core_validation_worker.stop()
            container.provider_scheduler.stop()

    return create_http_application(
        accounts=container.accounts,
        settings=container.settings,
        nest_management=container.nest_management,
        elfies=container.elfies,
        providers=container.providers,
        availability=container.availability,
        food=container.food,
        capabilities=container.capabilities,
        operations=container.operations,
        communication=container.communication,
        message_delivery=container.message_delivery,
        communication_realtime=container.communication_realtime,
        telegram_accounts=container.telegram_accounts,
        discord_accounts=container.discord_accounts,
        observer=container.observer,
        session_logout=container.session_logout,
        adoption=container.adoption,
        resident_admission=container.resident_admission,
        setup=container.setup,
        setup_installation=container.setup_installation,
        bodies=container.bodies,
        embodiment=container.embodiment,
        body_device_channel=container.body_device_channel,
        lifespan=application_lifespan,
        engine_ready=engine is not None,
        godot_web_ready=godot_web_bundle_present,
        godot_runtime_ready=lambda: bool(
            engine is not None and engine.session.runtime_world_ready
        ),
        godot_web_dir=configured_godot_web_directory(),
        service_access=service_access,
        web_build=web_build,
        web_build_error=web_build_error,
        runtime_capability_gate=runtime_capability_gate,
        runtime_projection=runtime_projection,
    )


def _web_build_directory(override: Optional[Path]) -> Path:
    if override is not None:
        return override
    configured = os.environ.get("ELFIENEST_WEB_BUILD_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "build" / "web"


def _discover_web_build(directory: Path) -> tuple[WebBuild | None, str | None]:
    try:
        return discover_web_build(directory), None
    except (WebBuildManifestMissingError, WebBuildManifestMalformedError) as error:
        return None, str(error)


__all__ = ("create_app",)
