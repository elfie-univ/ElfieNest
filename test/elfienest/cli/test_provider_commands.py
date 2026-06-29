from __future__ import annotations

from _pytest.capture import CaptureFixture

from elfienest.cli import provider_commands, route_commands


def test_list_providers_prints_configured_provider(
    monkeypatch,
    capsys: CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        provider_commands,
        "read_user_config",
        lambda: {"providers": {"openai": {"status": "active"}}},
    )

    provider_commands.list_providers()

    output = capsys.readouterr().out
    assert "OpenAI" in output
    assert "active" in output


def test_login_provider_saves_verified_credentials(monkeypatch) -> None:
    saved_configs = []
    saved_env_vars = []
    monkeypatch.setattr(provider_commands, "input_password", lambda prompt: "test-key")
    monkeypatch.setattr(provider_commands, "input_text", lambda prompt: "")
    monkeypatch.setattr(provider_commands, "read_user_config", lambda: {})
    monkeypatch.setattr(provider_commands, "read_env_file", lambda: {})
    monkeypatch.setattr(provider_commands, "write_user_config", saved_configs.append)
    monkeypatch.setattr(provider_commands, "write_env_file", saved_env_vars.append)
    monkeypatch.setattr(
        provider_commands,
        "verify_provider",
        lambda provider_id, config: {"status": "active", "latency_ms": 12.0},
    )

    provider_commands.login_provider("openai")

    assert saved_configs[0]["providers"]["openai"]["status"] == "active"
    assert saved_env_vars[0]["OPENAI_API_KEY"] == "test-key"


def test_login_provider_accepts_custom_openai_endpoint(monkeypatch) -> None:
    saved_configs = []
    saved_env_vars = []
    prompts = []
    text_answers = iter(["我的代理", "https://proxy.example.com/v1", "gpt-4o-mini"])

    def input_text(prompt: str) -> str:
        prompts.append(prompt)
        return next(text_answers)

    monkeypatch.setattr(provider_commands, "input_password", lambda prompt: "test-key")
    monkeypatch.setattr(provider_commands, "input_text", input_text)
    monkeypatch.setattr(provider_commands, "read_user_config", lambda: {})
    monkeypatch.setattr(provider_commands, "read_env_file", lambda: {})
    monkeypatch.setattr(provider_commands, "write_user_config", saved_configs.append)
    monkeypatch.setattr(provider_commands, "write_env_file", saved_env_vars.append)
    monkeypatch.setattr(
        provider_commands,
        "verify_provider",
        lambda provider_id, config: {"status": "active", "latency_ms": 12.0},
    )

    provider_commands.login_provider("custom_openai")

    provider = saved_configs[0]["providers"]["custom_openai"]
    assert prompts == ["  名称", "  Endpoint / Base URL", "  测试模型"]
    assert provider["display_name"] == "我的代理"
    assert provider["api_base"] == "https://proxy.example.com/v1"
    assert provider["test_model"] == "gpt-4o-mini"
    assert provider["api_mode"] == "chat_completions"
    assert saved_env_vars[0]["CUSTOM_OPENAI_API_KEY"] == "test-key"


def test_login_provider_saves_custom_endpoint_when_verify_fails(monkeypatch) -> None:
    saved_configs = []
    saved_env_vars = []
    text_answers = iter(["我的代理", "https://proxy.example.com/v1", "gpt-4o-mini"])
    monkeypatch.setattr(provider_commands, "input_password", lambda prompt: "test-key")
    monkeypatch.setattr(provider_commands, "input_text", lambda prompt: next(text_answers))
    monkeypatch.setattr(provider_commands, "read_user_config", lambda: {})
    monkeypatch.setattr(provider_commands, "read_env_file", lambda: {})
    monkeypatch.setattr(provider_commands, "write_user_config", saved_configs.append)
    monkeypatch.setattr(provider_commands, "write_env_file", saved_env_vars.append)
    monkeypatch.setattr(
        provider_commands,
        "verify_provider",
        lambda provider_id, config: {"status": "inactive", "error": "连接失败"},
    )

    provider_commands.login_provider("custom_openai")

    provider = saved_configs[0]["providers"]["custom_openai"]
    assert provider["display_name"] == "我的代理"
    assert provider["status"] == "active"
    assert saved_env_vars[0]["CUSTOM_OPENAI_API_BASE"] == "https://proxy.example.com/v1"


def test_show_route_prints_default_scene_routes(
    tmp_path,
    monkeypatch,
    capsys: CaptureFixture[str],
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))

    route_commands.show_route("elfie-test")

    output = capsys.readouterr().out
    assert "elfie-test 场景路由" in output
    assert "idle" in output
