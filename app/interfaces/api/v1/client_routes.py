"""Session-authenticated, versioned browser and future-client read API."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketDisconnect

from ai_runtime.storage.data_home import data_home_from_db_path
from ai_runtime.storage.data_layout import final_root_layout
from app.features.accounts import AccountPrincipal
from app.features.configuration.food_access import elfie_food_policy_projection
from app.features.elfie_profile.public_projection import build_public_profile
from app.features.elfies import (
    ElfieNotFound,
    ElfiesUnavailable,
    GetElfieProfileQuery,
    ListVisibleElfiesQuery,
)
from app.infrastructure.persistence.elfie_chat_history import (
    list_elfie_chat_history,
)
from app.infrastructure.persistence.embodiment_sessions import get_embodiment_session
from app.infrastructure.persistence.food_packages import SQLiteFoodPackageRepository
from app.infrastructure.persistence.runtime_query_repository import (
    RuntimeQueryRepository,
)
from app.interfaces.api.chat_persistence import record_owner_chat_message
from app.interfaces.api.v1.auth import get_current_user
from elfie.communication.contracts import InboundDisposition, InboundDispositionStatus

router = APIRouter(prefix="/api/v1", tags=["v1-client"])


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
    user = websocket.app.state.accounts.authenticate_session(token) if token else None
    if user is None:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    hub = websocket.app.state.v1_chat_hub
    user_id = user.user_id
    await hub.connect(user_id, websocket)
    await websocket.send_json(
        {
            "event": "ready",
            "principal": {
                "role": user.role,
                "account_id": user.account_id,
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
                user.user_id,
                user.account_id,
                elfie_id,
                text,
            )
        except HTTPException as error:
            await websocket.send_json({"event": "error", "detail": error.detail})
            continue
        await websocket.send_json({"event": "message", "message": message})


@router.get("/elfies")
async def list_public_elfies(
    request: Request,
    user: AccountPrincipal = Depends(get_current_user),  # noqa: B008
) -> list[Dict[str, Any]]:
    """List the authenticated user's Elfies as public profile projections."""
    return _owned_public_profiles(request, user)


@router.get("/elfies/{elfie_id}/profile")
async def public_elfie_profile(
    elfie_id: str,
    request: Request,
    user: AccountPrincipal = Depends(get_current_user),  # noqa: B008
) -> Dict[str, Any]:
    """Read one owned Elfie without exposing raw YAML or local paths."""
    profiles = _owned_public_profiles(request, user)
    for profile in profiles:
        if profile["elfie_id"] == elfie_id:
            return _private_profile_detail(
                request,
                user,
                profile,
            )
    raise HTTPException(status_code=404, detail="精灵不存在")


@router.get("/conversations")
async def list_conversations(
    request: Request,
    user: AccountPrincipal = Depends(get_current_user),  # noqa: B008
) -> list[Dict[str, Any]]:
    """Return chat list rows using only the current user's message history."""
    db_path = request.app.state.db_path
    user_id = user.user_id
    profiles = _owned_public_profiles(request, user)
    return [_conversation_summary(db_path, user_id, profile) for profile in profiles]


@router.get("/conversations/{elfie_id}/messages")
async def list_conversation_messages(
    elfie_id: str,
    request: Request,
    user: AccountPrincipal = Depends(get_current_user),  # noqa: B008
) -> list[Dict[str, Any]]:
    """Return the authenticated user's messages without legacy meta fields."""
    db_path = request.app.state.db_path
    user_id = user.user_id
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
    user: AccountPrincipal = Depends(get_current_user),  # noqa: B008
) -> Dict[str, Any]:
    """Persist and deliver one owned-elfie message through the Core session."""
    return _send_client_message(
        request.app, user.user_id, user.account_id, elfie_id, body.text
    )


