"""Owner Provider route assembly with stable public URLs."""

from fastapi import APIRouter

from .ollama_owner_routes import router as ollama_owner_router

router = APIRouter(prefix="/api/owner/providers", tags=["providers"])
router.include_router(ollama_owner_router)
