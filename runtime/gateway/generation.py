import logging
from collections.abc import Callable
from dataclasses import dataclass
from itertools import count
from typing import Any

from runtime.config import LLMRuntimeConfig
from runtime.gateway.fallback import build_fallback_prompt, resolve_fallback_plan
from runtime.gateway.loop import RuntimeToolLoop, ToolLoopContext
from runtime.gateway.model_guard import ensure_model_ready
from runtime.gateway.multimodal import assemble_multimodal_payload
from runtime.gateway.skills_prompt import inject_skills_system_prompt

logger = logging.getLogger("runtime.gateway.generation")


class RemoteModelCallError(RuntimeError):
    def __init__(self, failure: Exception):
        super().__init__(str(failure))
        self.failure = failure


@dataclass(frozen=True, slots=True)
class GenerationRuntime:
    config: LLMRuntimeConfig
    registry: Any
    ollama_manager: Any
    search_plugin: Any
    sandbox_plugin: Any
    skills_evolution_plugin: Any
    permission_manager: Any
    call_llm_api: Callable[
        [str, str, list[dict[str, Any]], float, int],
        str,
    ]
    set_fallback_info: Callable[[dict[str, Any] | None], None]


def generate_text(
    runtime: GenerationRuntime,
    model_key: str,
    messages: list[dict[str, Any]],
    images: list[str] | None = None,
    audio: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    allowed_skills: list[str] | None = None,
    max_loops: int = 1,
    admin_token: str | None = None,
) -> str:
    target = ensure_model_ready(
        model_key, runtime.registry, runtime.ollama_manager, images, audio
    )
    local_messages = prepare_messages(
        messages, images, audio, target.provider, allowed_skills
    )
    temp = temperature if temperature is not None else runtime.config.temperature
    tokens = max_tokens if max_tokens is not None else runtime.config.max_tokens
    tool_loop = build_tool_loop(runtime, allowed_skills, admin_token)
    loop_numbers = count(1)

    def call_remote(messages_for_loop: list[dict[str, Any]]) -> str:
        loop_idx = next(loop_numbers)
        logger.info(
            "⚡ 大模型底座交互循环 #%s/%s (Model: %s)...",
            loop_idx,
            max_loops,
            target.model_name,
        )
        try:
            return runtime.call_llm_api(
                target.provider, target.model_name, messages_for_loop, temp, tokens
            )
        except (RuntimeError, ValueError) as failure:
            if target.provider == "ollama":
                raise
            raise RemoteModelCallError(failure) from failure

    try:
        return tool_loop.run(local_messages, max_loops, call_remote)
    except RemoteModelCallError as failure:
        return generate_with_local_fallback(
            runtime=runtime,
            failed_model_key=model_key,
            failed_provider=target.provider,
            failure=failure.failure,
            messages=messages,
            allowed_skills=allowed_skills,
            max_loops=max_loops,
            admin_token=admin_token,
            temperature=temp,
            max_tokens=tokens,
        )


def prepare_messages(
    messages: list[dict[str, Any]],
    images: list[str] | None,
    audio: str | None,
    provider: str,
    allowed_skills: list[str] | None,
) -> list[dict[str, Any]]:
    local_messages = [dict(message) for message in messages]
    if images or audio:
        local_messages = assemble_multimodal_payload(
            local_messages, images, audio, provider
        )
    if allowed_skills:
        local_messages = inject_skills_system_prompt(local_messages, allowed_skills)
    return local_messages


def build_tool_loop(
    runtime: GenerationRuntime,
    allowed_skills: list[str] | None,
    admin_token: str | None,
) -> RuntimeToolLoop:
    return RuntimeToolLoop(
        ToolLoopContext(
            allowed_skills=tuple(allowed_skills or ()),
            search_plugin=runtime.search_plugin,
            sandbox_plugin=runtime.sandbox_plugin,
            skills_evolution_plugin=runtime.skills_evolution_plugin,
            permission_manager=runtime.permission_manager,
            admin_token=admin_token,
        )
    )


def generate_with_local_fallback(
    runtime: GenerationRuntime,
    failed_model_key: str,
    failed_provider: str,
    failure: Exception,
    messages: list[dict[str, Any]],
    allowed_skills: list[str] | None,
    max_loops: int,
    admin_token: str | None,
    temperature: float,
    max_tokens: int,
) -> str:
    plan = resolve_fallback_plan(
        failed_model_key=failed_model_key,
        failed_provider=failed_provider,
        failure=failure,
        registry=runtime.registry,
        ollama_manager=runtime.ollama_manager,
    )
    runtime.set_fallback_info(
        {
            "from_model_key": failed_model_key,
            "to_model_key": plan.model_key,
            "reason": plan.reason,
        }
    )

    target = ensure_model_ready(
        plan.model_key, runtime.registry, runtime.ollama_manager, None, None
    )
    fallback_messages = [
        {
            "role": "user",
            "content": build_fallback_prompt(messages, plan.reason),
        }
    ]
    if allowed_skills:
        fallback_messages = inject_skills_system_prompt(fallback_messages, allowed_skills)

    tool_loop = build_tool_loop(runtime, allowed_skills, admin_token)
    loop_numbers = count(1)

    def call_local(messages_for_loop: list[dict[str, Any]]) -> str:
        loop_idx = next(loop_numbers)
        logger.info(
            "⚠️ 本地 Ollama 兜底循环 #%s/%s (Model: %s)...",
            loop_idx,
            max_loops,
            target.model_name,
        )
        return runtime.call_llm_api(
            target.provider, target.model_name, messages_for_loop, temperature, max_tokens
        )

    return tool_loop.run(fallback_messages, max_loops, call_local)
