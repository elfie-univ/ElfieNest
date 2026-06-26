"""API Mode Dispatch Tests

Test the new api_mode dispatch system for LLM API calls.
"""

import json
import os
import sys
import urllib.error
from unittest.mock import Mock, patch

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from runtime.gateway.agent import RuntimeAgent
from runtime.providers.dispatch import (
    API_DISPATCH as _API_DISPATCH,
    call_anthropic_api as _call_anthropic_api,
    call_ollama_api as _call_ollama_api,
    call_openai_compatible_api as _call_openai_compatible_api,
    detect_api_mode_for_url as _detect_api_mode_for_url,
)
from runtime.config import LLMRuntimeConfig


class TestDetectApiMode:
    """API 模式自动检测测试"""

    def test_anthropic_url_detection(self):
        """Anthropic URL 应检测为 anthropic_messages"""
        assert _detect_api_mode_for_url("https://api.anthropic.com/v1") == "anthropic_messages"
        assert _detect_api_mode_for_url("https://api.anthropic.com") == "anthropic_messages"

    def test_ollama_url_detection(self):
        """Ollama URL 应检测为 ollama"""
        assert _detect_api_mode_for_url("http://localhost:11434") == "ollama"
        assert _detect_api_mode_for_url("http://localhost:11434/api/chat") == "ollama"

    def test_openai_url_detection(self):
        """OpenAI URL 应检测为 chat_completions"""
        assert _detect_api_mode_for_url("https://api.openai.com/v1") == "chat_completions"

    def test_deepseek_url_detection(self):
        """DeepSeek URL 应检测为 chat_completions"""
        assert _detect_api_mode_for_url("https://api.deepseek.com/v1") == "chat_completions"

    def test_unknown_url_default(self):
        """未知 URL 应默认为 chat_completions"""
        assert _detect_api_mode_for_url("https://unknown.api.com") == "chat_completions"
        assert _detect_api_mode_for_url("https://custom.llm.service") == "chat_completions"

    def test_case_insensitive(self):
        """URL 检测应忽略大小写"""
        assert _detect_api_mode_for_url("HTTPS://API.ANTHROPIC.COM/V1") == "anthropic_messages"
        assert _detect_api_mode_for_url("HTTP://LOCALHOST:11434") == "ollama"


class TestCallAnthropicApi:
    """Anthropic Messages API 调用测试"""

    def test_anthropic_headers(self):
        """Anthropic API 应使用正确的 headers"""
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            "content": [{"text": "Hello from Claude"}]
        }).encode("utf-8")
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            with patch("urllib.request.Request") as mock_request:
                result = _call_anthropic_api(
                    api_base="https://api.anthropic.com/v1",
                    api_key="sk-ant-test-key",
                    model_name="claude-3-opus-20240229",
                    messages=[{"role": "user", "content": "Hello"}],
                    temperature=0.7,
                    max_tokens=100,
                )

                # 验证 Request 被调用
                assert mock_request.called
                call_args = mock_request.call_args

                # 验证 headers
                headers = call_args[1]["headers"]
                assert headers["x-api-key"] == "sk-ant-test-key"
                assert headers["anthropic-version"] == "2023-06-01"
                assert "Authorization" not in headers

    def test_anthropic_system_prompt_extraction(self):
        """Anthropic API 应提取 system prompt 为顶层参数"""
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            "content": [{"text": "Response"}]
        }).encode("utf-8")
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)

        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]

        with patch("urllib.request.urlopen", return_value=mock_response):
            with patch("urllib.request.Request") as mock_request:
                _call_anthropic_api(
                    api_base="https://api.anthropic.com/v1",
                    api_key="test-key",
                    model_name="claude-3-opus-20240229",
                    messages=messages,
                    temperature=0.7,
                    max_tokens=100,
                )

                # 验证 payload
                call_args = mock_request.call_args
                data = json.loads(call_args[1]["data"].decode("utf-8"))

                assert "system" in data
                assert data["system"] == "You are helpful."
                # system message 应从 messages 中移除
                assert len(data["messages"]) == 1
                assert data["messages"][0]["role"] == "user"

    def test_anthropic_response_parsing(self):
        """Anthropic API 应正确解析 response["content"][0]["text"] 并返回 usage"""
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            "content": [{"text": "This is Claude's response"}],
            "usage": {"input_tokens": 10, "output_tokens": 5}
        }).encode("utf-8")
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result, usage = _call_anthropic_api(
                api_base="https://api.anthropic.com/v1",
                api_key="test-key",
                model_name="claude-3-opus-20240229",
                messages=[{"role": "user", "content": "Hello"}],
                temperature=0.7,
                max_tokens=100,
            )

            assert result == "This is Claude's response"
            assert usage == {"input_tokens": 10, "output_tokens": 5}

    def test_anthropic_error_handling(self):
        """Anthropic API 应正确处理 HTTP 错误"""
        mock_error = urllib.error.HTTPError(
            url="https://api.anthropic.com/v1/messages",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=None,
        )
        mock_error.read = Mock(return_value=b'{"error": "Invalid API key"}')

        with patch("urllib.request.urlopen", side_effect=mock_error):
            with pytest.raises(RuntimeError) as exc_info:
                _call_anthropic_api(
                    api_base="https://api.anthropic.com/v1",
                    api_key="invalid-key",
                    model_name="claude-3-opus-20240229",
                    messages=[{"role": "user", "content": "Hello"}],
                    temperature=0.7,
                    max_tokens=100,
                )

            assert "Anthropic API 返回 HTTP 401 错误" in str(exc_info.value)


