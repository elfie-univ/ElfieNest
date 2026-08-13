"""tests for infrastructure.models.catalog module"""

import urllib.error
from unittest.mock import MagicMock, patch

from infrastructure.models.catalog import (
    BUILTIN_MODEL_CATALOG,
    ModelCatalog,
    verify_provider,
)
from infrastructure.models.model_execution_config import ModelExecutionConfig


class TestBuiltinModelCatalog:
    """BUILTIN_MODEL_CATALOG 内置模型目录测试"""

    def test_builtin_catalog_has_fifteen_plus_entries(self):
        """BUILTIN_MODEL_CATALOG 包含 15+ 个模型"""
        assert len(BUILTIN_MODEL_CATALOG) >= 15

    def test_each_entry_has_required_fields(self):
        """每个 ModelEntry 都有必需字段"""
        required_fields = [
            "model_id",
            "provider",
            "display_name",
            "capabilities",
            "context_window",
            "cost_tier",
            "visible",
            "active",
        ]
        for model_id, entry in BUILTIN_MODEL_CATALOG.items():
            for field in required_fields:
                assert hasattr(entry, field), f"{model_id} 缺少字段 {field}"

    def test_model_id_format(self):
        """model_id 格式为 provider/model"""
        for model_id, entry in BUILTIN_MODEL_CATALOG.items():
            assert "/" in model_id, f"{model_id} 格式错误，应为 provider/model"
            parts = model_id.split("/", 1)
            assert len(parts) == 2, f"{model_id} 格式错误"
            assert parts[0] == entry.provider, f"{model_id} 的 provider 不匹配"

    def test_ollama_models_are_active(self):
        """Ollama 模型默认为 active"""
        ollama_models = [
            entry
            for entry in BUILTIN_MODEL_CATALOG.values()
            if entry.provider == "ollama"
        ]
        assert len(ollama_models) > 0
        for entry in ollama_models:
            assert entry.active is True, f"{entry.model_id} 应该默认 active"

    def test_non_ollama_models_are_inactive_by_default(self):
        """非 Ollama 模型默认为 inactive"""
        non_ollama_models = [
            entry
            for entry in BUILTIN_MODEL_CATALOG.values()
            if entry.provider != "ollama"
        ]
        assert len(non_ollama_models) > 0
        for entry in non_ollama_models:
            assert entry.active is False, f"{entry.model_id} 应该默认 inactive"


class TestModelCatalog:
    """ModelCatalog 类测试"""

    def test_loads_builtin_catalog(self):
        """ModelCatalog 加载内置目录"""
        catalog = ModelCatalog()
        assert len(catalog.get_all_models()) >= 15

    def test_get_visible_models(self):
        """get_visible_models 返回可见模型"""
        catalog = ModelCatalog()
        visible = catalog.get_visible_models()
        # 默认所有模型都是可见的
        assert len(visible) >= 15
        for entry in visible.values():
            assert entry.visible is True

    def test_get_active_models(self):
        """get_active_models 返回可用模型"""
        catalog = ModelCatalog()
        active = catalog.get_active_models()
        # 默认只有 Ollama 模型是 active 的
        for entry in active.values():
            assert entry.active is True

    def test_filter_by_capability_vision(self):
        """get_models_by_capability 按 vision 能力筛选"""
        catalog = ModelCatalog()
        vision_models = catalog.get_models_by_capability("vision")
        assert len(vision_models) > 0
        for entry in vision_models:
            assert "vision" in entry.capabilities

    def test_filter_by_capability_text(self):
        """get_models_by_capability 按 text 能力筛选"""
        catalog = ModelCatalog()
        text_models = catalog.get_models_by_capability("text")
        assert len(text_models) > 0
        for entry in text_models:
            assert "text" in entry.capabilities

    def test_filter_by_provider_openai(self):
        """get_models_by_provider 按 openai 筛选"""
        catalog = ModelCatalog()
        openai_models = catalog.get_models_by_provider("openai")
        assert len(openai_models) > 0
        for entry in openai_models:
            assert entry.provider == "openai"

    def test_filter_by_provider_ollama(self):
        """get_models_by_provider 按 ollama 筛选"""
        catalog = ModelCatalog()
        ollama_models = catalog.get_models_by_provider("ollama")
        assert len(ollama_models) > 0
        for entry in ollama_models:
            assert entry.provider == "ollama"

    def test_update_visibility(self):
        """update_visibility 切换可见性"""
        catalog = ModelCatalog()
        # 隐藏一个模型
        result = catalog.update_visibility("openai/gpt-4o", False)
        assert result is True
        assert catalog.get_model("openai/gpt-4o").visible is False
        # 可见模型应该少一个
        visible = catalog.get_visible_models()
        assert "openai/gpt-4o" not in visible

    def test_update_visibility_nonexistent_model(self):
        """update_visibility 对不存在的模型返回 False"""
        catalog = ModelCatalog()
        result = catalog.update_visibility("nonexistent/model", False)
        assert result is False

    def test_refresh_status_updates_active_based_on_api_key(
        self, monkeypatch, tmp_path
    ):
        """refresh_status 根据 API key 更新 active 状态"""
        monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
        config = ModelExecutionConfig()
        config.providers["openai"]["api_key"] = "sk-test"
        config.providers["deepseek"]["api_key"] = ""

        catalog = ModelCatalog(config)
        catalog.refresh_status()

        openai_models = catalog.get_models_by_provider("openai")
        for entry in openai_models:
            assert entry.active is True, f"{entry.model_id} 应该 active"

        deepseek_models = catalog.get_models_by_provider("deepseek")
        for entry in deepseek_models:
            assert entry.active is False, f"{entry.model_id} 应该 inactive"

    def test_refresh_status_keeps_ollama_active(self, monkeypatch, tmp_path):
        """refresh_status 保持 Ollama 模型为 active"""
        monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
        config = ModelExecutionConfig()
        catalog = ModelCatalog(config)

        ollama_models = catalog.get_models_by_provider("ollama")
        for entry in ollama_models:
            assert entry.active is True

    def test_get_model_returns_entry(self):
        """get_model 返回正确的 ModelEntry"""
        catalog = ModelCatalog()
        entry = catalog.get_model("openai/gpt-4o")
        assert entry is not None
        assert entry.model_id == "openai/gpt-4o"
        assert entry.provider == "openai"
        assert entry.display_name == "GPT-4o"

    def test_get_model_returns_none_for_nonexistent(self):
        """get_model 对不存在的模型返回 None"""
        catalog = ModelCatalog()
        entry = catalog.get_model("nonexistent/model")
        assert entry is None

    def test_empty_catalog_falls_back_to_builtin(self):
        """空配置时使用内置目录"""
        catalog = ModelCatalog(config=None)
        assert len(catalog.get_all_models()) >= 15


