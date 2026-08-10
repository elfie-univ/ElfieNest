"""Versioned administrator Nest resource boundary."""

from .dependencies import nest_management_service
from .routes import router

__all__ = ("nest_management_service", "router")
