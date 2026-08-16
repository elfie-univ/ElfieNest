"""Owner-scoped external communication-account resources."""

from fastapi import APIRouter

from .discord_routes import router as discord_router
from .routes import router as telegram_router

router = APIRouter()
router.include_router(telegram_router)
router.include_router(discord_router)

__all__ = ("router",)
