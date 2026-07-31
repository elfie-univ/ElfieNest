"""Owner Provider route assembly with stable public URLs."""

from fastapi import APIRouter

from .provider_connection_model_routes import router as connection_model_router
from .provider_connection_routes import router as connection_router

router = APIRouter(prefix="/api/owner/providers", tags=["providers"])
router.include_router(connection_router)
router.include_router(connection_model_router)
