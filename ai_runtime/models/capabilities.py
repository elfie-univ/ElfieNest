"""模型家族的已知能力目录。

这里记录模型本身公开声明的能力，不代表某个 Provider 通道一定完整开放这些
能力。连通性、工具调用等通道能力仍由 Runtime Lab 的真实验证结果负责。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelCapabilityProfile:
    canonical_name: str
    capabilities: frozenset[str]
    source: str = "official_catalog"


# 讯飞官方模型 ID 是确定性映射；ID 比用户手工填写的显示名更可信。
_EXACT_MODEL_IDS: dict[str, ModelCapabilityProfile] = {
    "xopglm5": ModelCapabilityProfile("GLM-5", frozenset({"text", "reasoning"})),
    "xopglm51": ModelCapabilityProfile(
        "GLM-5.1", frozenset({"text", "reasoning"})
    ),
    "xopglm52": ModelCapabilityProfile(
        "GLM-5.2", frozenset({"text", "reasoning"})
    ),
    "xopkimik25": ModelCapabilityProfile(
        "Kimi-K2.5", frozenset({"text", "reasoning", "vision"})
    ),
    "xopkimik26": ModelCapabilityProfile(
        "Kimi-K2.6", frozenset({"text", "reasoning", "vision"})
    ),
    "xminimaxm25": ModelCapabilityProfile(
        "MiniMax-M2.5", frozenset({"text", "reasoning"})
    ),
}


def resolve_model_capability_profile(
    model_id: str,
    display_name: str = "",
) -> ModelCapabilityProfile | None:
    """按官方 ID 或规范显示名解析模型能力。"""
    short_id = model_id.rsplit("/", 1)[-1].strip().lower()
    exact = _EXACT_MODEL_IDS.get(short_id)
    if exact is not None:
        return exact

    name = f"{display_name} {short_id}".lower().replace("_", "-").replace(" ", "-")
    if any(marker in name for marker in ("kimi-k2.5", "kimi-k2-5")):
        return ModelCapabilityProfile(
            "Kimi-K2.5", frozenset({"text", "reasoning", "vision"})
        )
    if any(marker in name for marker in ("kimi-k2.6", "kimi-k2-6")):
        return ModelCapabilityProfile(
            "Kimi-K2.6", frozenset({"text", "reasoning", "vision"})
        )
    for version in ("5.2", "5.1", "5"):
        if f"glm-{version}" in name:
            return ModelCapabilityProfile(
                f"GLM-{version}", frozenset({"text", "reasoning"})
            )
    if "minimax-m2.5" in name or "minimax-m2-5" in name:
        return ModelCapabilityProfile(
            "MiniMax-M2.5", frozenset({"text", "reasoning"})
        )
    return None


def known_capabilities(model_id: str, display_name: str = "") -> frozenset[str]:
    profile = resolve_model_capability_profile(model_id, display_name)
    return profile.capabilities if profile else frozenset()


def canonical_display_name(model_id: str, display_name: str = "") -> str:
    """官方精确 ID 可纠正错误别名；模糊匹配不覆盖用户自定义名称。"""
    short_id = model_id.rsplit("/", 1)[-1].strip().lower()
    exact = _EXACT_MODEL_IDS.get(short_id)
    return exact.canonical_name if exact else display_name or model_id
