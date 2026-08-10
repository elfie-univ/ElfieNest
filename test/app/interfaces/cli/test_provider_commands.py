from __future__ import annotations

from _pytest.capture import CaptureFixture

from app.infrastructure.persistence.account_repository import AccountRepository
from app.infrastructure.persistence.elfie_repository import ElfieRepository
from app.infrastructure.persistence.store import get_db, init_db
from app.interfaces.cli import provider_commands, route_commands
from test.app.interfaces.cli.configuration_test_support import (
    FakeProvidersService,
    manager_principal,
    verification,
)


def test_list_providers_prints_configured_provider(
    capsys: CaptureFixture[str],
) -> None:
    providers = FakeProvidersService()
    providers.add_connection("openai")

    provider_commands.list_providers(providers, manager_principal())

    output = capsys.readouterr().out
    assert "OpenAI" in output
    assert "active" in output


def test_login_provider_saves_verified_credentials(monkeypatch) -> None:
    providers = FakeProvidersService()
    monkeypatch.setattr(provider_commands, "input_password", lambda prompt: "test-key")
    monkeypatch.setattr(provider_commands, "input_text", lambda prompt: "")

    provider_commands.login_provider(providers, manager_principal(), "openai")

    saved = providers.connections[0]
    assert saved.catalog_id == "openai"
    assert saved.has_api_key is True
    assert saved.verification.status == "passed"


def test_login_provider_accepts_custom_openai_endpoint(monkeypatch) -> None:
    providers = FakeProvidersService()
    prompts = []
    text_answers = iter(["My Proxy", "https://proxy.example.com/v1", "gpt-4o-mini"])

    def input_text(prompt: str) -> str:
        prompts.append(prompt)
        return next(text_answers)

    monkeypatch.setattr(provider_commands, "input_password", lambda prompt: "test-key")
    monkeypatch.setattr(provider_commands, "input_text", input_text)

    provider_commands.login_provider(
        providers,
        manager_principal(),
        "custom_openai",
    )

    provider = providers.connections[0]
    assert prompts == ["  Name", "  Endpoint / Base URL", "  Test model"]
    assert provider.alias == "My Proxy"
    assert provider.api_base == "https://proxy.example.com/v1"
    assert provider.models[0].model_id == "gpt-4o-mini"
    assert provider.api_mode == "chat_completions"
    assert provider.has_api_key is True


def test_login_provider_saves_custom_endpoint_when_verify_fails(
    monkeypatch,
    capsys: CaptureFixture[str],
) -> None:
    providers = FakeProvidersService()
    providers.next_verification = verification("failed", error="连接失败")
    text_answers = iter(["My Proxy", "https://proxy.example.com/v1", "gpt-4o-mini"])
    monkeypatch.setattr(provider_commands, "input_password", lambda prompt: "test-key")
    monkeypatch.setattr(
        provider_commands, "input_text", lambda prompt: next(text_answers)
    )

    provider_commands.login_provider(
        providers,
        manager_principal(),
        "custom_openai",
    )

    provider = providers.connections[0]
    assert provider.alias == "My Proxy"
    assert provider.api_base == "https://proxy.example.com/v1"
    assert "Config will still be saved" in capsys.readouterr().out


def test_remove_provider_uses_facade_lifecycle_and_delete(capsys) -> None:
    providers = FakeProvidersService()
    providers.add_connection("openai")

    provider_commands.remove_provider(providers, manager_principal(), "openai")

    assert providers.connections == []
    assert "configuration removed" in capsys.readouterr().out


def test_remove_ollama_uses_explicit_local_removal(capsys) -> None:
    providers = FakeProvidersService()
    providers.add_connection("ollama")

    provider_commands.remove_provider(providers, manager_principal(), "ollama")

    assert providers.connections == []
    assert "configuration removed" in capsys.readouterr().out


def test_show_route_prints_main_food_without_models(
    tmp_path,
    monkeypatch,
    capsys: CaptureFixture[str],
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    database_path = init_db()
    with get_db(database_path) as connection:
        owner_id = AccountRepository(connection).create_owner(
            account_id="owner",
            password_hash="test-hash",
            display_name="Owner",
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
    from infrastructure.persistence import SQLiteFoodAdapter

    SQLiteFoodAdapter(database_path).set_main_food("00000001", "premium")

    route_commands.show_route("00000001")

    output = capsys.readouterr().out
    assert "00000001 Main Food" in output
    assert "Main food: premium" in output
    assert "Models are managed by Runtime food packages" in output
