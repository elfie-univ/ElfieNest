"""Deterministic safety checks for direct owner replies."""

from __future__ import annotations

import re
from dataclasses import dataclass

_CURRENT_NEST_QUERY = re.compile(
    r"(?:精灵巢|巢内|巢里|elfienest).{0,32}"
    r"(?:今天|现在|此刻|刚才|最近|发生|活动|动态|情况|在做|怎么样)"
    r"|(?:今天|现在|此刻|刚才|最近).{0,32}"
    r"(?:精灵巢|巢内|巢里|elfienest)",
    flags=re.IGNORECASE | re.DOTALL,
)
_EXPLICIT_UNKNOWN = re.compile(
    r"(?:不(?:知道|清楚)|不知道|还没有(?:真实)?(?:探索|去过|接触)|"
    r"尚未(?:探索|接触)|没(?:有)?(?:真实)?(?:探索|去过)|"
    r"无法(?:知道|确认|获取)|没有(?:巢内|精灵巢).{0,8}"
    r"(?:观测|信息|事实|记录))",
    flags=re.IGNORECASE | re.DOTALL,
)
_UNSAFE_CURRENT_NEST_CLAIM = re.compile(
    r"(?:今天|现在|此刻|刚才|最近).{0,32}"
    r"(?:精灵巢|巢内|巢里|elfienest).{0,32}"
    r"(?:发生|活动|动态|情况|在做|安静|整理|待)",
    flags=re.IGNORECASE | re.DOTALL,
)

SAFE_CURRENT_NEST_REPLY = "我现在还没有真实探索精灵巢，所以不知道今天那里发生了什么呢。"


@dataclass(frozen=True)
class ReplySafetyContext:
    """Facts needed to enforce current-state boundaries for one direct reply."""

    current_message: str
    has_current_nest_observation: bool = False


def sanitize_direct_owner_reply(
    text: str,
    context: ReplySafetyContext | None,
) -> str:
    """Keep unsupported current Nest claims out of owner-facing chat."""
    if context is None or context.has_current_nest_observation:
        return text
    if not _CURRENT_NEST_QUERY.search(context.current_message):
        return text
    if _EXPLICIT_UNKNOWN.search(text) and not _UNSAFE_CURRENT_NEST_CLAIM.search(text):
        return text
    return SAFE_CURRENT_NEST_REPLY


__all__ = (
    "ReplySafetyContext",
    "SAFE_CURRENT_NEST_REPLY",
    "sanitize_direct_owner_reply",
)
