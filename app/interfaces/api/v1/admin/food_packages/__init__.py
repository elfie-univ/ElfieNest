"""Versioned administrator Food package resource boundary."""

from .dependencies import food_service
from .routes import router

__all__ = ("food_service", "router")
