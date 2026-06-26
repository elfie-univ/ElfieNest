from typing import Any

from runtime.config import LLMRuntimeConfig
from runtime.providers.dispatch import (
    API_DISPATCH,
    call_openai_compatible_api,
    detect_api_mode_for_url,
)
from runtime.usage.observer import (
    ModelCallObservation,
    RuntimeEventStatus,
    get_runtime_observer,
)
from runtime.usage.token_tracker import get_token_tracker


def call_llm_api(
    config: LLMRuntimeConfig,
    provider: str,
    model_name: str,
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int,
) -> str:
    provider_cfg: dict[str, Any] = config.providers.get(provider, {})
    api_key = provider_cfg.get("api_key", "")
    api_base = provider_cfg.get("api_base", "")
    api_mode = provider_cfg.get("api_mode", "") or detect_api_mode_for_url(api_base)

    dispatch_fn = API_DISPATCH.get(api_mode, call_openai_compatible_api)
    prompt_chars = sum(len(str(message.get("content", ""))) for message in messages)

    try:
        if api_mode == "ollama":
            response_text, usage = dispatch_fn(
                api_base or config.ollama_host,
                model_name,
                messages,
                temperature,
                max_tokens,
            )
        elif api_mode == "anthropic_messages":
            response_text, usage = dispatch_fn(
                api_base, api_key, model_name, messages, temperature, max_tokens
            )
        else:
            response_text, usage = dispatch_fn(
                api_base,
                api_key,
                model_name,
                messages,
                temperature,
                max_tokens,
                provider,
            )
    except (RuntimeError, ValueError) as failure:
        get_runtime_observer().record_model_call(
            ModelCallObservation(
                provider=provider,
                model_name=model_name,
                status=RuntimeEventStatus.ERROR,
                prompt_chars=prompt_chars,
                error_type=type(failure).__name__,
            )
        )
        raise

    get_runtime_observer().record_model_call(
        ModelCallObservation(
            provider=provider,
            model_name=model_name,
            status=RuntimeEventStatus.OK,
            prompt_chars=prompt_chars,
            response_chars=len(response_text),
        )
    )
    get_token_tracker().record(provider, usage)
    return response_text
