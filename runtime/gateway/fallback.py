from dataclasses import dataclass
from typing import Any, Protocol


class MissingLocalModelError(RuntimeError):
    pass


class ModelRegistry(Protocol):
    def get_model_info(self, model_key: str) -> dict[str, Any]: ...


class OllamaManager(Protocol):
    def has_model(self, model_name: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class FallbackPlan:
    model_key: str
    model_name: str
    provider: str
    reason: str


def resolve_fallback_plan(
    failed_model_key: str,
    failed_provider: str,
    failure: Exception,
    registry: ModelRegistry,
    ollama_manager: OllamaManager,
) -> FallbackPlan:
    local_info = registry.get_model_info("local_fast")
    model_name = local_info["name"]
    provider = local_info["provider"]

    if provider != "ollama":
        raise MissingLocalModelError(
            f"本地兜底模型配置异常：local_fast 当前 provider 为 {provider}，应为 ollama。"
        )

    if not ollama_manager.has_model(model_name):
        raise MissingLocalModelError(
            f"远程模型 {failed_model_key} 调用失败，且本地 Ollama 缺少兜底模型 {model_name}。\n"
            f"请先运行：ollama pull {model_name}\n"
            f"原始错误：{failure}"
        )

    return FallbackPlan(
        model_key="local_fast",
        model_name=model_name,
        provider=provider,
        reason=f"{failed_provider} 调用失败，已切换到本地 Ollama 兜底模型 {model_name}。",
    )


def build_fallback_prompt(messages: list[dict[str, Any]], reason: str) -> str:
    request_text = _latest_user_text(messages)
    return (
        "【本地兜底模式】\n"
        f"{reason}\n"
        "请先用简洁、诚实的方式说明当前处于本地兜底状态，再尽力回答用户请求。"
        "如果能力不足，请明确说明需要联网或云端模型恢复后继续。\n\n"
        f"【用户原始请求】\n{request_text}"
    )


def _latest_user_text(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            content = message.get("content", "")
            if isinstance(content, str):
                return content
            return str(content)
    return ""
