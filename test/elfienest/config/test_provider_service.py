from __future__ import annotations

from elfienest.config.provider_service import (
    list_configured_provider_rows,
    list_model_rows,
    list_provider_rows,
    remove_provider_credentials,
    save_provider_credentials,
)


def test_list_provider_rows_marks_configured_provider_active() -> None:
    config = {"providers": {"openai": {"status": "active"}}}

    rows = list_provider_rows(config)

    row_by_id = {row.provider_id: row for row in rows}
    assert row_by_id["openai"].name == "OpenAI"
    assert row_by_id["openai"].status == "active"
    assert row_by_id["ollama"].status == "inactive"
    assert row_by_id["custom_openai"].name == "自定义 OpenAI 兼容接口"
    assert rows[-1].provider_id == "custom_openai"


def test_list_provider_rows_uses_custom_provider_display_name() -> None:
    config = {
        "providers": {
            "custom_openai": {
                "display_name": "我的代理",
                "status": "active",
            }
        }
    }

    rows = list_provider_rows(config)

    row_by_id = {row.provider_id: row for row in rows}
    assert row_by_id["custom_openai"].name == "我的代理"


def test_list_configured_provider_rows_uses_custom_provider_display_name() -> None:
    config = {
        "providers": {
            "custom_openai": {
                "display_name": "我的代理",
                "status": "active",
            }
        }
    }

    rows = list_configured_provider_rows(config)

    assert rows[0].provider_id == "custom_openai"
    assert rows[0].name == "我的代理"


def test_list_configured_provider_rows_keeps_unknown_provider() -> None:
    config = {"providers": {"custom": {"status": "active", "api_mode": "custom"}}}

    rows = list_configured_provider_rows(config)

    assert len(rows) == 1
    assert rows[0].provider_id == "custom"
    assert rows[0].name == "custom"
    assert rows[0].api_mode == "custom"


def test_save_provider_credentials_updates_config_and_env() -> None:
    config = {}
    env_vars = {}

    result = save_provider_credentials(
        config,
        env_vars,
        "openai",
        "test-key",
        "https://api.openai.com/v1",
    )

    assert result is not None
    assert result.config["providers"]["openai"]["status"] == "active"
    assert result.config["providers"]["openai"]["api_mode"] == "chat_completions"
    assert result.env_vars["OPENAI_API_KEY"] == "test-key"
    assert "OPENAI_API_BASE" not in result.env_vars


def test_save_provider_credentials_stores_custom_base_url() -> None:
    result = save_provider_credentials({}, {}, "openai", "test-key", "http://local")

    assert result is not None
    assert result.env_vars["OPENAI_API_BASE"] == "http://local"


def test_save_provider_credentials_supports_custom_openai_endpoint() -> None:
    result = save_provider_credentials(
        {},
        {},
        "custom_openai",
        "test-key",
        "https://proxy.example.com/v1",
        display_name="我的代理",
        test_model="gpt-4o-mini",
    )

    assert result is not None
    provider = result.config["providers"]["custom_openai"]
    assert provider["display_name"] == "我的代理"
    assert provider["api_base"] == "https://proxy.example.com/v1"
    assert provider["test_model"] == "gpt-4o-mini"
    assert provider["api_mode"] == "chat_completions"
    assert provider["status"] == "active"
    assert result.env_vars["CUSTOM_OPENAI_API_KEY"] == "test-key"
    assert result.env_vars["CUSTOM_OPENAI_API_BASE"] == "https://proxy.example.com/v1"


def test_remove_provider_credentials_removes_config_api_key_and_base_url() -> None:
    config = {"providers": {"openai": {"status": "active"}}}
    env_vars = {
        "OPENAI_API_BASE": "http://local",
        "OPENAI_API_KEY": "test-key",
        "OTHER": "kept",
    }

    result = remove_provider_credentials(config, env_vars, "openai")

    assert result is not None
    assert result.removed_config is True
    assert result.removed_env_key is True
    assert result.removed_base_url_env_key is True
    assert "openai" not in result.config["providers"]
    assert result.env_vars == {"OTHER": "kept"}


def test_list_model_rows_reflects_provider_status() -> None:
    config = {"providers": {"openai": {"status": "active"}}}

    rows = list_model_rows(config)

    row_by_id = {row.model_id: row for row in rows}
    assert row_by_id["openai/gpt-4o"].status_text == "✅ 可用"
    assert row_by_id["deepseek/deepseek-chat"].status_text == "⭕ 未配置"
    assert row_by_id["ollama/qwen3.5:0.8b"].cost_text == "免费"
