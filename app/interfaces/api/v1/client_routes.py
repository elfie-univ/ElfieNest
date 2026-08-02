"""Session-authenticated, versioned browser and future-client read API."""

from __future__ import annotations

from typing import Any, Dict, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketDisconnect

from ai_runtime.storage.data_home import data_home_from_db_path
from app.features.accounts.auth import get_current_user, verify_session
from app.features.elfie_profile.public_projection import build_public_profile
from app.infrastructure.persistence.elfie_chat_history import (
    list_elfie_chat_history,
)
from app.infrastructure.persistence.embodiment_sessions import get_embodiment_session
from app.infrastructure.persistence.runtime_query_repository import (
    RuntimeQueryRepository,
)
from app.interfaces.api.chat_persistence import record_owner_chat_message

router = APIRouter(prefix="/api/v1", tags=["v1-client"])


class LandingPageUpdate(BaseModel):
    default_landing_page: Literal["chat", "manage"]


class ChatMessageCreate(BaseModel):
    """A bounded message sent by an authenticated product client."""

    text: str = Field(..., min_length=1, max_length=4000)


@router.websocket("/ws/chat")
async def chat_websocket(websocket: WebSocket) -> None:
    """Authenticate the future chat stream with the same session as REST."""
    policy = websocket.app.state.service_access_policy
    origin = websocket.headers.get("origin")
    if policy.mode.value == "lan" and (
        origin is None or not policy.allows_origin(origin)
    ):
        await websocket.close(code=1008)
        return
    token = websocket.cookies.get("session_token")
    user = verify_session(token, websocket.app.state.db_path) if token else None
    if user is None:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    hub = websocket.app.state.v1_chat_hub
    user_id = user["user_id"]
    await hub.connect(user_id, websocket)
    await websocket.send_json(
        {
            "event": "ready",
            "principal": {
                "role": user["role"],
                "account_id": user["account_id"],
            },
        }
    )
    while True:
        try:
            payload = await websocket.receive_json()
        except WebSocketDisconnect:
            await hub.disconnect(user_id, websocket)
            return
        if not isinstance(payload, dict) or payload.get("event") != "user_message":
            await websocket.send_json({"event": "error", "detail": "不支持的聊天事件"})
            continue
        elfie_id = payload.get("elfie_id")
        text = payload.get("text")
        if not isinstance(elfie_id, str) or not isinstance(text, str):
            await websocket.send_json({"event": "error", "detail": "聊天字段无效"})
            continue
        try:
            message = _send_client_message(
                websocket.app,
                user["user_id"],
                user["account_id"],
                elfie_id,
                text,
            )
        except HTTPException as error:
            await websocket.send_json({"event": "error", "detail": error.detail})
            continue
        await websocket.send_json({"event": "message", "message": message})


