from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from ai_runtime.usage.observer import RuntimeEvent, get_runtime_observer
from app.interfaces.api.v1.auth import require_manager

router = APIRouter(prefix="/api/owner/runtime", tags=["runtime"])


def build_runtime_status() -> Dict[str, Any]:
    observer_events = get_runtime_observer().snapshot()

    return {
        "status": "ok",
        "observer": {
            "event_count": len(observer_events),
            "last_event": _event_payload(observer_events[-1])
            if observer_events
            else None,
        },
    }


@router.get("/status")
async def get_runtime_status(
    owner: Dict[str, Any] = Depends(require_manager),  # noqa: B008
) -> Dict[str, Any]:
    _ = owner
    return build_runtime_status()


def _event_payload(event: RuntimeEvent) -> Dict[str, Any]:
    return event.to_dict()