def _owned_public_profiles(
    request: Request, user: AccountPrincipal
) -> list[Dict[str, Any]]:
    db_path = request.app.state.db_path
    data_home = data_home_from_db_path(db_path)
    records = {
        record.elfie_id: record
        for record in RuntimeQueryRepository(db_path).list_elfies_for_owner(
            user.user_id
        )
    }
    try:
        visible = request.app.state.elfies.list_visible(
            user,
            ListVisibleElfiesQuery(relationship="owned"),
        )
    except ElfiesUnavailable as error:
        raise HTTPException(status_code=503, detail="精灵目录暂不可用") from error
    profiles: list[Dict[str, Any]] = []
    for item in visible:
        projected = item.profile
        record = records.get(projected.elfie_id)
        if record is None:
            continue
        elfie_layout = final_root_layout(data_home).elfie(projected.elfie_id)
        profile = build_public_profile(
            elfie_id=projected.elfie_id,
            name=projected.name,
            species_id=projected.species_id,
            personality_style=projected.summary or "",
            config_dir=str(elfie_layout.profile.parent),
            room_id=None,
            room_name=None,
            bed_id=record.bed_number,
            bed_name=(
                f"Bed {record.bed_number}" if record.bed_number is not None else None
            ),
            embodiment_state=get_embodiment_session(
                db_path, projected.elfie_id
            ).state.value,
        )
        profile["gender"] = projected.gender
        profile["birth_date"] = projected.birth_date
        profile["summary"] = projected.summary
        profile["big_five"] = (
            {} if projected.big_five is None else asdict(projected.big_five)
        )
        profile["personality_tags"] = list(projected.personality_tags)
        profiles.append(profile)
    return profiles


def _private_profile_detail(
    request: Request,
    user: AccountPrincipal,
    profile: Dict[str, Any],
) -> Dict[str, Any]:
    """Add owner-only cognition and read-only care facts to one public profile."""
    db_path = request.app.state.db_path
    elfie_id = str(profile["elfie_id"])
    try:
        detail = request.app.state.elfies.get_profile(
            user,
            GetElfieProfileQuery(elfie_id=elfie_id),
        )
    except ElfieNotFound as error:
        raise HTTPException(status_code=404, detail="精灵不存在") from error
    except ElfiesUnavailable as error:
        raise HTTPException(status_code=503, detail="精灵档案暂不可用") from error
    policy = elfie_food_policy_projection(
        db_path,
        elfie_id,
        user.user_id,
        SQLiteFoodPackageRepository(db_path).load(),
    )
    options = [
        {"id": str(item["food_id"]), "label": str(item["display_name"])}
        for item in policy["main_food_options"]
    ]
    selected_id = str(policy["effective_main_food_id"] or policy["main_food_id"] or "")
    selected_label = next(
        (item["label"] for item in options if item["id"] == selected_id),
        "",
    )
    return {
        **profile,
        "private_cognition": asdict(detail.private_cognition),
        "care_settings": {
            "food": {
                "selected_id": selected_id,
                "selected_label": selected_label,
                "options": options,
                "unavailable": bool(policy["main_food_unavailable"]),
            }
        },
    }


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


def _require_admitted_message(disposition: InboundDisposition | None) -> None:
    if disposition is None:
        raise HTTPException(status_code=503, detail="elfie_runtime_unavailable")
    if disposition.status is InboundDispositionStatus.ACCEPTED:
        return
    if disposition.status is InboundDispositionStatus.DUPLICATE:
        raise HTTPException(status_code=409, detail="duplicate_message")
    if disposition.status is InboundDispositionStatus.REJECTED:
        error = disposition.error
        if error is not None and error.retryable:
            raise HTTPException(status_code=503, detail=error.code)
        raise HTTPException(
            status_code=409,
            detail=error.code if error is not None else "message_rejected",
        )
    raise HTTPException(status_code=503, detail="message_admission_unknown")


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
        _require_admitted_message(
            engine.session.send_user_message(
                elfie_id,
                normalized,
                owner_id=str(user_id),
                conversation_id=f"owner:{user_id}",
                account_id=account_id,
            )
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
