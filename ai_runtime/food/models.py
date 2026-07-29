"""粮食领域对象。

推理强度、模型和 Provider 参数全部封装在 ``ExecutionProfile`` 内部，
精灵只持有粮食 key，不直接选择这些底层细节。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping


class ReasoningProfile(str, Enum):
    """Runtime 内部推理档位，不属于精灵公开接口。"""

    OFF = "off"
    LOW = "low"
    BALANCED = "balanced"
    DEEP = "deep"
    MAX = "max"
    VERIFY = "verify"


class FoodValidationStatus(str, Enum):
    UNVERIFIED = "unverified"
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"


@dataclass(frozen=True)
class FoodKind:
    key: str
    display_name: str
    description: str
    required_capabilities: tuple[str, ...] = ("text",)


FIXED_FOOD_KINDS: Mapping[str, FoodKind] = {
    "coarse": FoodKind("coarse", "Coarse", "Local-first, low-cost simple tasks"),
    "standard": FoodKind(
        "standard", "Standard", "Daily default, balanced quality/speed/cost"
    ),
    "focus": FoodKind(
        "focus", "Focus", "Logic analysis and complex problems", ("text", "reasoning")
    ),
    "creative": FoodKind("creative", "Creative", "Writing, imagination and expression"),
    "tool": FoodKind("tool", "工具粮", "搜索、文件和代码工具调用", ("text", "tools")),
    "vision": FoodKind(
        "vision", "Vision", "Image understanding and visual tasks", ("text", "vision")
    ),
    "premium": FoodKind(
        "premium", "Premium", "High-quality deep reasoning", ("text", "reasoning")
    ),
    "emergency": FoodKind(
        "emergency",
        "Emergency",
        "High-urgency scenarios prioritizing reliability and speed",
    ),
}


@dataclass(frozen=True)
class ExecutionProfile:
    model: str
    reasoning_profile: ReasoningProfile = ReasoningProfile.BALANCED
    max_tokens: int = 1500
    temperature: float = 0.7
    tools: tuple[str, ...] = ()
    provider_options: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasoning_profile"] = self.reasoning_profile.value
        # Tool authorization belongs to Runtime/Elfie policy, not a model package.
        payload.pop("tools", None)
        payload["provider_options"] = dict(self.provider_options)
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ExecutionProfile:
        return cls(
            model=str(data.get("model", "")),
            reasoning_profile=_parse_reasoning(data.get("reasoning_profile")),
            max_tokens=int(data.get("max_tokens", 1500)),
            temperature=float(data.get("temperature", 0.7)),
            tools=(),
            provider_options=(
                dict(data.get("provider_options", {}))
                if isinstance(data.get("provider_options", {}), Mapping)
                else {}
            ),
        )


@dataclass(frozen=True)
class FoodRecipe:
    key: str
    display_name: str
    description: str
    primary: ExecutionProfile
    deep: ExecutionProfile | None = None
    vision: ExecutionProfile | None = None
    verifier: ExecutionProfile | None = None
    technical_fallbacks: tuple[ExecutionProfile, ...] = ()
    local_only: bool = False
    validation_status: FoodValidationStatus = FoodValidationStatus.UNVERIFIED
    source: str = "auto"
    locked_fields: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "display_name": self.display_name,
            "description": self.description,
            "primary": self.primary.to_dict(),
            "deep": self.deep.to_dict() if self.deep else None,
            "vision": self.vision.to_dict() if self.vision else None,
            "verifier": self.verifier.to_dict() if self.verifier else None,
            "technical_fallbacks": [
                profile.to_dict() for profile in self.technical_fallbacks
            ],
            "local_only": self.local_only,
            "validation_status": self.validation_status.value,
            "source": self.source,
            "locked_fields": list(self.locked_fields),
        }

    @classmethod
    def from_dict(cls, key: str, data: Mapping[str, Any]) -> FoodRecipe:
        kind = FIXED_FOOD_KINDS.get(key)
        primary = data.get("primary", {})
        if not isinstance(primary, Mapping):
            primary = {}
        return cls(
            key=key,
            display_name=str(
                data.get("display_name", kind.display_name if kind else key)
            ),
            description=str(data.get("description", kind.description if kind else "")),
            primary=ExecutionProfile.from_dict(primary),
            deep=_optional_profile(data.get("deep")),
            vision=_optional_profile(data.get("vision")),
            verifier=_optional_profile(data.get("verifier")),
            technical_fallbacks=tuple(
                ExecutionProfile.from_dict(item)
                for item in data.get("technical_fallbacks", ())
                if isinstance(item, Mapping)
            ),
            local_only=bool(data.get("local_only", False)),
            validation_status=_parse_validation_status(data.get("validation_status")),
            source=str(data.get("source", "auto")),
            locked_fields=tuple(
                str(item) for item in data.get("locked_fields", ()) if str(item)
            ),
        )


def _optional_profile(value: Any) -> ExecutionProfile | None:
    return ExecutionProfile.from_dict(value) if isinstance(value, Mapping) else None


def _parse_reasoning(value: Any) -> ReasoningProfile:
    try:
        return ReasoningProfile(str(value or ReasoningProfile.BALANCED.value))
    except ValueError:
        return ReasoningProfile.BALANCED


def _parse_validation_status(value: Any) -> FoodValidationStatus:
    try:
        return FoodValidationStatus(str(value or FoodValidationStatus.UNVERIFIED.value))
    except ValueError:
        return FoodValidationStatus.UNVERIFIED
