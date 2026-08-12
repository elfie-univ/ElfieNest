"""Application composition root."""

from .api import create_app
from .app_wiring import build_accounts_service
from .container import ApplicationContainer, build_application_container

__all__ = (
    "ApplicationContainer",
    "build_accounts_service",
    "build_application_container",
    "create_app",
)
