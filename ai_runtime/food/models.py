"""Food packages map semantic roles to exact connection/model references."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional

FOOD_EMERGENCY_ID = "food_emergency"
FOOD_COMMON_ID = "food_common"
SYSTEM_FOOD_IDS = frozenset({FOOD_EMERGENCY_ID, FOOD_COMMON_ID})
FOOD_ROLES = ("primary", "reasoning", "vision", "tool", "fallback")


class FoodValidationStatus(str, Enum):
    UNVERIFIED = "unverified"
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"


@dataclass(frozen=True)
class ModelAssignment:
    model: str

    def to_dict(self) -> dict[str, str]:
        return {"model": self.model}

    @classmethod
    def from_value(cls, value: Any) -> Optional[ModelAssignment]:
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
        elif isinstance(value, Mapping):
            normalized = str(value.get("model") or "").strip()
        else:
            normalized = ""
        return cls(normalized) if normalized else None


@dataclass(frozen=True)
class FoodPackage:
    key: str
    display_name: str
    system_role: Optional[str] = None
    enabled: bool = True
    archived: bool = False
    primary: Optional[ModelAssignment] = None
    reasoning: Optional[ModelAssignment] = None
    vision: Optional[ModelAssignment] = None
    tool: Optional[ModelAssignment] = None
    fallback: Optional[ModelAssignment] = None
    visibility_mode: str = "global"
    visible_user_ids: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.system_role not in {None, "emergency", "common"}:
            raise ValueError("未知系统粮食角色")
        if self.visibility_mode not in {"global", "users"}:
            raise ValueError("未知粮食可见范围")
        normalized_user_ids = tuple(sorted({int(user_id) for user_id in self.visible_user_ids}))
        if any(user_id <= 0 for user_id in normalized_user_ids):
            raise ValueError("粮食可见用户 ID 必须为正整数")
        if self.visibility_mode == "global" and normalized_user_ids:
            raise ValueError("全局可见粮食不能包含指定用户")
        if self.visibility_mode == "users" and not normalized_user_ids:
            raise ValueError("指定用户可见粮食至少需要一个用户")
        object.__setattr__(self, "visible_user_ids", normalized_user_ids)
        if self.key in SYSTEM_FOOD_IDS and self.system_role is None:
            raise ValueError("系统粮食必须声明系统角色")
        if self.system_role is not None and self.archived:
            raise ValueError("系统粮食不能归档")
        if self.archived and self.enabled:
            raise ValueError("归档粮食不能保持启用")

    @property
    def model_references(self) -> tuple[str, ...]:
        assignments = (
            self.primary,
            self.reasoning,
            self.vision,
            self.tool,
            self.fallback,
        )
        return tuple(item.model for item in assignments if item is not None)

    def assignment_for(self, role: str) -> Optional[ModelAssignment]:
        if role == "fallback":
            return self.fallback
        if role not in FOOD_ROLES:
            raise ValueError(f"未知模型角色: {role}")
        return getattr(self, role)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "display_name": self.display_name,
            "system_role": self.system_role,
            "enabled": self.enabled,
            "archived": self.archived,
            "visibility_mode": self.visibility_mode,
            "visible_user_ids": list(self.visible_user_ids),
            "roles": {
                "primary": self.primary.to_dict() if self.primary else None,
                "reasoning": self.reasoning.to_dict() if self.reasoning else None,
                "vision": self.vision.to_dict() if self.vision else None,
                "tool": self.tool.to_dict() if self.tool else None,
                "fallback": self.fallback.to_dict() if self.fallback else None,
            },
        }

    @classmethod
    def from_dict(cls, key: str, data: Mapping[str, Any]) -> FoodPackage:
        raw_roles = data.get("roles")
        roles = raw_roles if isinstance(raw_roles, Mapping) else {}
        raw_fallback = roles.get("fallback")
        if raw_fallback is not None and not isinstance(raw_fallback, Mapping):
            raise ValueError("roles.fallback 必须是对象或 null")
        fallback = ModelAssignment.from_value(raw_fallback)
        return cls(
            key=key,
            display_name=str(data.get("display_name") or key).strip(),
            system_role=(str(data["system_role"]) if data.get("system_role") else None),
            enabled=bool(data.get("enabled", True)),
            archived=bool(data.get("archived", False)),
            visibility_mode=str(data.get("visibility_mode") or "global"),
            visible_user_ids=tuple(
                int(user_id)
                for user_id in (data.get("visible_user_ids") or ())
                if isinstance(user_id, int) and not isinstance(user_id, bool)
            ),
            primary=ModelAssignment.from_value(roles.get("primary")),
            reasoning=ModelAssignment.from_value(roles.get("reasoning")),
            vision=ModelAssignment.from_value(roles.get("vision")),
            tool=ModelAssignment.from_value(roles.get("tool")),
            fallback=fallback,
        )


def system_food_packages() -> dict[str, FoodPackage]:
    return {
        FOOD_EMERGENCY_ID: FoodPackage(
            key=FOOD_EMERGENCY_ID,
            display_name="保底粮",
            system_role="emergency",
            enabled=False,
        ),
        FOOD_COMMON_ID: FoodPackage(
            key=FOOD_COMMON_ID,
            display_name="常用粮",
            system_role="common",
            enabled=False,
        ),
    }
