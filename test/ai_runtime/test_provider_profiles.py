from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.providers.profiles import (
    BUILTIN_PROFILES,
    get_default_api_mode,
    get_profile,
)


class TestBuiltinProfiles:
    """BUILTIN_PROFILES 内置服务商档案测试"""

    def test_builtin_profiles_has_custom_openai_profile(self):
        assert "custom_openai" in BUILTIN_PROFILES
        assert BUILTIN_PROFILES["custom_openai"].api_mode == "chat_completions"
        assert (
            BUILTIN_PROFILES["custom_openai"].api_key_env_var == "CUSTOM_OPENAI_API_KEY"
        )

    def test_each_profile_has_required_fields(self):
        """每个 profile 都有必需字段"""
        required_fields = ["name", "api_base", "auth_type", "api_mode"]
        for provider_name, profile in BUILTIN_PROFILES.items():
            for field in required_fields:
                assert hasattr(profile, field), f"{provider_name} 缺少字段 {field}"
                assert getattr(profile, field), f"{provider_name} 字段 {field} 为空"

    def test_anthropic_profile_auth_type_and_api_mode(self):
        """Anthropic 使用 x-api-key 认证和 anthropic_messages API 模式"""
        anthropic = BUILTIN_PROFILES["anthropic"]
        assert anthropic.auth_type == "x-api-key"
        assert anthropic.api_mode == "anthropic_messages"

    def test_ollama_profile_auth_type_and_api_mode(self):
        """Ollama 使用 none 认证和 ollama API 模式"""
        ollama = BUILTIN_PROFILES["ollama"]
        assert ollama.auth_type == "none"
        assert ollama.api_mode == "ollama"

    def test_default_models_structure(self):
        """每个 profile 的 default_models 包含 cheap/deep/multimodal 分类"""
        for provider_name, profile in BUILTIN_PROFILES.items():
            models = profile.default_models
            assert "cheap" in models, f"{provider_name} 缺少 cheap 模型列表"
            assert "deep" in models, f"{provider_name} 缺少 deep 模型列表"
            assert "multimodal" in models, f"{provider_name} 缺少 multimodal 模型列表"


class TestProviderProfileHelpers:
    """ProviderProfile 辅助函数测试"""

    def test_get_profile_returns_profile_for_known_provider(self):
        """get_profile 返回已知服务商的 profile"""
        profile = get_profile("openai")
        assert profile is not None
        assert profile.name == "OpenAI"

    def test_get_profile_returns_none_for_unknown_provider(self):
        """get_profile 对未知服务商返回 None"""
        profile = get_profile("unknown_provider")
        assert profile is None

    def test_get_default_api_mode_for_known_provider(self):
        """get_default_api_mode 返回已知服务商的 API 模式"""
        assert get_default_api_mode("ollama") == "ollama"
        assert get_default_api_mode("anthropic") == "anthropic_messages"
        assert get_default_api_mode("openai") == "chat_completions"

    def test_get_default_api_mode_defaults_to_chat_completions(self):
        """get_default_api_mode 对未知服务商默认返回 chat_completions"""
        assert get_default_api_mode("unknown_provider") == "chat_completions"