@router.get("/me")
async def current_client_user(
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Dict[str, Any]:
    """Expose the minimum session identity needed to choose a product page."""
    return {
        "user_id": user["user_id"],
        "account_id": user["account_id"],
        "role": user["role"],
        "default_landing_page": user["default_landing_page"],
    }


@router.put("/me/default-landing-page")
async def update_owner_default_landing_page(
    body: LandingPageUpdate,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Dict[str, str]:
    """Persist a manager landing preference; normal users always use chat."""
    if user["role"] not in {"owner", "admin"}:
        raise HTTPException(
            status_code=403, detail="只有 Owner 或 Admin 可以设置管理默认页"
        )
    RuntimeQueryRepository(request.app.state.db_path).update_default_landing_page(
        user["user_id"], body.default_landing_page
    )
    return {"default_landing_page": body.default_landing_page}


@router.get("/elfies")
async def list_public_elfies(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> list[Dict[str, Any]]:
    """List the authenticated user's Elfies as public profile projections."""
    return _owned_public_profiles(request.app.state.db_path, user["user_id"])


@router.get("/elfies/{elfie_id}/profile")
async def public_elfie_profile(
    elfie_id: str,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Dict[str, Any]:
    """Read one owned Elfie without exposing raw YAML or local paths."""
    profiles = _owned_public_profiles(request.app.state.db_path, user["user_id"])
    for profile in profiles:
        if profile["elfie_id"] == elfie_id:
            return profile
    raise HTTPException(status_code=404, detail="精灵不存在")


@router.get("/conversations")
async def list_conversations(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> list[Dict[str, Any]]:
    """Return chat list rows using only the current user's message history."""
    db_path = request.app.state.db_path
    user_id = user["user_id"]
    profiles = _owned_public_profiles(db_path, user_id)
    return [_conversation_summary(db_path, user_id, profile) for profile in profiles]


@router.get("/conversations/{elfie_id}/messages")
async def list_conversation_messages(
    elfie_id: str,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> list[Dict[str, Any]]:
    """Return the authenticated user's messages without legacy meta fields."""
    db_path = request.app.state.db_path
    user_id = user["user_id"]
    if not _owns_elfie(db_path, user_id, elfie_id):
        raise HTTPException(status_code=404, detail="精灵不存在")
    return [
        {
            "id": message.id,
            "elfie_id": elfie_id,
            "sender": message.sender.value,
            "text": message.text,
            "created_at": message.created_at,
        }
        for message in list_elfie_chat_history(
            elfie_id,
            user_id=user_id,
            data_home=data_home_from_db_path(db_path),
        )
    ]


@router.post("/conversations/{elfie_id}/messages")
async def send_conversation_message(
    elfie_id: str,
    body: ChatMessageCreate,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Dict[str, Any]:
    """Persist and deliver one owned-elfie message through the Core session."""
    return _send_client_message(
        request.app, user["user_id"], user["account_id"], elfie_id, body.text
    )


def _owned_public_profiles(db_path: str, user_id: int) -> list[Dict[str, Any]]:
    data_home = data_home_from_db_path(db_path)
    profiles: list[Dict[str, Any]] = []
    for record in RuntimeQueryRepository(db_path).list_elfies_for_owner(user_id):
        profile_dir = data_home / "elfies" / record.elfie_id / "profile"
        profile = build_public_profile(
            elfie_id=record.elfie_id,
            name=record.name,
            species_id=record.species,
            personality_style=record.summary or "",
            config_dir=str(profile_dir),
            room_id=None,
            room_name=None,
            bed_id=record.bed_number,
            bed_name=(
                f"Bed {record.bed_number}" if record.bed_number is not None else None
            ),
            embodiment_state=get_embodiment_session(
                db_path, record.elfie_id
            ).state.value,
        )
        profile["gender"] = record.gender
        profile["birth_date"] = record.birth_date
        profile["summary"] = record.summary
        profiles.append(profile)
    return profiles


def _owns_elfie(db_path: str, user_id: int, elfie_id: str) -> bool:
    return RuntimeQueryRepository(db_path).elfie_is_owned_by(elfie_id, user_id)


def _conversation_summary(
    db_path: str, user_id: int, profile: Dict[str, Any]
) -> Dict[str, Any]:
    messages = list_elfie_chat_history(
        str(profile["elfie_id"]),
        user_id=user_id,
        data_home=data_home_from_db_path(db_path),
    )
    latest = messages[-1] if messages else None
    return {
        "elfie_id": profile["elfie_id"],
        "name": profile["name"],
        "portrait_url": profile["portrait_url"],
        "last_message_preview": latest.text if latest else "",
        "last_message_at": latest.created_at if latest else None,
    }


def _send_client_message(
    app: Any, user_id: int, account_id: str, elfie_id: str, text: str
) -> Dict[str, Any]:
    """Keep HTTP and same-origin WebSocket chat submission behavior identical."""
    normalized = text.strip()
    if not normalized:
        raise HTTPException(status_code=422, detail="消息不能为空")
    if not _owns_elfie(app.state.db_path, user_id, elfie_id):
        raise HTTPException(status_code=404, detail="精灵不存在")
    engine = app.state.engine
    if engine is not None:
        engine.session.send_user_message(
            elfie_id,
            normalized,
            owner_id=str(user_id),
            conversation_id=f"owner:{user_id}",
            account_id=account_id,
        )
    message = record_owner_chat_message(
        elfie_id,
        user_id,
        normalized,
        conversation_id=f"owner:{user_id}",
        channel="web",
    )
    return {
        "id": message.id,
        "elfie_id": elfie_id,
        "sender": message.sender.value,
        "text": message.text,
        "created_at": message.created_at,
    }