class TestCallOllamaApi:
    """Ollama API 调用测试"""

    def test_ollama_payload_format(self):
        """Ollama API 应使用正确的 payload 格式"""
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            "message": {"content": "Hello from Ollama"}
        }).encode("utf-8")
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            with patch("urllib.request.Request") as mock_request:
                result = _call_ollama_api(
                    ollama_host="http://localhost:11434",
                    model_name="llama3",
                    messages=[{"role": "user", "content": "Hello"}],
                    temperature=0.7,
                    max_tokens=100,
                )

                # 验证 payload
                call_args = mock_request.call_args
                data = json.loads(call_args[1]["data"].decode("utf-8"))

                assert data["model"] == "llama3"
                assert data["stream"] is False
                assert "options" in data
                assert data["options"]["temperature"] == 0.7
                assert data["options"]["num_predict"] == 100
                assert data["options"]["think"] is False


class TestCallOpenaiCompatibleApi:
    """OpenAI Compatible API 调用测试"""

    def test_openai_authorization_header(self):
        """OpenAI API 应使用 Authorization Bearer header"""
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            "choices": [{"message": {"content": "Hello from GPT"}}]
        }).encode("utf-8")
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            with patch("urllib.request.Request") as mock_request:
                result = _call_openai_compatible_api(
                    api_base="https://api.openai.com/v1",
                    api_key="sk-test-key",
                    model_name="gpt-4",
                    messages=[{"role": "user", "content": "Hello"}],
                    temperature=0.7,
                    max_tokens=100,
                    provider="openai",
                )

                # 验证 headers
                call_args = mock_request.call_args
                headers = call_args[1]["headers"]
                assert headers["Authorization"] == "Bearer sk-test-key"

    def test_openai_response_parsing(self):
        """OpenAI API 应正确解析 response["choices"][0]["message"]["content"] 并返回 usage"""
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            "choices": [{"message": {"content": "GPT response"}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}
        }).encode("utf-8")
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result, usage = _call_openai_compatible_api(
                api_base="https://api.openai.com/v1",
                api_key="test-key",
                model_name="gpt-4",
                messages=[{"role": "user", "content": "Hello"}],
                temperature=0.7,
                max_tokens=100,
                provider="openai",
            )

            assert result == "GPT response"
            assert usage == {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}

    def test_openai_missing_api_base(self):
        """OpenAI API 应在缺少 api_base 时抛出错误"""
        with pytest.raises(ValueError) as exc_info:
            _call_openai_compatible_api(
                api_base="",
                api_key="test-key",
                model_name="gpt-4",
                messages=[{"role": "user", "content": "Hello"}],
                temperature=0.7,
                max_tokens=100,
                provider="openai",
            )

        assert "未找到大模型服务商 'openai' 的有效 API Base 配置" in str(exc_info.value)


