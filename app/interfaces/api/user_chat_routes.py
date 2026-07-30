"""普通用户读取精灵工作区聊天历史的兼容 API。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from app.features.accounts.auth import get_current_user
from app.infrastructure.persistence.elfie_chat_history import (
    ElfieChatHistoryRange,
    list_elfie_chat_history,
)
from app.infrastructure.persistence.runtime_query_repository import (
    RuntimeQueryRepository,
)

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
    if not RuntimeQueryRepository(request.app.state.db_path).elfie_is_owned_by(
        elfie_id, user_id
    ):
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
            data_home=Path(request.app.state.db_path).expanduser().parent,
        )
    ]
