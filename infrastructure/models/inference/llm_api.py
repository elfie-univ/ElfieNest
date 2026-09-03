from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Callable, Mapping, cast

from elfie.brain.reasoning.skill_port import SKILL_LOADER_NAME, SkillLoadCall
from elfie.brain.reasoning.tool_port import ToolCall
from infrastructure.models.inference.token_usage import get_token_tracker
from infrastructure.models.model_execution_config import ModelExecutionConfig
from infrastructure.models.model_execution_observations import (
    ModelCallObservation,
    ModelExecutionEventStatus,
    current_model_call_context,
    get_model_execution_observer,
)
from infrastructure.models.provider_errors import (
    ProviderCallError,
    classify_provider_error,
)
from infrastructure.models.providers.dispatch import (
    API_DISPATCH,
    call_openai_compatible_api,
    detect_api_mode_for_url,
)
from infrastructure.models.providers.request_profiles import (
    RequestProfile,
    default_request_profile_id,
    get_request_profile,
)

_TRACE_TEXT_LIMIT = 8_000
_TRACE_ITEM_LIMIT = 32
_SENSITIVE_TRACE_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "access_token",
        "refresh_token",
        "password",
        "secret",
        "credential",
    }
)


@dataclass(frozen=True)
class LLMCallResult:
    """Text plus non-content metadata needed by controlled probes."""

    text: str
    usage: Mapping[str, Any]
    metadata: Mapping[str, Any]
    tool_calls: tuple[ToolCall, ...] = ()
    skill_calls: tuple[SkillLoadCall, ...] = ()


