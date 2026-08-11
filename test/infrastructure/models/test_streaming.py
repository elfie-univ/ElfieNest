"""Provider SSE streaming parser tests."""

import json
from unittest.mock import patch

import pytest

from infrastructure.models.providers.ollama import OllamaNotReadyError
from infrastructure.models.providers.streaming import (
    STREAM_DISPATCH as _STREAM_DISPATCH,
)
from infrastructure.models.providers.streaming import (
    stream_anthropic_api as _stream_anthropic_api,
)
from infrastructure.models.providers.streaming import (
    stream_ollama_api as _stream_ollama_api,
)
from infrastructure.models.providers.streaming import (
    stream_openai_compatible_api as _stream_openai_compatible_api,
)


class MockHttpResponse:
    """Mock httpx stream response"""

    def __init__(self, lines):
        self.lines = lines

    def iter_lines(self):
        return iter(self.lines)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class TestStreamOllamaApi:
    """Ollama 流式 API 测试"""

    def test_yields_text_chunks_from_sse_lines(self):
        """Ollama 流式 API 应正确解析并 yield 文本 chunk"""
        lines = [
            json.dumps({"message": {"content": "Hello"}}),
            json.dumps({"message": {"content": " world"}}),
            json.dumps({"message": {"content": "!"}}),
        ]

        mock_response = MockHttpResponse(lines)

        with patch("httpx.stream", return_value=mock_response):
            chunks = list(
                _stream_ollama_api(
                    ollama_host="http://localhost:11434",
                    model_name="llama3",
                    messages=[{"role": "user", "content": "Hi"}],
                    temperature=0.7,
                    max_tokens=100,
                )
            )

            assert chunks == ["Hello", " world", "!"]

    def test_skips_empty_lines(self):
        """应跳过空行"""
        lines = [
            "",
            json.dumps({"message": {"content": "text"}}),
            "",
        ]

        mock_response = MockHttpResponse(lines)

        with patch("httpx.stream", return_value=mock_response):
            chunks = list(
                _stream_ollama_api(
                    ollama_host="http://localhost:11434",
                    model_name="llama3",
                    messages=[{"role": "user", "content": "Hi"}],
                    temperature=0.7,
                    max_tokens=100,
                )
            )

            assert chunks == ["text"]

    def test_skips_malformed_json(self):
        """应跳过无法解析的 JSON"""
        lines = [
            json.dumps({"message": {"content": "valid"}}),
            "not valid json",
            json.dumps({"message": {"content": "also valid"}}),
        ]

        mock_response = MockHttpResponse(lines)

        with patch("httpx.stream", return_value=mock_response):
            chunks = list(
                _stream_ollama_api(
                    ollama_host="http://localhost:11434",
                    model_name="llama3",
                    messages=[{"role": "user", "content": "Hi"}],
                    temperature=0.7,
                    max_tokens=100,
                )
            )

            assert chunks == ["valid", "also valid"]

    def test_raises_ollama_not_ready_on_error(self):
        """连接错误应抛出 OllamaNotReadyError"""
        with patch("httpx.stream", side_effect=Exception("Connection refused")):
            with pytest.raises(OllamaNotReadyError) as exc_info:
                list(
                    _stream_ollama_api(
                        ollama_host="http://localhost:11434",
                        model_name="llama3",
                        messages=[{"role": "user", "content": "Hi"}],
                        temperature=0.7,
                        max_tokens=100,
                    )
                )

            assert "Connection refused" in str(exc_info.value)


class TestStreamOpenaiCompatibleApi:
    """OpenAI Compatible 流式 API 测试"""

    def test_parses_data_prefix_correctly(self):
        """应正确解析 data: 前缀"""
        lines = [
            'data: {"choices": [{"delta": {"content": "Hello"}}]}',
            'data: {"choices": [{"delta": {"content": " world"}}]}',
        ]

        mock_response = MockHttpResponse(lines)

        with patch("httpx.stream", return_value=mock_response):
            chunks = list(
                _stream_openai_compatible_api(
                    api_base="https://api.openai.com/v1",
                    api_key="sk-test",
                    model_name="gpt-4",
                    messages=[{"role": "user", "content": "Hi"}],
                    temperature=0.7,
                    max_tokens=100,
                )
            )

            assert chunks == ["Hello", " world"]

    def test_stops_at_done_marker(self):
        """应在 data: [DONE] 处停止"""
        lines = [
            'data: {"choices": [{"delta": {"content": "text"}}]}',
            "data: [DONE]",
            'data: {"choices": [{"delta": {"content": "should not appear"}}]}',
        ]

        mock_response = MockHttpResponse(lines)

        with patch("httpx.stream", return_value=mock_response):
            chunks = list(
                _stream_openai_compatible_api(
                    api_base="https://api.openai.com/v1",
                    api_key="sk-test",
                    model_name="gpt-4",
                    messages=[{"role": "user", "content": "Hi"}],
                    temperature=0.7,
                    max_tokens=100,
                )
            )

            assert chunks == ["text"]
            assert "should not appear" not in chunks

    def test_skips_malformed_sse_data(self):
        """应跳过无法解析的 SSE 数据"""
        lines = [
            'data: {"choices": [{"delta": {"content": "valid"}}]}',
            "data: not valid json",
            'data: {"choices": [{"delta": {"content": "also valid"}}]}',
        ]

        mock_response = MockHttpResponse(lines)

        with patch("httpx.stream", return_value=mock_response):
            chunks = list(
                _stream_openai_compatible_api(
                    api_base="https://api.openai.com/v1",
                    api_key="sk-test",
                    model_name="gpt-4",
                    messages=[{"role": "user", "content": "Hi"}],
                    temperature=0.7,
                    max_tokens=100,
                )
            )

            assert chunks == ["valid", "also valid"]

    def test_requires_api_base(self):
        """缺少 api_base 应抛出错误"""
        with pytest.raises(ValueError) as exc_info:
            list(
                _stream_openai_compatible_api(
                    api_base="",
                    api_key="test",
                    model_name="gpt-4",
                    messages=[{"role": "user", "content": "Hi"}],
                    temperature=0.7,
                    max_tokens=100,
                )
            )

        assert "未找到大模型服务商" in str(exc_info.value)

    def test_includes_authorization_header(self):
        """应包含 Authorization header"""
        lines = []
        mock_response = MockHttpResponse(lines)

        with patch("httpx.stream", return_value=mock_response) as mock_stream:
            list(
                _stream_openai_compatible_api(
                    api_base="https://api.openai.com/v1",
                    api_key="sk-test-key",
                    model_name="gpt-4",
                    messages=[{"role": "user", "content": "Hi"}],
                    temperature=0.7,
                    max_tokens=100,
                )
            )

            call_args = mock_stream.call_args
            headers = call_args[1]["headers"]
            assert headers["Authorization"] == "Bearer sk-test-key"


