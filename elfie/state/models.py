"""精灵可恢复动态状态的数据模型。"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

STATE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ElfieState:
    """不包含稳定档案和长期记忆的轻量运行快照。"""

    schema_version: int = STATE_SCHEMA_VERSION
    energy: float = 100.0
    fatigue: float = 0.0
    is_sleeping: bool = False
    emotions: Dict[str, float] = field(default_factory=dict)
    elapsed_time: float = 0.0
    current_body_id: Optional[str] = None

    def validate(self) -> None:
        if self.schema_version != STATE_SCHEMA_VERSION:
            raise ValueError(f"不支持 state schema_version={self.schema_version}")
        for name, value in (
            ("energy", self.energy),
            ("fatigue", self.fatigue),
            ("elapsed_time", self.elapsed_time),
        ):
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ValueError(f"{name} 必须是有限数值")
            if float(value) < 0.0:
                raise ValueError(f"{name} 不能为负数")
        if not isinstance(self.is_sleeping, bool):
            raise ValueError("is_sleeping 必须是布尔值")
        if self.current_body_id is not None and (
            not isinstance(self.current_body_id, str) or not self.current_body_id.strip()
        ):
            raise ValueError("current_body_id 必须是非空字符串或 null")
        for name, value in self.emotions.items():
            if not isinstance(name, str) or not name:
                raise ValueError("emotions 的键必须是非空字符串")
            if (
                not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or not 0.0 <= float(value) <= 100.0
            ):
                raise ValueError(f"emotions.{name} 必须在 [0, 100] 内")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> ElfieState:
        emotions_raw = raw.get("emotions", {})
        state = cls(
            schema_version=int(raw.get("schema_version", STATE_SCHEMA_VERSION)),
            energy=float(raw.get("energy", 100.0)),
            fatigue=float(raw.get("fatigue", 0.0)),
            is_sleeping=raw.get("is_sleeping", False),
            emotions={
                str(name): float(value)
                for name, value in (
                    emotions_raw.items() if isinstance(emotions_raw, dict) else ()
                )
            },
            elapsed_time=float(raw.get("elapsed_time", 0.0)),
            current_body_id=raw.get("current_body_id"),
        )
        state.validate()
        return state
