from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.providers.profiles import (
    BUILTIN_PROFILES,
    get_default_api_mode,
    get_profile,
)
from infrastructure.persistence.provider_connections import (
    ProviderConnectionStore,
    ProviderModelRecord,
)
from infrastructure.persistence.secrets import (
    set_connection_secret,
    set_provider_secret,
    write_secrets,
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

    def test_bundled_models_are_a_flat_nonempty_list(self):
        """Bundled model candidates do not encode runtime selection groups."""
        for provider_name, profile in BUILTIN_PROFILES.items():
            assert profile.bundled_models, f"{provider_name} 缺少内置模型列表"
            assert len(profile.bundled_models) == len(set(profile.bundled_models))


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


class TestLLMRuntimeConfigProviderProfiles:
    """LLMRuntimeConfig 内置 Provider 档案投影测试。"""

    def test_loads_old_config_without_api_mode(self, monkeypatch, tmp_path):
        """加载无 api_mode 字段的旧配置时自动补充"""
        monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
        set_provider_secret("openai", "sk-test")

        config = LLMRuntimeConfig()
        assert "api_mode" in config.providers["openai"]
        assert config.providers["openai"]["api_mode"] == "chat_completions"
        assert config.providers["ollama"]["api_mode"] == "ollama"

    def test_merges_api_mode_from_builtin_profiles(self, monkeypatch, tmp_path):
        """从 BUILTIN_PROFILES 合并 api_mode"""
        monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
        # 使用默认已知的 provider (deepseek) 来测试 api_mode 合并
        set_provider_secret("deepseek", "sk-test")

        config = LLMRuntimeConfig()
        assert "api_mode" in config.providers["deepseek"]
        assert config.providers["deepseek"]["api_mode"] == "chat_completions"

    def test_unknown_legacy_provider_is_not_loaded(self, monkeypatch, tmp_path):
        """Provider 实例只从 providers.yaml 加载，不复活旧 runtime 配置。"""
        monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
        set_provider_secret("custom_provider", "test-key")

        config = LLMRuntimeConfig()
        assert "custom_provider" not in config.providers

    def test_status_defaults_based_on_api_key(self, monkeypatch, tmp_path):
        """status 根据是否有 api_key 自动设置"""
        monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
        set_provider_secret("openai", "sk-test")

        config = LLMRuntimeConfig()
        assert config.providers["openai"]["status"] == "active"
        assert config.providers["deepseek"]["status"] == "inactive"

    def test_ollama_status_always_active(self, monkeypatch, tmp_path):
        """Ollama status 始终为 active"""
        monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
        config = LLMRuntimeConfig()
        assert config.providers["ollama"]["status"] == "active"

    def test_loads_custom_openai_credentials_from_env_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
        write_secrets(
            {
                "CUSTOM_OPENAI_API_KEY": "test-key",
                "CUSTOM_OPENAI_API_BASE": "https://proxy.example.com/v1",
            }
        )

        config = LLMRuntimeConfig()

        provider = config.providers["custom_openai"]
        assert provider["api_key"] == "test-key"
        assert provider["api_base"] == "https://proxy.example.com/v1"
        assert provider["status"] == "active"

    def test_loads_stable_connection_instance_for_runtime(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
        connection = ProviderConnectionStore().create(
            catalog_id="openai_api",
            alias="工作账号",
            api_base="https://api.openai.com/v1",
            api_mode="chat_completions",
            auth_type="bearer",
            models=(
                ProviderModelRecord(
                    endpoint_model_id="gpt-test",
                    display_name="GPT Test",
                ),
            ),
        )
        set_connection_secret(connection.connection_id, "connection-key")

        config = LLMRuntimeConfig()

        runtime_provider = config.providers[connection.connection_id]
        assert runtime_provider["catalog_id"] == "openai_api"
        assert runtime_provider["display_name"] == "工作账号"
        assert runtime_provider["api_key"] == "connection-key"
        assert runtime_provider["models"] == [
            {"id": "gpt-test", "display_name": "GPT Test"}
        ]


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
