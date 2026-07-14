from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from runtime.providers.ollama import OllamaNotReadyError

logger = logging.getLogger("runtime.providers.dispatch")


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
    request_options: dict[str, Any] | None = None,
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
            "think": False,
        },
    }
    _merge_request_options(payload, request_options)
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            usage: dict[str, Any] = {}
            if "eval_count" in res_data:
                usage = {
                    "prompt_tokens": res_data.get("prompt_eval_count", 0),
                    "completion_tokens": res_data.get("eval_count", 0),
                }
            return res_data["message"]["content"], usage
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
) -> tuple[str, dict[str, Any]]:
    if not api_base:
        raise ValueError(f"❌ 未找到大模型服务商 '{provider}' 的有效 API Base 配置！")

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
        with urllib.request.urlopen(req, timeout=60) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            usage = res_data.get("usage", {})
            return res_data["choices"][0]["message"]["content"], usage
    except Exception as e:
        logger.error("云端大模型 API 调用异常: %s", e)
        if isinstance(e, urllib.error.HTTPError):
            err_msg = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(
                f"❌ 云端大模型接口 ({provider}) 返回 HTTP {e.code} 错误。响应详情: {err_msg}"
            ) from e
        raise RuntimeError(
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
        with urllib.request.urlopen(req, timeout=60) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            usage = res_data.get("usage", {})
            return res_data["content"][0]["text"], usage
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(
            f"❌ Anthropic API 返回 HTTP {e.code} 错误。响应详情: {err_msg}"
        ) from e
    except Exception as e:
        raise RuntimeError(f"❌ 物理层无法连通 Anthropic 服务: {e}") from e


API_DISPATCH = {
    "ollama": call_ollama_api,
    "chat_completions": call_openai_compatible_api,
    "anthropic_messages": call_anthropic_api,
}


_RESERVED_REQUEST_FIELDS = frozenset(
    {"model", "messages", "system", "stream", "temperature", "max_tokens"}
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