class TestStreamAnthropicApi:
    """Anthropic 流式 API 测试"""

    def test_parses_content_block_delta(self):
        """应解析 content_block_delta 事件"""
        lines = [
            'data: {"type": "content_block_delta", "delta": {"text": "Hello"}}',
            'data: {"type": "content_block_delta", "delta": {"text": " world"}}',
        ]

        mock_response = MockHttpResponse(lines)

        with patch("httpx.stream", return_value=mock_response):
            chunks = list(
                _stream_anthropic_api(
                    api_base="https://api.anthropic.com/v1",
                    api_key="sk-ant-test",
                    model_name="claude-3-opus-20240229",
                    messages=[{"role": "user", "content": "Hi"}],
                    temperature=0.7,
                    max_tokens=100,
                )
            )

            assert chunks == ["Hello", " world"]

    def test_ignores_other_event_types(self):
        """应忽略其他事件类型"""
        lines = [
            'data: {"type": "message_start", "message": {}}',
            'data: {"type": "content_block_delta", "delta": {"text": "text"}}',
            'data: {"type": "message_delta", "delta": {}}',
        ]

        mock_response = MockHttpResponse(lines)

        with patch("httpx.stream", return_value=mock_response):
            chunks = list(
                _stream_anthropic_api(
                    api_base="https://api.anthropic.com/v1",
                    api_key="sk-ant-test",
                    model_name="claude-3-opus-20240229",
                    messages=[{"role": "user", "content": "Hi"}],
                    temperature=0.7,
                    max_tokens=100,
                )
            )

            assert chunks == ["text"]

    def test_extracts_system_prompt(self):
        """应提取 system prompt 为顶层参数"""
        lines = []
        mock_response = MockHttpResponse(lines)

        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]

        with patch("httpx.stream", return_value=mock_response) as mock_stream:
            list(
                _stream_anthropic_api(
                    api_base="https://api.anthropic.com/v1",
                    api_key="sk-ant-test",
                    model_name="claude-3-opus-20240229",
                    messages=messages,
                    temperature=0.7,
                    max_tokens=100,
                )
            )

            call_args = mock_stream.call_args
            payload = call_args[1]["json"]

            assert "system" in payload
            assert payload["system"] == "You are helpful."
            assert len(payload["messages"]) == 1
            assert payload["messages"][0]["role"] == "user"

    def test_uses_correct_headers(self):
        """应使用正确的 Anthropic headers"""
        lines = []
        mock_response = MockHttpResponse(lines)

        with patch("httpx.stream", return_value=mock_response) as mock_stream:
            list(
                _stream_anthropic_api(
                    api_base="https://api.anthropic.com/v1",
                    api_key="sk-ant-test",
                    model_name="claude-3-opus-20240229",
                    messages=[{"role": "user", "content": "Hi"}],
                    temperature=0.7,
                    max_tokens=100,
                )
            )

            call_args = mock_stream.call_args
            headers = call_args[1]["headers"]

            assert headers["x-api-key"] == "sk-ant-test"
            assert headers["anthropic-version"] == "2023-06-01"
            assert "Authorization" not in headers


class TestStreamDispatch:
    """SSE 流式 API 分发测试"""

    def test_dispatch_table_contains_all_modes(self):
        """分发表应包含所有 API 模式"""
        assert "ollama" in _STREAM_DISPATCH
        assert "chat_completions" in _STREAM_DISPATCH
        assert "anthropic_messages" in _STREAM_DISPATCH

    def test_dispatch_routes_to_correct_function(self):
        """分发表应路由到正确的函数"""
        assert _STREAM_DISPATCH["ollama"] == _stream_ollama_api
        assert _STREAM_DISPATCH["chat_completions"] == _stream_openai_compatible_api
        assert _STREAM_DISPATCH["anthropic_messages"] == _stream_anthropic_api