def call_llm_api_result(
    config: ModelExecutionConfig,
    provider: str,
    model_name: str,
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int,
    *,
    thinking: bool = False,
    request_options: dict[str, Any] | None = None,
    timeout_seconds: float | None = None,
    capture_metadata: bool = True,
    response_capture: dict[str, Any] | None = None,
) -> LLMCallResult:
    provider_cfg: dict[str, Any] = config.providers.get(provider, {})
    api_key = provider_cfg.get("api_key", "")
    api_base = provider_cfg.get("api_base", "")
    api_mode = provider_cfg.get("api_mode", "") or detect_api_mode_for_url(api_base)
    args: tuple[Any, ...]
    prompt_chars = sum(len(str(message.get("content", ""))) for message in messages)
    started = perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    context = current_model_call_context()
    connection_id = (context.connection_id if context else None) or provider
    endpoint_model_id = (context.endpoint_model_id if context else None) or model_name
    workload_kind = (context.workload_kind if context else "validation") or "unknown"
    config_fingerprint = _provider_config_fingerprint(provider_cfg, model_name)

    metadata: Mapping[str, Any] = {}
    try:
        request_profile = _resolve_request_profile(provider_cfg, model_name, api_mode)
        effective_messages = _adapt_messages(messages, request_profile)
        effective_request_options = _adapt_request_options(
            request_options,
            request_profile,
        )
        if response_capture is not None:
            response_capture["request"] = {
                "messages": _trace_value(effective_messages),
                "options": _trace_value(effective_request_options or {}),
            }
        dispatch_fn = cast(
            Callable[..., Any],
            API_DISPATCH.get(request_profile.api_mode, call_openai_compatible_api),
        )
        if request_profile.api_mode == "ollama":
            args = (
                api_base or config.ollama_host,
                model_name,
                effective_messages,
                temperature,
                max_tokens,
            )
        elif request_profile.api_mode == "anthropic_messages":
            args = (
                api_base,
                api_key,
                model_name,
                effective_messages,
                temperature,
                max_tokens,
            )
        elif request_profile.api_mode == "codex_responses":
            dispatch_result = _invoke_dispatch(
                dispatch_fn,
                (
                    api_base,
                    api_key,
                    model_name,
                    effective_messages,
                    temperature,
                    max_tokens,
                    provider,
                ),
                {
                    "request_options": (
                        dict(effective_request_options)
                        if effective_request_options
                        else None
                    ),
                    "credential_ref": str(provider_cfg.get("credential_ref") or ""),
                    "account_id": (
                        str(provider_cfg["account_id"])
                        if provider_cfg.get("account_id")
                        else None
                    ),
                    "oauth_credentials": config.oauth_credentials,
                    "timeout_seconds": timeout_seconds,
                    "response_capture": response_capture,
                    "return_metadata": capture_metadata,
                },
            )
            response_text, usage, metadata = _unpack_dispatch_result(dispatch_result)
            args = ()
        else:
            args = (
                api_base,
                api_key,
                model_name,
                effective_messages,
                temperature,
                max_tokens,
                provider,
            )
        if request_profile.api_mode == "codex_responses":
            pass
        elif request_profile.api_mode == "ollama":
            dispatch_result = _invoke_dispatch(
                dispatch_fn,
                args,
                {
                    "thinking": thinking,
                    "request_options": (
                        dict(effective_request_options)
                        if effective_request_options
                        else None
                    ),
                    "timeout_seconds": timeout_seconds,
                    "response_capture": response_capture,
                    "return_metadata": capture_metadata,
                },
            )
            response_text, usage, metadata = _unpack_dispatch_result(dispatch_result)
        elif (
            effective_request_options
            or response_capture is not None
            or timeout_seconds is not None
        ):
            dispatch_options: dict[str, Any] = {}
            if effective_request_options:
                dispatch_options["request_options"] = dict(effective_request_options)
            if timeout_seconds is not None:
                dispatch_options["timeout_seconds"] = timeout_seconds
            if capture_metadata:
                dispatch_options["return_metadata"] = True
            if response_capture is not None:
                dispatch_options["response_capture"] = response_capture
            response_text, usage, metadata = _unpack_dispatch_result(
                _invoke_dispatch(dispatch_fn, args, dispatch_options)
            )
        else:
            response_text, usage, metadata = _unpack_dispatch_result(
                _invoke_dispatch(
                    dispatch_fn,
                    args,
                    {
                        "response_capture": response_capture,
                        "return_metadata": capture_metadata,
                    },
                )
            )
    except Exception as failure:
        finished_at = datetime.now(timezone.utc).isoformat()
        classification = classify_provider_error(failure)
        get_model_execution_observer().record_model_call(
            ModelCallObservation(
                provider=provider,
                model_name=model_name,
                status=ModelExecutionEventStatus.ERROR,
                prompt_chars=prompt_chars,
                error_type=type(failure).__name__,
                error_code=classification.code,
                error_scope=classification.scope,
                error_category=classification.category,
                connection_id=connection_id,
                endpoint_model_id=endpoint_model_id,
                food_id=context.food_id if context else None,
                semantic_role=context.semantic_role if context else None,
                route_stage=context.route_stage if context else None,
                workload_kind=workload_kind,
                scope_id=context.scope_id if context else None,
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=(perf_counter() - started) * 1000.0,
                config_fingerprint=config_fingerprint,
            )
        )
        raise

    if response_capture is not None:
        response_capture["response"] = {
            "text": _trace_value(response_text),
            "usage": _trace_value(usage),
            "metadata": _trace_value(metadata),
        }
    finished_at = datetime.now(timezone.utc).isoformat()
    get_model_execution_observer().record_model_call(
        ModelCallObservation(
            provider=provider,
            model_name=model_name,
            status=ModelExecutionEventStatus.OK,
            prompt_chars=prompt_chars,
            response_chars=len(response_text),
            connection_id=connection_id,
            endpoint_model_id=endpoint_model_id,
            food_id=context.food_id if context else None,
            semantic_role=context.semantic_role if context else None,
            route_stage=context.route_stage if context else None,
            workload_kind=workload_kind,
            scope_id=context.scope_id if context else None,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=(perf_counter() - started) * 1000.0,
            time_to_first_token_ms=(
                float(metadata["time_to_first_token_ms"])
                if isinstance(metadata.get("time_to_first_token_ms"), (int, float))
                and not isinstance(metadata.get("time_to_first_token_ms"), bool)
                else None
            ),
            config_fingerprint=config_fingerprint,
            prompt_tokens=_usage_count(
                usage, "prompt_tokens", "input_tokens", "prompt_eval_count"
            ),
            completion_tokens=_usage_count(
                usage, "completion_tokens", "output_tokens", "eval_count"
            ),
            tool_called=metadata.get("tool_called") is True,
            reasoning_observed=metadata.get("reasoning_observed") is True,
        )
    )
    get_token_tracker().record(provider, usage)
    tool_calls, skill_calls = _coerce_calls(metadata.get("tool_calls"))
    return LLMCallResult(
        response_text,
        usage,
        metadata,
        tool_calls,
        skill_calls,
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
    timeout_seconds: float | None = None,
) -> str:
    """Return only text for the existing execution callers."""
    return call_llm_api_result(
        config,
        provider,
        model_name,
        messages,
        temperature,
        max_tokens,
        thinking=thinking,
        request_options=request_options,
        timeout_seconds=timeout_seconds,
        capture_metadata=True,
    ).text