class TestLLMRuntimeConfigBackwardCompat:
    """LLMRuntimeConfig 向后兼容性测试"""

    def test_loads_old_config_without_api_mode(self, monkeypatch, tmp_path):
        """加载无 api_mode 字段的旧配置时自动补充"""
        monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
        config_path = tmp_path / "config.yaml"
        old_config = {
            "providers": {
                "openai": {
                    "api_key": "sk-test",
                    "api_base": "https://api.openai.com/v1",
                },
                "ollama": {
                    "api_key": "",
                    "api_base": "http://localhost:11434",
                },
            }
        }
        import yaml

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(old_config, f)

        config = LLMRuntimeConfig()
        assert "api_mode" in config.providers["openai"]
        assert config.providers["openai"]["api_mode"] == "chat_completions"
        assert config.providers["ollama"]["api_mode"] == "ollama"

    def test_merges_api_mode_from_builtin_profiles(self, monkeypatch, tmp_path):
        """从 BUILTIN_PROFILES 合并 api_mode"""
        monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
        config_path = tmp_path / "config.yaml"
        # 使用默认已知的 provider (deepseek) 来测试 api_mode 合并
        old_config = {
            "providers": {
                "deepseek": {
                    "api_key": "sk-test",
                    "api_base": "https://api.deepseek.com/v1",
                },
            }
        }
        import yaml

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(old_config, f)

        config = LLMRuntimeConfig()
        assert "api_mode" in config.providers["deepseek"]
        assert config.providers["deepseek"]["api_mode"] == "chat_completions"

    def test_unknown_provider_defaults_to_chat_completions(self, monkeypatch, tmp_path):
        """未知服务商默认使用 chat_completions API 模式"""
        monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
        config_path = tmp_path / "config.yaml"
        old_config = {
            "providers": {
                "custom_provider": {
                    "api_key": "test-key",
                    "api_base": "https://custom.api.com/v1",
                },
            }
        }
        import yaml

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(old_config, f)

        config = LLMRuntimeConfig()
        assert config.providers["custom_provider"]["api_mode"] == "chat_completions"
        assert (
            config.providers["custom_provider"]["api_base"]
            == "https://custom.api.com/v1"
        )
        assert config.providers["custom_provider"]["api_key"] == "test-key"
        assert config.providers["custom_provider"]["status"] == "active"

    def test_status_defaults_based_on_api_key(self, monkeypatch, tmp_path):
        """status 根据是否有 api_key 自动设置"""
        monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
        config_path = tmp_path / "config.yaml"
        old_config = {
            "providers": {
                "openai": {
                    "api_key": "sk-test",
                    "api_base": "https://api.openai.com/v1",
                },
                "deepseek": {
                    "api_key": "",
                    "api_base": "https://api.deepseek.com/v1",
                },
            }
        }
        import yaml

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(old_config, f)

        config = LLMRuntimeConfig()
        assert config.providers["openai"]["status"] == "active"
        assert config.providers["deepseek"]["status"] == "inactive"

    def test_ollama_status_always_active(self, monkeypatch, tmp_path):
        """Ollama status 始终为 active"""
        monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
        config_path = tmp_path / "config.yaml"
        old_config = {
            "providers": {
                "ollama": {
                    "api_key": "",
                    "api_base": "http://localhost:11434",
                },
            }
        }
        import yaml

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(old_config, f)

        config = LLMRuntimeConfig()
        assert config.providers["ollama"]["status"] == "active"

    def test_loads_custom_openai_credentials_from_env_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
        env_path = tmp_path / ".env"
        env_path.write_text(
            "CUSTOM_OPENAI_API_KEY=test-key\n"
            "CUSTOM_OPENAI_API_BASE=https://proxy.example.com/v1\n",
            encoding="utf-8",
        )

        config = LLMRuntimeConfig()

        provider = config.providers["custom_openai"]
        assert provider["api_key"] == "test-key"
        assert provider["api_base"] == "https://proxy.example.com/v1"
        assert provider["status"] == "active"


def test_verify_custom_openai_falls_back_to_chat_completion_when_models_endpoint_fails(
    monkeypatch,
) -> None:
    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, request.data))
        if request.full_url.endswith("/models"):
            import urllib.error

            raise urllib.error.HTTPError(
                request.full_url,
                400,
                "Bad Request",
                hdrs=None,
                fp=None,
            )
        return FakeResponse()

    monkeypatch.setattr("ai_runtime.models.catalog.open_provider_request", fake_urlopen)

    class Config:
        providers = {
            "custom_openai": {
                "api_key": "test-key",
                "api_base": "https://proxy.example.com/v1",
                "api_mode": "chat_completions",
                "test_model": "gpt-4o-mini",
            }
        }

    from ai_runtime.models.catalog import verify_provider

    result = verify_provider("custom_openai", Config())

    assert result["status"] == "active"
    assert calls[0][0] == "https://proxy.example.com/v1/models"
    assert calls[1][0] == "https://proxy.example.com/v1/chat/completions"
    assert b'"model": "gpt-4o-mini"' in calls[1][1]


def test_verify_custom_openai_returns_actionable_error_when_models_and_chat_fail(
    monkeypatch,
) -> None:
    import urllib.error

    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            400,
            "Bad Request",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr("ai_runtime.models.catalog.open_provider_request", fake_urlopen)

    class Config:
        providers = {
            "custom_openai": {
                "api_key": "test-key",
                "api_base": "https://proxy.example.com/v1",
                "api_mode": "chat_completions",
                "test_model": "gpt-4o-mini",
            }
        }

    from ai_runtime.models.catalog import verify_provider

    result = verify_provider("custom_openai", Config())

    assert result["status"] == "inactive"
    assert "Base URL 应该类似" in result["error"]
    assert "测试模型" in result["error"]
