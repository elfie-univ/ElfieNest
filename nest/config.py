"""Nest 初始化配置。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

FIXED_BED_COUNT: Final[int] = 32


@dataclass(frozen=True)
class NestConfigError(Exception):
    """Nest 配置不满足运行约束。"""

    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True)
class NestConfig:
    """一个本机唯一 Nest 的初始化参数。"""

    nest_id: str = "local-nest"
    bed_count: int = FIXED_BED_COUNT

    def __post_init__(self) -> None:
        if not self.nest_id.strip():
            raise NestConfigError("nest_id 不能为空")
        if self.bed_count != FIXED_BED_COUNT:
            raise NestConfigError("bed_count 必须固定为 32")


__all__ = ("FIXED_BED_COUNT", "NestConfig", "NestConfigError")
