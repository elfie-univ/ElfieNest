"""普通用户读取精灵工作区聊天历史的兼容 API。"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from app.features.accounts.auth import get_current_user
from app.infrastructure.persistence.elfie_chat_history import (
    ElfieChatHistoryRange,
    list_elfie_chat_history,
)
from app.infrastructure.persistence.store import get_db

router = APIRouter()


@router.get("/elfies/{elfie_id}/chat-history")
async def get_elfie_chat_history(
    elfie_id: str,
    request: Request,
    range: ElfieChatHistoryRange = ElfieChatHistoryRange.ALL,  # noqa: A002
    q: str = "",
    limit: int = 100,
    user: Dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> list[Dict[str, Any]]:
    """保持旧返回字段，同时只读取该精灵自己的历史库。"""
    user_id = int(user["id"])
    if not _owns_elfie(request.app.state.db_path, elfie_id, user_id):
        raise HTTPException(status_code=404, detail="精灵不存在")
    return [
        {
            "id": record.id,
            "elfie_id": elfie_id,
            "sender": record.sender.value,
            "text": record.text,
            "meta": record.meta,
            "created_at": record.created_at,
        }
        for record in list_elfie_chat_history(
            elfie_id,
            user_id=user_id,
            history_range=range,
            keyword=q,
            limit=limit,
        )
    ]


def _owns_elfie(db_path: str, elfie_id: str, user_id: int) -> bool:
    with get_db(db_path) as connection:
        row = connection.execute(
            "SELECT 1 FROM elfie_registry WHERE elfie_id = ? AND owner_user_id = ?",
            (elfie_id, user_id),
        ).fetchone()
    return row is not None
