import logging
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from runtime.config import LLMRuntimeConfig
from runtime.providers.dispatch import detect_api_mode_for_url
from runtime.providers.streaming import (
    STREAM_DISPATCH,
    stream_openai_compatible_api,
)

logger = logging.getLogger("runtime.gateway.streaming")


@dataclass(frozen=True, slots=True)
class RuntimeStreamRequest:
    config: LLMRuntimeConfig
    provider: str
    model_name: str
    messages: list[dict[str, Any]]
    temperature: float
    max_tokens: int
    allowed_skills: tuple[str, ...] = ()


def stream_runtime_response(request: RuntimeStreamRequest) -> Iterator[str]:
    provider_cfg: dict[str, Any] = request.config.providers.get(request.provider, {})
    api_key = provider_cfg.get("api_key", "")
    api_base = provider_cfg.get("api_base", "")
    api_mode = provider_cfg.get("api_mode", "") or detect_api_mode_for_url(api_base)
    stream_fn = STREAM_DISPATCH.get(api_mode, stream_openai_compatible_api)

    logger.info("⚡ 大模型底座 SSE 流式交互 (Model: %s)...", request.model_name)

    full_response = ""
    try:
        if api_mode == "ollama":
            stream_generator = stream_fn(
                api_base or request.config.ollama_host,
                request.model_name,
                request.messages,
                request.temperature,
                request.max_tokens,
            )
        elif api_mode == "anthropic_messages":
            stream_generator = stream_fn(
                api_base,
                api_key,
                request.model_name,
                request.messages,
                request.temperature,
                request.max_tokens,
            )
        else:
            stream_generator = stream_fn(
                api_base,
                api_key,
                request.model_name,
                request.messages,
                request.temperature,
                request.max_tokens,
                request.provider,
            )

        for chunk in stream_generator:
            full_response += chunk
            yield chunk

    except Exception as error:
        if full_response:
            yield f"\n⚠️ [流式生成中断] 已返回部分响应，错误: {error}"
        else:
            yield f"❌ 流式生成失败: {error}"
        return

    detected_skills = detect_stream_skill_tags(full_response, request.allowed_skills)
    if detected_skills:
        yield f"\n⚠️ [流式模式提示] 检测到技能标签: {', '.join(detected_skills)}。流式模式下不支持自动回调执行，请使用 generate() 进行完整工具调用。"


def detect_stream_skill_tags(response_text: str, allowed_skills: tuple[str, ...]) -> list[str]:
    detected_skills = []
    if "web_search" in allowed_skills and "[SEARCH]" in response_text:
        detected_skills.append("web_search")
    if "code_sandbox" in allowed_skills and "[CODE]" in response_text:
        detected_skills.append("code_sandbox")
    if "skills_evolution" in allowed_skills:
        if "[WRITE_SKILL]" in response_text:
            detected_skills.append("write_skill")
        if "[RUN_SKILL]" in response_text:
            detected_skills.append("run_skill")
        if "[LIST_SKILLS]" in response_text:
            detected_skills.append("list_skills")
    return detected_skills
