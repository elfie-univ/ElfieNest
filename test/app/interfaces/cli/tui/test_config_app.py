from __future__ import annotations

import builtins

import pytest
from _pytest.capture import CaptureFixture

from app.features.configuration import (
    GetElfieSettingsQuery,
    GetRuntimeSettingsQuery,
    GetSecuritySettingsQuery,
    UpdateRuntimeSettingsCommand,
)
from app.interfaces.cli.tui import (
    config_app,
    config_editors,
    config_views,
    provider_menu,
)
from test.app.interfaces.cli.configuration_test_support import (
    FakeProvidersService,
    manager_principal,
    settings_service,
    verification,
)


class FakeRuntimeMenus:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def tool_menu(self) -> None:
        self._calls.append("tools")

    def food_menu(self) -> None:
        self._calls.append("food")


def _run_config_tui(runtime_menus: FakeRuntimeMenus) -> None:
    config_app.run_config_tui(
        FakeProvidersService(),
        settings_service(),
        manager_principal(),
        lambda _provider_id: None,
        runtime_menus,
    )


def test_run_config_tui_exits_from_main_menu(
    monkeypatch: pytest.MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    monkeypatch.setattr(config_app, "clear_screen", lambda: None)
    monkeypatch.setattr(config_app, "print_banner", lambda: None)
    _patch_input(monkeypatch, ["0"])

    _run_config_tui(FakeRuntimeMenus([]))

    output = capsys.readouterr().out
    assert "Runtime Config" in output
    assert "Goodbye" in output


def test_run_config_tui_exits_cleanly_on_eof(
    monkeypatch: pytest.MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    monkeypatch.setattr(config_app, "clear_screen", lambda: None)
    monkeypatch.setattr(config_app, "print_banner", lambda: None)

    def raise_eof(_prompt: str = "") -> str:
        raise EOFError

    monkeypatch.setattr(builtins, "input", raise_eof)

    _run_config_tui(FakeRuntimeMenus([]))

    assert "Goodbye" in capsys.readouterr().out


def test_config_tui_dispatches_three_runtime_layers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(config_app, "clear_screen", lambda: None)
    monkeypatch.setattr(config_app, "print_banner", lambda: None)
    monkeypatch.setattr(config_app, "config_providers", lambda *args: calls.append("provider"))
    _patch_input(monkeypatch, ["1", "2", "3", "0"])

    _run_config_tui(FakeRuntimeMenus(calls))

    assert calls == ["provider", "tools", "food"]


def test_config_tui_dispatches_view_and_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(config_app, "clear_screen", lambda: None)
    monkeypatch.setattr(config_app, "print_banner", lambda: None)
    monkeypatch.setattr(config_app, "config_providers", lambda *args: calls.append("provider"))
    monkeypatch.setattr(config_app, "show_config", lambda *args: calls.append("view"))
    monkeypatch.setattr(config_app, "reset_config", lambda *args: calls.append("reset"))
    _patch_input(monkeypatch, ["1", "2", "3", "4", "5", "0"])

    _run_config_tui(FakeRuntimeMenus(calls))

    assert calls == ["provider", "tools", "food", "view", "reset"]


def test_config_menu_only_shows_runtime_and_basic_config(
    monkeypatch: pytest.MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    monkeypatch.setattr(config_app, "clear_screen", lambda: None)
    monkeypatch.setattr(config_app, "print_banner", lambda: None)
    _patch_input(monkeypatch, ["0"])

    _run_config_tui(FakeRuntimeMenus([]))

    output = capsys.readouterr().out
    assert "Provider and Model Configuration" in output
    assert "Agent Capability Validation" in output
    assert "Food Strategy Configuration" in output
    assert "View Current Config" in output
    assert "Reset Runtime Config" in output
    assert "Owner Account" not in output
    assert "Diagnostics and auto-repair" not in output


def test_config_llm_redirects_model_management_to_runtime_lab(
    monkeypatch: pytest.MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    monkeypatch.setattr(config_editors, "clear_screen", lambda: None)
    monkeypatch.setattr(config_editors, "print_banner", lambda: None)
    _patch_input(monkeypatch, [""])

    config_editors.config_llm()

    assert "managed in AI Runtime" in capsys.readouterr().out


def test_security_editor_writes_typed_security_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_service()
    principal = manager_principal()
    _patch_input(monkeypatch, ["1", "14", "2", "8", "3", "600", "0"])

    config_editors.config_security(settings, principal)

    security = settings.get_security_settings(principal, GetSecuritySettingsQuery())
    assert security.session_ttl_days == 14
    assert security.rate_limit.max_attempts == 8
    assert security.rate_limit.window_seconds == 600


def test_adoption_editor_uses_typed_settings_facade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_service()
    principal = manager_principal()
    _patch_input(monkeypatch, ["1", "5", "0"])

    config_editors.config_adoption(settings, principal)

    adoption = settings.get_elfie_settings(principal, GetElfieSettingsQuery())
    assert adoption.max_elfies_per_user == 5


def test_reset_config_preserves_providers_and_resets_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers = FakeProvidersService()
    providers.add_connection("openai")
    settings = settings_service()
    principal = manager_principal()
    settings.update_runtime_settings(
        principal,
        UpdateRuntimeSettingsCommand(tick_interval_sec=9.0),
    )
    _patch_input(monkeypatch, ["yes", ""])

    config_views.reset_config(settings, principal)

    assert providers.connections[0].catalog_id == "openai"
    runtime = settings.get_runtime_settings(principal, GetRuntimeSettingsQuery())
    assert runtime.tick_interval_sec == 1.5


def test_config_providers_dispatches_provider_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected_provider_ids: list[str] = []
    _patch_input(monkeypatch, ["2", "1", "0"])

    provider_menu.config_providers(
        FakeProvidersService(),
        manager_principal(),
        selected_provider_ids.append,
    )

    assert selected_provider_ids == ["openai"]


def test_config_providers_reads_model_overview_through_facade(
    monkeypatch: pytest.MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    _patch_input(monkeypatch, ["1", "", "0"])

    provider_menu.config_providers(
        FakeProvidersService(),
        manager_principal(),
        lambda _provider_id: None,
    )

    assert "No configured models" in capsys.readouterr().out


def test_config_providers_keeps_custom_openai_choice_last(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers = FakeProvidersService()
    selected_provider_ids: list[str] = []
    _patch_input(monkeypatch, ["2", str(len(providers.products)), "0"])

    provider_menu.config_providers(
        providers,
        manager_principal(),
        selected_provider_ids.append,
    )

    assert selected_provider_ids == ["custom_openai"]


def test_config_providers_displays_custom_provider_name(
    monkeypatch: pytest.MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    providers = FakeProvidersService()
    providers.add_connection("custom_openai", alias="My Proxy")
    _patch_input(monkeypatch, ["0"])

    provider_menu.config_providers(
        providers,
        manager_principal(),
        lambda _provider_id: None,
    )

    output = capsys.readouterr().out
    assert "My Proxy" in output
    assert "Custom OpenAI-compatible endpoint" not in output


def test_config_providers_tests_custom_provider_with_custom_name(
    monkeypatch: pytest.MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    providers = FakeProvidersService()
    providers.add_connection("custom_openai", alias="My Proxy")
    providers.next_verification = verification("failed", error="HTTP 400")
    _patch_input(monkeypatch, ["2", "3", "", "0", "0"])

    provider_menu.config_providers(
        providers,
        manager_principal(),
        lambda _provider_id: None,
    )

    assert "❌ My Proxy: HTTP 400" in capsys.readouterr().out


def test_config_providers_deletes_connection_through_facade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers = FakeProvidersService()
    providers.add_connection("openai")
    _patch_input(monkeypatch, ["2", "4", "yes", "", "0"])

    provider_menu.config_providers(
        providers,
        manager_principal(),
        lambda _provider_id: None,
    )

    assert providers.connections == []


def _patch_input(
    monkeypatch: pytest.MonkeyPatch,
    values: list[str],
) -> None:
    iterator = iter(values)

    def fake_input(prompt: str = "") -> str:
        return next(iterator)

    monkeypatch.setattr(builtins, "input", fake_input)
