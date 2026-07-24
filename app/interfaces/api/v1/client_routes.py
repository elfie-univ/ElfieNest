"""Session-authenticated, versioned browser and future-client read API."""

from __future__ import annotations

from typing import Any, Dict, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketDisconnect

from app.features.accounts.auth import get_current_user, verify_session
from app.features.elfie_profile.public_projection import build_public_profile
from app.infrastructure.persistence.chat_history import (
    ChatHistoryQuery,
    ChatMessageInput,
    ChatSender,
    list_chat_history,
    record_chat_message,
)
from app.infrastructure.persistence.embodiment_sessions import get_embodiment_session
from app.infrastructure.persistence.store import get_db

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
    user_id = int(user["id"])
    await hub.connect(user_id, websocket)
    await websocket.send_json(
        {
            "event": "ready",
            "principal": {"role": user["role"], "username": user["username"]},
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
                websocket.app, int(user["id"]), elfie_id, text
            )
        except HTTPException as error:
            await websocket.send_json({"event": "error", "detail": error.detail})
            continue
        await websocket.send_json({"event": "message", "message": message})


@router.get("/me")
async def current_client_user(
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Dict[str, Any]:
    """Expose the minimum session identity needed to select a product page."""
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "default_landing_page": user["default_landing_page"],
    }


@router.put("/me/default-landing-page")
async def update_owner_default_landing_page(
    body: LandingPageUpdate,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Dict[str, str]:
    """Persist an Owner-only landing preference; normal users always use chat."""
    if user["role"] != "owner":
        raise HTTPException(status_code=403, detail="只有 Owner 可以设置管理默认页")
    with get_db(request.app.state.db_path) as connection:
        connection.execute(
            "UPDATE users SET default_landing_page = ? WHERE id = ?",
            (body.default_landing_page, int(user["id"])),
        )
        connection.commit()
    return {"default_landing_page": body.default_landing_page}


@router.get("/elfies")
async def list_public_elfies(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> list[Dict[str, Any]]:
    """List the authenticated user's Elfies as public profile projections."""
    return _owned_public_profiles(request.app.state.db_path, int(user["id"]))


@router.get("/elfies/{elfie_id}/profile")
async def public_elfie_profile(
    elfie_id: str,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Dict[str, Any]:
    """Read one owned Elfie without exposing raw YAML or local paths."""
    profiles = _owned_public_profiles(request.app.state.db_path, int(user["id"]))
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
    user_id = int(user["id"])
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
    user_id = int(user["id"])
    if not _owns_elfie(db_path, user_id, elfie_id):
        raise HTTPException(status_code=404, detail="精灵不存在")
    return [
        {
            "id": message.id,
            "elfie_id": message.elfie_id,
            "sender": message.sender,
            "text": message.text,
            "created_at": message.created_at,
        }
        for message in list_chat_history(db_path, ChatHistoryQuery(elfie_id, user_id))
    ]


@router.post("/conversations/{elfie_id}/messages")
async def send_conversation_message(
    elfie_id: str,
    body: ChatMessageCreate,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Dict[str, Any]:
    """Persist and deliver one owned-elfie message through the Core session."""
    return _send_client_message(request.app, int(user["id"]), elfie_id, body.text)


def _owned_public_profiles(db_path: str, user_id: int) -> list[Dict[str, Any]]:
    with get_db(db_path) as connection:
        rows = connection.execute(
            """SELECT e.elfie_id, e.name, e.species_id, e.personality_style,
                      e.config_dir, e.bed_id, b.name AS bed_name,
                      r.id AS room_id, r.name AS room_name
               FROM elfie_registry e
               LEFT JOIN beds b ON b.id = e.bed_id
               LEFT JOIN rooms r ON r.id = b.room_id
               WHERE e.owner_user_id = ? ORDER BY e.created_at DESC""",
            (user_id,),
        ).fetchall()
    return [
        build_public_profile(
            elfie_id=str(row["elfie_id"]),
            name=str(row["name"]),
            species_id=str(row["species_id"]),
            personality_style=str(row["personality_style"] or ""),
            config_dir=str(row["config_dir"]),
            room_id=int(row["room_id"]) if row["room_id"] is not None else None,
            room_name=str(row["room_name"]) if row["room_name"] is not None else None,
            bed_id=int(row["bed_id"]) if row["bed_id"] is not None else None,
            bed_name=str(row["bed_name"]) if row["bed_name"] is not None else None,
            embodiment_state=get_embodiment_session(
                db_path, str(row["elfie_id"])
            ).state.value,
        )
        for row in rows
    ]


def _owns_elfie(db_path: str, user_id: int, elfie_id: str) -> bool:
    with get_db(db_path) as connection:
        row = connection.execute(
            "SELECT 1 FROM elfie_registry WHERE elfie_id = ? AND owner_user_id = ?",
            (elfie_id, user_id),
        ).fetchone()
    return row is not None


def _conversation_summary(
    db_path: str, user_id: int, profile: Dict[str, Any]
) -> Dict[str, Any]:
    messages = list_chat_history(
        db_path, ChatHistoryQuery(str(profile["elfie_id"]), user_id)
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
    app: Any, user_id: int, elfie_id: str, text: str
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
            account_id="product-web",
        )
    message = record_chat_message(
        app.state.db_path,
        ChatMessageInput(
            elfie_id=elfie_id,
            user_id=user_id,
            sender=ChatSender.USER,
            text=normalized,
            meta="已投递到下一次 tick",
        ),
    )
    return {
        "id": message.id,
        "elfie_id": message.elfie_id,
        "sender": message.sender,
        "text": message.text,
        "created_at": message.created_at,
    }
