"""Application composition root."""

from .accounts import build_accounts_service
from .api import create_app
from .container import ApplicationContainer, build_application_container

__all__ = (
    "ApplicationContainer",
    "build_accounts_service",
    "build_application_container",
    "create_app",
)
