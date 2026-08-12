from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypedDict


class UnsupportedModalError(Exception):
    pass


class RuntimeModelInfo(TypedDict):
    """Validated model capability projection consumed by the readiness guard."""

    active: bool
    name: str
    provider: str
    is_vision: bool
    is_audio: bool


class ModelRegistry(Protocol):
    def get_model_info(self, model_key: str) -> RuntimeModelInfo: ...


class OllamaManager(Protocol):
    def ensure_service_started(self) -> bool: ...


@dataclass(frozen=True)
class RuntimeModelTarget:
    model_name: str
    provider: str


def ensure_model_ready(
    model_key: str,
    registry: ModelRegistry,
    ollama_manager: OllamaManager,
    images: list[str] | None = None,
    audio: str | None = None,
) -> RuntimeModelTarget:
    model_info = registry.get_model_info(model_key)
    if not model_info["active"]:
        raise ValueError(
            f"❌ 目标模型 Key '{model_key}' 未激活，请核对云端 API Key 或本地配置。"
        )

    model_name = model_info["name"]
    provider = model_info["provider"]

    if images and not model_info["is_vision"]:
        raise UnsupportedModalError(
            f"❌ 模型 '{model_name}' 不支持处理视觉(图片)多模态输入！"
        )
    if audio and not model_info["is_audio"]:
        raise UnsupportedModalError(
            f"❌ 模型 '{model_name}' 不支持原生处理音频(语音)多模态输入！"
        )

    if provider == "ollama":
        ollama_manager.ensure_service_started()

    return RuntimeModelTarget(model_name=model_name, provider=provider)
