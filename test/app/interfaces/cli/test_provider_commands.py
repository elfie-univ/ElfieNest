from __future__ import annotations

from _pytest.capture import CaptureFixture

from app.infrastructure.persistence.account_repository import AccountRepository
from app.infrastructure.persistence.elfie_repository import ElfieRepository
from app.infrastructure.persistence.store import get_db, init_db
from app.interfaces.cli import provider_commands, route_commands


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
    text_answers = iter(["My Proxy", "https://proxy.example.com/v1", "gpt-4o-mini"])

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
    assert prompts == ["  Name", "  Endpoint / Base URL", "  Test model"]
    assert provider["display_name"] == "My Proxy"
    assert provider["api_base"] == "https://proxy.example.com/v1"
    assert provider["test_model"] == "gpt-4o-mini"
    assert provider["api_mode"] == "chat_completions"
    assert saved_env_vars[0]["CUSTOM_OPENAI_API_KEY"] == "test-key"


def test_login_provider_saves_custom_endpoint_when_verify_fails(monkeypatch) -> None:
    saved_configs = []
    saved_env_vars = []
    text_answers = iter(["My Proxy", "https://proxy.example.com/v1", "gpt-4o-mini"])
    monkeypatch.setattr(provider_commands, "input_password", lambda prompt: "test-key")
    monkeypatch.setattr(
        provider_commands, "input_text", lambda prompt: next(text_answers)
    )
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
    assert provider["display_name"] == "My Proxy"
    assert provider["status"] == "active"
    assert saved_env_vars[0]["CUSTOM_OPENAI_API_BASE"] == "https://proxy.example.com/v1"


def test_show_route_prints_main_food_without_models(
    tmp_path,
    monkeypatch,
    capsys: CaptureFixture[str],
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    database_path = init_db()
    with get_db(database_path) as connection:
        owner_id = AccountRepository(connection).create_owner(
            username="owner",
            password_hash="test-hash",
            nickname="Owner",
            avatar_color=0,
        )
        connection.commit()
    elfies = ElfieRepository(database_path)
    elfies.reserve_adoption(
        elfie_id="00000001",
        owner_user_id=owner_id,
        name="Elfie",
        species="fox",
        summary=None,
        max_elfies=3,
    )
    from app.infrastructure.persistence.food_assignments import set_elfie_main_food_id

    set_elfie_main_food_id(database_path, "00000001", "premium")

    route_commands.show_route("00000001")

    output = capsys.readouterr().out
    assert "00000001 Main Food" in output
    assert "Main food: premium" in output
    assert "Models are managed by Runtime food packages" in output
