"""身体实现共享的描述类型。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict

from elfie.body.capabilities import BodyCapabilities


class BodyMode(str, Enum):
    HEADLESS = "headless"
    NATIVE = "native"
    EXTERNAL = "external"


@dataclass(frozen=True)
class BodyDescriptor:
    body_id: str
    mode: BodyMode
    display_name: str
    capabilities: BodyCapabilities

    def to_dict(self) -> Dict[str, object]:
        return {
            "body_id": self.body_id,
            "mode": self.mode.value,
            "display_name": self.display_name,
            "capabilities": self.capabilities.to_dict(),
        }
__all__ = (
    "BodyDescriptor",
    "BodyMode",
)
