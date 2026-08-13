import json
import logging
from collections.abc import Iterator
from typing import Any

from infrastructure.models.providers.ollama import OllamaNotReadyError

logger = logging.getLogger("infrastructure.models.providers.streaming")


def stream_ollama_api(
    ollama_host: str,
    model_name: str,
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int,
) -> Iterator[str]:
    import httpx

    url = f"{ollama_host.rstrip('/')}/api/chat"
    payload = {
        "model": model_name,
        "messages": messages,
        "stream": True,
        "think": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }

    try:
        with httpx.stream("POST", url, json=payload, timeout=300) as response:
            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        logger.error("Ollama 流式调用异常: %s", e)
        raise OllamaNotReadyError(
            f"❌ 物理层无法连通本地 Ollama 算力服务 (Ollama host: {ollama_host})，错误信息: {e}"
        ) from e


def stream_openai_compatible_api(
    api_base: str,
    api_key: str,
    model_name: str,
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int,
    provider: str = "unknown",
) -> Iterator[str]:
    import httpx

    if not api_base:
        raise ValueError(f"❌ 未找到大模型服务商 '{provider}' 的有效 API Base 配置！")

    url = f"{api_base.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }

    try:
        with httpx.stream(
            "POST", url, json=payload, headers=headers, timeout=60
        ) as response:
            for line in response.iter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        logger.error("云端大模型流式 API 调用异常: %s", e)
        raise RuntimeError(
            f"❌ 物理层无法连通云端大模型服务接口 ({provider}): {e}"
        ) from e


def stream_anthropic_api(
    api_base: str,
    api_key: str,
    model_name: str,
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int,
) -> Iterator[str]:
    import httpx

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
        "stream": True,
    }
    if system_prompt.strip():
        payload["system"] = system_prompt.strip()

    try:
        with httpx.stream(
            "POST", url, json=payload, headers=headers, timeout=60
        ) as response:
            for line in response.iter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    try:
                        chunk = json.loads(data_str)
                        if chunk.get("type") == "content_block_delta":
                            text = chunk.get("delta", {}).get("text", "")
                            if text:
                                yield text
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        logger.error("Anthropic 流式 API 调用异常: %s", e)
        raise RuntimeError(f"❌ 物理层无法连通 Anthropic 服务: {e}") from e


STREAM_DISPATCH = {
    "ollama": stream_ollama_api,
    "chat_completions": stream_openai_compatible_api,
    "anthropic_messages": stream_anthropic_api,
}