class TestApiDispatch:
    """API 分发测试"""

    def test_dispatch_table_contains_all_modes(self):
        """分发表应包含所有 API 模式"""
        assert "ollama" in _API_DISPATCH
        assert "chat_completions" in _API_DISPATCH
        assert "anthropic_messages" in _API_DISPATCH

    def test_dispatch_to_ollama(self):
        """_call_llm_api 应正确分发到 Ollama"""
        config = LLMRuntimeConfig()
        config.providers["ollama"] = {
            "api_base": "http://localhost:11434",
            "api_mode": "ollama",
        }

        agent = RuntimeAgent(config)

        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            "message": {"content": "Ollama response"}
        }).encode("utf-8")
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = agent._call_llm_api(
                provider="ollama",
                model_name="llama3",
                messages=[{"role": "user", "content": "Hello"}],
                temperature=0.7,
                max_tokens=100,
            )

            assert result == "Ollama response"

    def test_dispatch_to_anthropic(self):
        """_call_llm_api 应正确分发到 Anthropic"""
        config = LLMRuntimeConfig()
        config.providers["anthropic"] = {
            "api_base": "https://api.anthropic.com/v1",
            "api_key": "sk-ant-test",
            "api_mode": "anthropic_messages",
        }

        agent = RuntimeAgent(config)

        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            "content": [{"text": "Claude response"}]
        }).encode("utf-8")
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = agent._call_llm_api(
                provider="anthropic",
                model_name="claude-3-opus-20240229",
                messages=[{"role": "user", "content": "Hello"}],
                temperature=0.7,
                max_tokens=100,
            )

            assert result == "Claude response"

    def test_dispatch_to_openai_compatible(self):
        """_call_llm_api 应正确分发到 OpenAI Compatible"""
        config = LLMRuntimeConfig()
        config.providers["openai"] = {
            "api_base": "https://api.openai.com/v1",
            "api_key": "sk-test",
            "api_mode": "chat_completions",
        }

        agent = RuntimeAgent(config)

        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            "choices": [{"message": {"content": "GPT response"}}]
        }).encode("utf-8")
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = agent._call_llm_api(
                provider="openai",
                model_name="gpt-4",
                messages=[{"role": "user", "content": "Hello"}],
                temperature=0.7,
                max_tokens=100,
            )

            assert result == "GPT response"

    def test_dispatch_auto_detect_mode(self):
        """_call_llm_api 应在未指定 api_mode 时自动检测"""
        config = LLMRuntimeConfig()
        config.providers["anthropic"] = {
            "api_base": "https://api.anthropic.com/v1",
            "api_key": "sk-ant-test",
        }

        agent = RuntimeAgent(config)

        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            "content": [{"text": "Auto-detected Anthropic"}]
        }).encode("utf-8")
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = agent._call_llm_api(
                provider="anthropic",
                model_name="claude-3-opus-20240229",
                messages=[{"role": "user", "content": "Hello"}],
                temperature=0.7,
                max_tokens=100,
            )

            assert result == "Auto-detected Anthropic"

    def test_dispatch_default_to_chat_completions(self):
        """_call_llm_api 应默认使用 chat_completions"""
        config = LLMRuntimeConfig()
        config.providers["unknown"] = {
            "api_base": "https://unknown.api.com/v1",
            "api_key": "test-key",
        }

        agent = RuntimeAgent(config)

        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            "choices": [{"message": {"content": "Default chat_completions"}}]
        }).encode("utf-8")
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = agent._call_llm_api(
                provider="unknown",
                model_name="model-x",
                messages=[{"role": "user", "content": "Hello"}],
                temperature=0.7,
                max_tokens=100,
            )

            assert result == "Default chat_completions"
