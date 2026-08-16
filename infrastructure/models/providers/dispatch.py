from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, cast

from infrastructure.models.oauth_credentials import OAuthCredentialPort, OAuthToken
from infrastructure.models.provider_errors import (
    ProviderCallError,
    provider_error_from_http,
    provider_network_error,
)
from infrastructure.models.providers.http import (
    ProviderHttpResponse,
    open_provider_request,
    read_provider_response,
)
from infrastructure.models.providers.ollama import OllamaNotReadyError
from infrastructure.models.providers.openai_chatgpt import (
    refresh_openai_chatgpt_token,
)

logger = logging.getLogger("infrastructure.models.providers.dispatch")

_MAX_ERROR_RESPONSE_BYTES = 64 * 1024
_ERROR_RESPONSE_DEADLINE_SECONDS = 5.0


def detect_api_mode_for_url(base_url: str) -> str:
    url = base_url.lower().rstrip("/")
    if "anthropic.com" in url:
        return "anthropic_messages"
    if "localhost:11434" in url or "/api/chat" in url:
        return "ollama"
    return "chat_completions"


def call_ollama_api(
    ollama_host: str,
    model_name: str,
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int,
    *,
    thinking: bool = False,
    request_options: dict[str, Any] | None = None,
    response_capture: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    url = f"{ollama_host}/api/chat"
    payload = {
        "model": model_name,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    _merge_request_options(payload, request_options)
    payload["think"] = thinking
    options = payload.get("options")
    if isinstance(options, dict):
        options.pop("think", None)
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with open_provider_request(req, timeout=300) as response:
            res_data = json.loads(
                read_provider_response(
                    response,
                    max_bytes=8 * 1024 * 1024,
                    deadline_seconds=300,
                ).decode("utf-8")
            )
            usage: dict[str, Any] = {}
            if "eval_count" in res_data:
                usage = {
                    "prompt_tokens": res_data.get("prompt_eval_count", 0),
                    "completion_tokens": res_data.get("eval_count", 0),
                }
            message = res_data["message"]
            if response_capture is not None:
                _capture_message(response_capture, message)
            return message["content"], usage
    except Exception as e:
        logger.error("本地 Ollama 调用异常: %s", e)
        raise OllamaNotReadyError(
            f"❌ 物理层无法连通本地 Ollama 算力服务 (Ollama host: {ollama_host})，错误信息: {e}"
        ) from e


def call_openai_compatible_api(
    api_base: str,
    api_key: str,
    model_name: str,
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int,
    provider: str = "unknown",
    *,
    request_options: dict[str, Any] | None = None,
    timeout_seconds: float | None = None,
    response_capture: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    if not api_base:
        raise ProviderCallError(
            f"❌ 未找到大模型服务商 '{provider}' 的有效 API Base 配置！",
            code="provider_base_missing",
            scope="connection",
            category="configuration",
        )

    headers: dict[str, str] = {"Content-Type": "application/json"}
    url = f"{api_base}/chat/completions"
    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    _merge_request_options(payload, request_options)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        request_timeout = timeout_seconds if timeout_seconds is not None else 60.0
        with open_provider_request(req, timeout=request_timeout) as response:
            res_data = json.loads(
                read_provider_response(
                    response,
                    max_bytes=8 * 1024 * 1024,
                    deadline_seconds=request_timeout,
                ).decode("utf-8")
            )
            usage = res_data.get("usage", {})
            message = res_data["choices"][0]["message"]
            if response_capture is not None:
                _capture_message(response_capture, message)
            content = message.get("content")
            if not isinstance(content, str) or not content.strip():
                reasoning_content = message.get("reasoning_content")
                content = (
                    reasoning_content if isinstance(reasoning_content, str) else ""
                )
            return content, usage
    except Exception as e:
        logger.error("Cloud LLM API call exception: %s", e)
        if isinstance(e, urllib.error.HTTPError):
            err_msg = _http_error_summary(e)
            raise provider_error_from_http(
                e,
                f"❌ 云端大模型接口 ({provider}) 返回 HTTP {e.code} 错误。响应详情: {err_msg}",
            ) from e
        raise provider_network_error(
            f"❌ 物理层无法连通云端大模型服务接口 ({provider}): {e}"
        ) from e


def call_anthropic_api(
    api_base: str,
    api_key: str,
    model_name: str,
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int,
    *,
    request_options: dict[str, Any] | None = None,
    response_capture: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    url = f"{api_base.rstrip('/')}/messages"
    system_prompt = ""
    filtered_messages = []
    for msg in messages:
        if msg.get("role") == "system":
            system_prompt += msg.get("content", "") + "\n"
        else:
            filtered_messages.append(msg)

    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    payload: dict[str, Any] = {
        "model": model_name,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": filtered_messages,
    }
    if system_prompt.strip():
        payload["system"] = system_prompt.strip()
    _merge_request_options(payload, request_options)

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with open_provider_request(req, timeout=60) as response:
            res_data = json.loads(
                read_provider_response(
                    response,
                    max_bytes=8 * 1024 * 1024,
                    deadline_seconds=60,
                ).decode("utf-8")
            )
            usage = res_data.get("usage", {})
            blocks = res_data.get("content", [])
            text_parts = []
            tool_use_count = 0
            reasoning_present = False
            if isinstance(blocks, list):
                for block in blocks:
                    if not isinstance(block, dict):
                        continue
                    if isinstance(block.get("text"), str):
                        text_parts.append(block["text"])
                    if block.get("type") == "tool_use":
                        tool_use_count += 1
                    if block.get("type") in {"thinking", "redacted_thinking"}:
                        reasoning_present = True
            if response_capture is not None:
                response_capture.update(
                    {
                        "tool_call_count": tool_use_count,
                        "reasoning_present": reasoning_present,
                    }
                )
            return "".join(text_parts), usage
    except urllib.error.HTTPError as e:
        err_msg = _http_error_summary(e)
        raise provider_error_from_http(
            e,
            f"❌ Anthropic API 返回 HTTP {e.code} 错误。响应详情: {err_msg}",
        ) from e
    except Exception as e:
        raise provider_network_error(f"❌ 物理层无法连通 Anthropic 服务: {e}") from e


def call_codex_responses_api(
    api_base: str,
    api_key: str,
    model_name: str,
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int,
    provider: str = "openai_chatgpt",
    *,
    request_options: dict[str, Any] | None = None,
    credential_ref: str = "",
    account_id: str | None = None,
    oauth_credentials: OAuthCredentialPort | None = None,
    response_capture: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Call the ChatGPT Codex Responses transport with a refreshable user token."""
    _ = temperature, max_tokens
    token: OAuthToken | None = None
    if oauth_credentials is not None and credential_ref:
        token = oauth_credentials.load(credential_ref)
        if token is not None and _token_expired(token.expires_at):
            token = refresh_openai_chatgpt_token(token, oauth_credentials)
    access_token = token.access_token if token is not None else api_key
    account_id = token.account_id if token is not None else account_id
    if not access_token:
        raise ProviderCallError(
            "ChatGPT 授权已失效，请重新登录",
            code="invalid_credential",
            scope="connection",
            category="authentication",
        )
    instructions = "\n\n".join(
        str(item.get("content") or "")
        for item in messages
        if item.get("role") == "system"
    ).strip()
    payload: dict[str, Any] = {
        "model": model_name,
        "input": [item for item in messages if item.get("role") != "system"],
        "stream": True,
        "store": False,
    }
    if instructions:
        payload["instructions"] = instructions
    _merge_codex_request_options(payload, request_options)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "originator": "elfienest",
        "User-Agent": "ElfieNest/0.1",
        "session-id": uuid.uuid4().hex,
    }
    if account_id:
        headers["ChatGPT-Account-Id"] = account_id
    url = f"{api_base.rstrip('/')}/responses"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with open_provider_request(request, timeout=300) as response:
            raw = read_provider_response(
                response, max_bytes=32 * 1024 * 1024, deadline_seconds=300
            ).decode("utf-8")
        return _parse_codex_response(raw, response_capture=response_capture)
    except urllib.error.HTTPError as error:
        summary = _http_error_summary(error)
        raise provider_error_from_http(
            error,
            f"❌ ChatGPT Codex 接口返回 HTTP {error.code} 错误。响应详情: {summary}",
        ) from error
    except Exception as error:
        if isinstance(error, (ProviderCallError, ValueError)):
            raise
        raise provider_network_error(
            f"❌ 物理层无法连通 ChatGPT Codex 服务 ({provider}): {error}"
        ) from error


API_DISPATCH = {
    "ollama": call_ollama_api,
    "chat_completions": call_openai_compatible_api,
    "anthropic_messages": call_anthropic_api,
    "codex_responses": call_codex_responses_api,
}


_RESERVED_REQUEST_FIELDS = frozenset(
    {
        "model",
        "messages",
        "system",
        "stream",
        "temperature",
        "max_tokens",
    }
)


def _merge_request_options(
    payload: dict[str, Any], request_options: dict[str, Any] | None
) -> None:
    """合并粮食内的 Provider 参数，同时保护调用核心字段。"""
    if not request_options:
        return
    for key, value in request_options.items():
        if key in _RESERVED_REQUEST_FIELDS:
            continue
        if key == "options" and isinstance(value, dict):
            existing = payload.get("options")
            merged = dict(existing) if isinstance(existing, dict) else {}
            merged.update(value)
            payload["options"] = merged
        else:
            payload[key] = value


def _merge_codex_request_options(
    payload: dict[str, Any], request_options: dict[str, Any] | None
) -> None:
    if not request_options:
        return
    response_format = request_options.get("response_format")
    if isinstance(response_format, dict):
        format_value = dict(response_format)
        json_schema = format_value.pop("json_schema", None)
        if isinstance(json_schema, dict):
            format_value.update(json_schema)
        payload["text"] = {"format": format_value}
    tools = request_options.get("tools")
    if isinstance(tools, list):
        payload["tools"] = [
            {"type": "function", **item["function"]}
            if isinstance(item, dict)
            and item.get("type") == "function"
            and isinstance(item.get("function"), dict)
            else item
            for item in tools
        ]
    if "tool_choice" in request_options:
        choice = request_options["tool_choice"]
        if (
            isinstance(choice, dict)
            and choice.get("type") == "function"
            and isinstance(choice.get("function"), dict)
        ):
            payload["tool_choice"] = {
                "type": "function",
                "name": choice["function"].get("name"),
            }
        else:
            payload["tool_choice"] = choice


def _parse_codex_response(
    raw: str,
    *,
    response_capture: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    stripped = raw.lstrip()
    if stripped.startswith("{"):
        payload = json.loads(stripped)
        if response_capture is not None:
            _capture_responses_output(response_capture, payload)
        return _responses_text(payload), _responses_usage(payload)
    deltas: list[str] = []
    function_deltas: list[str] = []
    completed: dict[str, Any] | None = None
    for line in raw.splitlines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        event = json.loads(data)
        if event.get("type") == "response.output_text.delta":
            deltas.append(str(event.get("delta") or ""))
        if event.get("type") == "response.function_call_arguments.delta":
            function_deltas.append(str(event.get("delta") or ""))
            if response_capture is not None:
                response_capture["tool_call_count"] = 1
        if event.get("type", "").startswith("response.reasoning"):
            if response_capture is not None:
                response_capture["reasoning_present"] = True
        if event.get("type") == "response.completed" and isinstance(
            event.get("response"), dict
        ):
            completed = event["response"]
    if completed is not None:
        if response_capture is not None:
            _capture_responses_output(response_capture, completed)
        text = (
            "".join(deltas)
            or "".join(function_deltas)
            or _responses_text(completed)
            or _responses_function_arguments(completed)
        )
        return text, _responses_usage(completed)
    if deltas:
        return "".join(deltas), {}
    if function_deltas:
        return "".join(function_deltas), {}
    raise ValueError("ChatGPT Codex 响应没有返回文本")


def _responses_text(payload: Mapping[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str):
        return direct
    parts: list[str] = []
    output = payload.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    parts.append(part["text"])
    return "".join(parts)


def _responses_function_arguments(payload: Mapping[str, Any]) -> str:
    output = payload.get("output")
    if not isinstance(output, list):
        return ""
    for item in output:
        if (
            isinstance(item, dict)
            and item.get("type") == "function_call"
            and isinstance(item.get("arguments"), str)
        ):
            return item["arguments"]
    return ""


def _responses_usage(payload: Mapping[str, Any]) -> dict[str, Any]:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return {}
    return {
        "prompt_tokens": usage.get("input_tokens", 0),
        "completion_tokens": usage.get("output_tokens", 0),
    }


def _capture_message(capture: dict[str, Any], message: Any) -> None:
    if not isinstance(message, Mapping):
        return
    tool_calls = message.get("tool_calls")
    capture["tool_call_count"] = len(tool_calls) if isinstance(tool_calls, list) else 0
    capture["reasoning_present"] = bool(
        message.get("reasoning_content")
        or message.get("reasoning")
        or message.get("thinking")
    )
    if isinstance(message.get("finish_reason"), str):
        capture["finish_reason"] = message["finish_reason"]


def _capture_responses_output(capture: dict[str, Any], payload: Mapping[str, Any]) -> None:
    output = payload.get("output")
    if not isinstance(output, list):
        return
    tool_calls = sum(
        1
        for item in output
        if isinstance(item, Mapping) and item.get("type") == "function_call"
    )
    capture["tool_call_count"] = tool_calls
    capture["reasoning_present"] = any(
        isinstance(item, Mapping) and item.get("type") == "reasoning"
        for item in output
    )


def _token_expired(expires_at: str | None) -> bool:
    if not expires_at:
        return False
    try:
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        return expiry <= datetime.now(timezone.utc)
    except ValueError:
        return True


def _http_error_summary(error: urllib.error.HTTPError) -> str:
    try:
        payload = read_provider_response(
            cast(ProviderHttpResponse, error),
            max_bytes=_MAX_ERROR_RESPONSE_BYTES,
            deadline_seconds=_ERROR_RESPONSE_DEADLINE_SECONDS,
        )
    except ValueError:
        return "[Provider 错误响应体超过安全上限，内容已丢弃]"
    except TimeoutError:
        return "[Provider 错误响应体读取超时，内容已丢弃]"
    return payload.decode("utf-8", errors="replace")