class TestVerifyProvider:
    """verify_provider 函数测试"""

    def test_verify_ollama_returns_active(self, monkeypatch, tmp_path):
        """verify_provider 对 Ollama 返回 active（模拟成功）"""
        monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
        config = ModelExecutionConfig()

        # Mock the credential-safe Provider transport.
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch(
            "infrastructure.models.catalog.open_provider_request",
            return_value=mock_response,
        ):
            result = verify_provider("ollama", config)

        assert result["status"] == "active"
        assert result["latency_ms"] is not None
        assert result["error"] is None

    def test_verify_openai_with_api_key(self, monkeypatch, tmp_path):
        """verify_provider 对 OpenAI 使用 Bearer token"""
        monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
        config = ModelExecutionConfig()
        config.providers["openai"]["api_key"] = "sk-test"

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        captured_request = []

        def capture_request(req, timeout=None):
            captured_request.append(req)
            return mock_response

        with patch(
            "infrastructure.models.catalog.open_provider_request",
            side_effect=capture_request,
        ):
            result = verify_provider("openai", config)

        assert result["status"] == "active"
        # 验证 Authorization header
        assert "Authorization" in captured_request[0].headers
        assert "Bearer sk-test" in captured_request[0].headers["Authorization"]

    def test_verify_anthropic_with_api_key(self, monkeypatch, tmp_path):
        """verify_provider 对 Anthropic 使用 x-api-key header"""
        monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
        config = ModelExecutionConfig()
        config.providers["anthropic"] = {
            "api_key": "sk-ant-test",
            "api_base": "https://api.anthropic.com/v1",
            "api_mode": "anthropic_messages",
        }

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        captured_request = []

        def capture_request(req, timeout=None):
            captured_request.append(req)
            return mock_response

        with patch(
            "infrastructure.models.catalog.open_provider_request",
            side_effect=capture_request,
        ):
            result = verify_provider("anthropic", config)

        assert result["status"] == "active"
        headers_lower = {k.lower(): v for k, v in captured_request[0].headers.items()}
        assert "x-api-key" in headers_lower

    def test_verify_provider_timeout(self, monkeypatch, tmp_path):
        """verify_provider 超时时返回 inactive"""
        monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
        config = ModelExecutionConfig()

        def raise_timeout(*args, **kwargs):
            raise TimeoutError("Connection timed out")

        with patch(
            "infrastructure.models.catalog.open_provider_request",
            side_effect=raise_timeout,
        ):
            result = verify_provider("openai", config)

        assert result["status"] == "inactive"
        assert "超时" in result["error"]

    def test_verify_provider_connection_error(self, monkeypatch, tmp_path):
        """verify_provider 连接错误时返回 inactive"""
        monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
        config = ModelExecutionConfig()

        def raise_url_error(*args, **kwargs):
            raise urllib.error.URLError("Connection refused")

        with patch(
            "infrastructure.models.catalog.open_provider_request",
            side_effect=raise_url_error,
        ):
            result = verify_provider("openai", config)

        assert result["status"] == "inactive"
        assert result["error"] is not None

    def test_verify_provider_http_error(self, monkeypatch, tmp_path):
        """verify_provider HTTP 错误时返回 inactive"""
        monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
        config = ModelExecutionConfig()

        def raise_http_error(*args, **kwargs):
            raise urllib.error.HTTPError(
                "http://example.com", 401, "Unauthorized", {}, None
            )

        with patch(
            "infrastructure.models.catalog.open_provider_request",
            side_effect=raise_http_error,
        ):
            result = verify_provider("openai", config)

        assert result["status"] == "inactive"
        assert "401" in result["error"]

    def test_verify_unknown_provider(self, monkeypatch, tmp_path):
        """verify_provider 对未知 provider 返回 unverified"""
        monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
        config = ModelExecutionConfig()

        result = verify_provider("unknown_provider", config)

        assert result["status"] == "unverified"
        assert "未知 provider" in result["error"]

    def test_verify_configured_dynamic_custom_provider(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
        config = ModelExecutionConfig()
        config.providers["custom_gateway"] = {
            "api_base": "https://gateway.example/v1",
            "api_mode": "chat_completions",
            "auth_type": "bearer",
            "api_key": "<test-api-key>",
        }
        expected = {"status": "active", "latency_ms": 12.0, "error": None}

        with patch(
            "infrastructure.models.catalog._verify_custom_openai_provider",
            return_value=expected,
        ) as verify_custom:
            result = verify_provider("custom_gateway", config)

        assert result == expected
        verify_custom.assert_called_once()
