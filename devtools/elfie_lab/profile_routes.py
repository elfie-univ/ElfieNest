"""Elfie Lab 稳定档案编辑 HTTP 路由。"""

from fastapi import APIRouter, HTTPException

from devtools.elfie_lab.api_models import BigFiveUpdateRequest
from devtools.elfie_lab.session_registry import SessionBusyError, SessionRegistry
from devtools.elfie_lab.storage import ElfieLabStorage


def build_profile_router(
    storage: ElfieLabStorage,
    sessions: SessionRegistry,
) -> APIRouter:
    router = APIRouter()

    @router.patch("/api/elfies/{elfie_id}/personality")
    def update_personality(elfie_id: str, request: BigFiveUpdateRequest):
        values = request.model_dump()
        try:
            session = sessions.reload(
                elfie_id,
                lambda: storage.update_big_five(elfie_id, values),
            )
            return session.get_payload()
        except SessionBusyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return router
