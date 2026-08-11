"""Production composition for the HTTP application."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI

from app.interfaces.api.app import create_http_application
from app.interfaces.api.ws_gateway import AuthenticatedWSManager
from infrastructure.persistence.data_home import get_db_path
from infrastructure.persistence.nest_state import SQLiteNestStateAdapter

from .container import build_application_container
from .lifecycle import create_lifecycle_facade
from .storage import (
    ensure_application_storage,
    initialize_application_storage,
    seed_service_owner,
)


def create_app(
    engine: Any = None,
    db_path: Optional[str] = None,
    ws_port: int = 8766,
    http_port: int = 8000,
    service_mode: str = "loopback",
    web_build_dir: Optional[Path] = None,
) -> FastAPI:
    selected_db_path = db_path or str(get_db_path())
    ensure_application_storage(selected_db_path)
    if engine is not None and not engine.session.has_repository:
        engine.session.attach_repository(SQLiteNestStateAdapter(selected_db_path))
    container = build_application_container(
        selected_db_path,
        nest_session=None if engine is None else engine.session,
    )
    lifecycle = create_lifecycle_facade()
    ws_manager = AuthenticatedWSManager(
        accounts=container.accounts,
        message_delivery=container.message_delivery,
        port=ws_port,
        http_port=http_port,
    )
    if engine is not None:
        engine.session.owner_broadcaster = ws_manager

    def start_application() -> None:
        initialize_application_storage(selected_db_path)
        container.setup_installation.recover()
        seed_service_owner(selected_db_path)
        lifecycle.start_runtime_channel(ws_manager)

    def stop_application() -> None:
        lifecycle.stop_runtime_channel(ws_manager)

    return create_http_application(
        accounts=container.accounts,
        settings=container.settings,
        nest_management=container.nest_management,
        elfies=container.elfies,
        providers=container.providers,
        food=container.food,
        capabilities=container.capabilities,
        operations=container.operations,
        communication=container.communication,
        message_delivery=container.message_delivery,
        communication_realtime=container.communication_realtime,
        observer=container.observer,
        adoption=container.adoption,
        resident_admission=container.resident_admission,
        setup=container.setup,
        setup_installation=container.setup_installation,
        bodies=container.bodies,
        embodiment=container.embodiment,
        body_device_channel=container.body_device_channel,
        ws_manager=ws_manager,
        start_application=start_application,
        stop_application=stop_application,
        engine=engine,
        db_path=selected_db_path,
        http_port=http_port,
        service_mode=service_mode,
        web_build_dir=web_build_dir,
    )


__all__ = ("create_app",)
