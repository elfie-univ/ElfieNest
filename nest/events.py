"""精灵巢内部事件类型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Union

EventValue = Union[str, float, bool, None]


@dataclass(frozen=True)
class NestEvent:
    """跨 Nest 内部组件传递的不可变事件。"""

    name: str
    payload: Mapping[str, EventValue]
