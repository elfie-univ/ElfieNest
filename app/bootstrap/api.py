"""Production composition for the HTTP application."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI

from app.interfaces.api.app import create_http_application
from infrastructure.persistence.data_home import get_db_path
from infrastructure.persistence.nest_state import SQLiteNestStateAdapter

from .container import build_application_container
from .storage import ensure_application_storage


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
        engine=engine,
        db_path=selected_db_path,
        ws_port=ws_port,
        http_port=http_port,
        service_mode=service_mode,
        web_build_dir=web_build_dir,
    )


__all__ = ("create_app",)
