"""Owner Provider route assembly with stable public URLs."""

from fastapi import APIRouter

from .provider_connection_routes import router as connection_router
from .provider_config_routes import router as config_router
from .provider_model_routes import router as model_router
from .provider_validation_routes import router as validation_router

router = APIRouter(prefix="/api/owner/providers", tags=["providers"])
router.include_router(connection_router)
router.include_router(model_router)
router.include_router(validation_router)
router.include_router(config_router)