def call_llm_api_with_trace(
    config: ModelExecutionConfig,
    provider: str,
    model_name: str,
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int,
    *,
    thinking: bool = False,
    request_options: dict[str, Any] | None = None,
    timeout_seconds: float | None = None,
) -> tuple[str, Mapping[str, Any]]:
    """Call one model and retain only capability-safe response metadata."""
    capture: dict[str, Any] = {}
    result = call_llm_api_result(
        config,
        provider,
        model_name,
        messages,
        temperature,
        max_tokens,
        thinking=thinking,
        request_options=request_options,
        timeout_seconds=timeout_seconds,
        capture_metadata=True,
        response_capture=capture,
    )
    return result.text, {**dict(result.metadata), **capture}


def _unpack_dispatch_result(
    result: Any,
) -> tuple[str, dict[str, Any], Mapping[str, Any]]:
    if not isinstance(result, tuple) or len(result) not in {2, 3}:
        raise TypeError("Provider adapter returned an invalid response tuple")
    text = str(result[0])
    usage = result[1] if isinstance(result[1], dict) else {}
    metadata = result[2] if len(result) == 3 and isinstance(result[2], Mapping) else {}
    return text, usage, metadata


def _coerce_calls(
    raw_calls: Any,
) -> tuple[tuple[ToolCall, ...], tuple[SkillLoadCall, ...]]:
    """Validate normalized Provider calls before they cross into Brain."""
    if raw_calls is None:
        return (), ()
    if not isinstance(raw_calls, (list, tuple)):
        raise TypeError("Provider tool_calls must be a list")
    calls: list[ToolCall] = []
    skill_calls: list[SkillLoadCall] = []
    for raw_call in raw_calls:
        if not isinstance(raw_call, Mapping):
            raise TypeError("Provider tool call must be an object")
        call_id = raw_call.get("call_id")
        tool_key = raw_call.get("name") or raw_call.get("tool_key")
        arguments = raw_call.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError as error:
                raise ValueError(
                    "Provider tool arguments are not valid JSON"
                ) from error
        if not isinstance(arguments, Mapping):
            raise TypeError("Provider tool arguments must be a JSON object")
        normalized_call_id = str(call_id or "tool_call")
        normalized_tool_key = str(tool_key or "")
        normalized_arguments = dict(arguments)
        if normalized_tool_key == SKILL_LOADER_NAME:
            skill_name = normalized_arguments.get("name")
            if not isinstance(skill_name, str):
                raise TypeError("Skill loader requires a string name")
            skill_calls.append(
                SkillLoadCall(
                    call_id=normalized_call_id,
                    skill_name=skill_name,
                    arguments=normalized_arguments,
                )
            )
        else:
            calls.append(
                ToolCall(
                    call_id=normalized_call_id,
                    tool_key=normalized_tool_key,
                    arguments=normalized_arguments,
                )
            )
    return tuple(calls), tuple(skill_calls)


