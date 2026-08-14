from __future__ import annotations

from typing import Any, Callable, cast

from infrastructure.models.inference.token_usage import get_token_tracker
from infrastructure.models.model_execution_config import ModelExecutionConfig
from infrastructure.models.model_execution_observations import (
    ModelCallObservation,
    ModelExecutionEventStatus,
    get_model_execution_observer,
)
from infrastructure.models.providers.dispatch import (
    API_DISPATCH,
    call_openai_compatible_api,
    detect_api_mode_for_url,
)


def call_llm_api(
    config: ModelExecutionConfig,
    provider: str,
    model_name: str,
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int,
    *,
    thinking: bool = False,
    request_options: dict[str, Any] | None = None,
) -> str:
    provider_cfg: dict[str, Any] = config.providers.get(provider, {})
    api_key = provider_cfg.get("api_key", "")
    api_base = provider_cfg.get("api_base", "")
    api_mode = provider_cfg.get("api_mode", "") or detect_api_mode_for_url(api_base)

    dispatch_fn = cast(
        Callable[..., tuple[str, dict[str, Any]]],
        API_DISPATCH.get(api_mode, call_openai_compatible_api),
    )
    args: tuple[Any, ...]
    prompt_chars = sum(len(str(message.get("content", ""))) for message in messages)

    try:
        if api_mode == "ollama":
            args = (
                api_base or config.ollama_host,
                model_name,
                messages,
                temperature,
                max_tokens,
            )
        elif api_mode == "anthropic_messages":
            args = (api_base, api_key, model_name, messages, temperature, max_tokens)
        elif api_mode == "codex_responses":
            response_text, usage = dispatch_fn(
                api_base,
                api_key,
                model_name,
                messages,
                temperature,
                max_tokens,
                provider,
                request_options=(dict(request_options) if request_options else None),
                credential_ref=str(provider_cfg.get("credential_ref") or ""),
                account_id=(
                    str(provider_cfg["account_id"])
                    if provider_cfg.get("account_id")
                    else None
                ),
                oauth_credentials=config.oauth_credentials,
            )
            args = ()
        else:
            args = (
                api_base,
                api_key,
                model_name,
                messages,
                temperature,
                max_tokens,
                provider,
            )
        if api_mode == "codex_responses":
            pass
        elif api_mode == "ollama":
            response_text, usage = dispatch_fn(
                *args,
                thinking=thinking,
                request_options=dict(request_options) if request_options else None,
            )
        elif request_options:
            response_text, usage = dispatch_fn(
                *args, request_options=dict(request_options)
            )
        else:
            response_text, usage = dispatch_fn(*args)
    except (RuntimeError, ValueError) as failure:
        get_model_execution_observer().record_model_call(
            ModelCallObservation(
                provider=provider,
                model_name=model_name,
                status=ModelExecutionEventStatus.ERROR,
                prompt_chars=prompt_chars,
                error_type=type(failure).__name__,
            )
        )
        raise

    get_model_execution_observer().record_model_call(
        ModelCallObservation(
            provider=provider,
            model_name=model_name,
            status=ModelExecutionEventStatus.OK,
            prompt_chars=prompt_chars,
            response_chars=len(response_text),
        )
    )
    get_token_tracker().record(provider, usage)
    return response_text