def _trace_value(value: Any, *, depth: int = 0) -> Any:
    """Return a bounded, secret-free value suitable for a local execution trace."""
    if depth >= 5:
        return "[trace depth truncated]"
    if isinstance(value, Mapping):
        traced: dict[str, Any] = {}
        for index, (raw_key, raw_value) in enumerate(value.items()):
            if index >= _TRACE_ITEM_LIMIT:
                traced["[items_truncated]"] = True
                break
            key = str(raw_key)
            normalized_key = key.lower().replace("-", "_")
            if normalized_key in _SENSITIVE_TRACE_KEYS:
                traced[key] = "[redacted]"
            else:
                traced[key] = _trace_value(raw_value, depth=depth + 1)
        return traced
    if isinstance(value, (list, tuple)):
        items = [
            _trace_value(item, depth=depth + 1) for item in value[:_TRACE_ITEM_LIMIT]
        ]
        if len(value) > _TRACE_ITEM_LIMIT:
            items.append("[items_truncated]")
        return items
    if isinstance(value, str):
        if len(value) <= _TRACE_TEXT_LIMIT:
            return value
        return f"{value[:_TRACE_TEXT_LIMIT]}...[text_truncated]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def _invoke_dispatch(
    dispatch_fn: Callable[..., Any],
    args: tuple[Any, ...],
    options: Mapping[str, Any],
) -> Any:
    """Invoke an adapter using only keywords in its declared call surface."""
    parameters: Mapping[str, inspect.Parameter]
    try:
        parameters = inspect.signature(dispatch_fn).parameters
    except (TypeError, ValueError):
        parameters = {}
    accepts_var_keywords = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )
    if accepts_var_keywords or not parameters:
        filtered = dict(options)
    else:
        filtered = {key: value for key, value in options.items() if key in parameters}
    return dispatch_fn(*args, **filtered)


def _usage_count(usage: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = usage.get(key)
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return max(0, int(value))
    return None


def _resolve_request_profile(
    provider_cfg: Mapping[str, Any],
    model_name: str,
    api_mode: str,
) -> RequestProfile:
    """Resolve and validate the typed profile for this exact endpoint model."""
    raw_profiles = provider_cfg.get("model_profiles")
    raw_model_profile = (
        raw_profiles.get(model_name) if isinstance(raw_profiles, Mapping) else None
    )
    profile_values = (
        raw_model_profile if isinstance(raw_model_profile, Mapping) else provider_cfg
    )
    profile_id = profile_values.get("request_profile_id")
    if not isinstance(profile_id, str) or not profile_id.strip():
        try:
            profile_id = default_request_profile_id(api_mode)
        except ValueError as error:
            raise ProviderCallError(
                "Provider API mode 没有对应的 Request Profile",
                code="request_profile_invalid",
                scope="endpoint",
                category="configuration",
            ) from error
    raw_version = profile_values.get("request_profile_version")
    version = (
        raw_version
        if isinstance(raw_version, int) and not isinstance(raw_version, bool)
        else None
    )
    try:
        profile = get_request_profile(profile_id.strip(), version)
    except (TypeError, ValueError) as error:
        raise ProviderCallError(
            "Provider 的 Request Profile 配置无效",
            code="request_profile_invalid",
            scope="endpoint",
            category="configuration",
        ) from error
    if profile.api_mode != api_mode:
        raise ProviderCallError(
            "Provider 的 Request Profile 与 API mode 不匹配",
            code="request_profile_invalid",
            scope="endpoint",
            category="configuration",
        )
    return profile


def _adapt_request_options(
    options: dict[str, Any] | None,
    profile: RequestProfile,
) -> dict[str, Any] | None:
    """Map semantic option aliases to the selected Provider adapter spelling."""
    if not options:
        return None
    adapted = dict(options)
    reasoning_mode = adapted.pop("reasoning_mode", None)
    if reasoning_mode is not None and profile.reasoning_parameter:
        if profile.api_mode == "anthropic_messages":
            budget = {"fast": 512, "medium": 1024, "deep": 2048}.get(
                str(reasoning_mode),
                1024,
            )
            adapted[profile.reasoning_parameter] = {
                "type": "enabled",
                "budget_tokens": budget,
            }
        elif profile.api_mode == "codex_responses":
            adapted[profile.reasoning_parameter] = {"effort": reasoning_mode}
        else:
            adapted[profile.reasoning_parameter] = reasoning_mode
    tool_definitions = adapted.pop("tool_definitions", None)
    if tool_definitions is not None and profile.tools_field:
        adapted[profile.tools_field] = _adapt_tool_definitions(
            tool_definitions,
            profile,
        )
    image_content = adapted.pop("image_content", None)
    if image_content is not None and profile.vision_encoding:
        adapted[profile.vision_encoding] = image_content
    return adapted


def _adapt_tool_definitions(
    definitions: Any,
    profile: RequestProfile,
) -> Any:
    if profile.api_mode != "anthropic_messages" or not isinstance(definitions, list):
        return definitions
    adapted: list[Any] = []
    for item in definitions:
        if not isinstance(item, Mapping):
            adapted.append(item)
            continue
        function = item.get("function")
        if not isinstance(function, Mapping):
            adapted.append(item)
            continue
        adapted.append(
            {
                "name": function.get("name"),
                "description": function.get("description", ""),
                "input_schema": function.get(
                    "parameters",
                    {"type": "object", "properties": {}},
                ),
            }
        )
    return adapted


def _adapt_messages(
    messages: list[dict[str, Any]],
    profile: RequestProfile,
) -> list[dict[str, Any]]:
    """Convert the shared multimodal message shape at the protocol boundary."""
    if profile.api_mode == "chat_completions":
        return messages
    adapted: list[dict[str, Any]] = []
    for message in messages:
        current = dict(message)
        content = current.get("content")
        if not isinstance(content, list):
            adapted.append(current)
            continue
        if profile.api_mode == "anthropic_messages":
            current["content"] = _anthropic_content(content)
        elif profile.api_mode == "codex_responses":
            current["content"] = _codex_content(content)
        elif profile.api_mode == "ollama":
            text_parts: list[str] = []
            images: list[str] = list(current.get("images") or [])
            for part in content:
                if not isinstance(part, Mapping):
                    continue
                if part.get("type") == "text" and isinstance(part.get("text"), str):
                    text_parts.append(part["text"])
                elif part.get("type") == "image_url":
                    image_url = part.get("image_url")
                    url = (
                        image_url.get("url") if isinstance(image_url, Mapping) else None
                    )
                    encoded = _data_url_payload(url)
                    if encoded is not None:
                        images.append(encoded)
            current["content"] = "\n".join(text_parts)
            if images:
                current["images"] = images
        adapted.append(current)
    return adapted


def _anthropic_content(content: list[Any]) -> list[Any]:
    result: list[Any] = []
    for part in content:
        if not isinstance(part, Mapping) or part.get("type") != "image_url":
            result.append(part)
            continue
        image_url = part.get("image_url")
        url = image_url.get("url") if isinstance(image_url, Mapping) else None
        payload = _data_url_payload(url)
        media_type = _data_url_media_type(url) or "image/png"
        if payload is None:
            result.append(part)
            continue
        result.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": payload,
                },
            }
        )
    return result


def _codex_content(content: list[Any]) -> list[Any]:
    result: list[Any] = []
    for part in content:
        if not isinstance(part, Mapping):
            result.append(part)
            continue
        if part.get("type") == "text":
            result.append({"type": "input_text", "text": part.get("text", "")})
        elif part.get("type") == "image_url":
            image_url = part.get("image_url")
            url = image_url.get("url") if isinstance(image_url, Mapping) else None
            result.append({"type": "input_image", "image_url": url})
        else:
            result.append(part)
    return result


def _data_url_payload(value: Any) -> str | None:
    if not isinstance(value, str) or not value.startswith("data:"):
        return None
    _, separator, payload = value.partition(",")
    return payload if separator and payload else None


def _data_url_media_type(value: Any) -> str | None:
    if not isinstance(value, str) or not value.startswith("data:"):
        return None
    header, separator, _ = value.partition(",")
    if not separator:
        return None
    media_type = header[5:].split(";", 1)[0].strip()
    return media_type or None


def _provider_config_fingerprint(
    provider_cfg: Mapping[str, Any],
    model_name: str,
) -> str:
    """Hash effective non-secret routing inputs; never persist raw config."""
    configured = provider_cfg.get("config_fingerprint")
    if isinstance(configured, str) and configured:
        return configured
    stable_keys = (
        "catalog_id",
        "api_base",
        "api_mode",
        "auth_type",
        "request_profile_id",
        "request_profile_version",
        "discovery_strategy",
        "models",
        "model_profiles",
    )
    payload: dict[str, Any] = {"model": model_name}
    payload.update(
        {key: provider_cfg.get(key) for key in stable_keys if key in provider_cfg}
    )
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
