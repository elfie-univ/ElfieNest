from __future__ import annotations

import builtins

import pytest
from _pytest.capture import CaptureFixture

from ai_runtime.config import LLMRuntimeConfig
from app.features.configuration.user_config import write_user_config
from app.interfaces.cli.tui import (
    config_app,
    config_editors,
    config_views,
    provider_menu,
)


def test_run_config_tui_exits_from_main_menu(
    monkeypatch: pytest.MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    monkeypatch.setattr(config_app, "clear_screen", lambda: None)
    monkeypatch.setattr(config_app, "print_banner", lambda: None)
    monkeypatch.setattr(config_app, "read_user_config", lambda: {})
    _patch_input(monkeypatch, ["0"])

    config_app.run_config_tui(lambda provider_id: None)

    output = capsys.readouterr().out
    assert "Runtime Config" in output
    assert "Goodbye" in output


def test_run_config_tui_exits_cleanly_on_eof(
    monkeypatch: pytest.MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    monkeypatch.setattr(config_app, "clear_screen", lambda: None)
    monkeypatch.setattr(config_app, "print_banner", lambda: None)
    monkeypatch.setattr(config_app, "read_user_config", lambda: {})

    def raise_eof(_prompt: str = "") -> str:
        raise EOFError

    monkeypatch.setattr(builtins, "input", raise_eof)

    config_app.run_config_tui(lambda _provider_id: None)

    assert "Goodbye" in capsys.readouterr().out


def test_config_tui_dispatches_three_runtime_layers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class FakeRuntimeLab:
        def provider_menu(self):
            calls.append("provider")

        def tool_menu(self):
            calls.append("tools")

        def food_menu(self):
            calls.append("food")

    monkeypatch.setattr(config_app, "RuntimeLab", FakeRuntimeLab)
    monkeypatch.setattr(config_app, "clear_screen", lambda: None)
    monkeypatch.setattr(config_app, "print_banner", lambda: None)
    monkeypatch.setattr(config_app, "read_user_config", lambda: {})
    _patch_input(monkeypatch, ["1", "2", "3", "0"])

    config_app.run_config_tui(lambda provider_id: None)

    assert calls == ["provider", "tools", "food"]


def test_config_tui_dispatches_view_and_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class FakeRuntimeLab:
        def provider_menu(self):
            calls.append("provider")

        def tool_menu(self):
            calls.append("tools")

        def food_menu(self):
            calls.append("food")

    monkeypatch.setattr(config_app, "RuntimeLab", FakeRuntimeLab)
    monkeypatch.setattr(config_app, "clear_screen", lambda: None)
    monkeypatch.setattr(config_app, "print_banner", lambda: None)
    monkeypatch.setattr(config_app, "read_user_config", lambda: {})
    monkeypatch.setattr(config_app, "show_config", lambda _: calls.append("view"))
    monkeypatch.setattr(config_app, "reset_config", lambda: calls.append("reset"))
    _patch_input(monkeypatch, ["1", "2", "3", "4", "5", "0"])

    config_app.run_config_tui(lambda provider_id: None)

    assert calls == ["provider", "tools", "food", "view", "reset"]


def test_config_menu_only_shows_runtime_and_basic_config(
    monkeypatch: pytest.MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    class FakeRuntimeLab:
        def provider_menu(self):
            return None

        def tool_menu(self):
            return None

        def food_menu(self):
            return None

    monkeypatch.setattr(config_app, "RuntimeLab", FakeRuntimeLab)
    monkeypatch.setattr(config_app, "clear_screen", lambda: None)
    monkeypatch.setattr(config_app, "print_banner", lambda: None)
    monkeypatch.setattr(config_app, "read_user_config", lambda: {})
    _patch_input(monkeypatch, ["0"])

    config_app.run_config_tui(lambda provider_id: None)

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
    config = {"system": {"llm": {"default_cheap_model": "old-model"}}}
    monkeypatch.setattr(config_editors, "clear_screen", lambda: None)
    monkeypatch.setattr(config_editors, "print_banner", lambda: None)
    _patch_input(monkeypatch, [""])

    config_editors.config_llm(config)

    output = capsys.readouterr().out
    assert "managed in AI Runtime" in output
    assert config["system"]["llm"]["default_cheap_model"] == "old-model"


def test_security_editor_writes_runtime_security_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    config = {"system": {"security": {}}}
    monkeypatch.setattr(config_editors, "write_user_config", lambda _config: None)
    _patch_input(monkeypatch, ["1", "14", "2", "8", "3", "600", "0"])

    # When
    config_editors.config_security(config)

    # Then
    security = config["system"]["security"]
    assert security == {
        "session_ttl_days": 14,
        "rate_limit": {"max_attempts": 8, "window_seconds": 600},
    }
    assert "session_ttl_hours" not in security
    assert "rate_limit_per_minute" not in security


def test_adoption_editor_round_trips_into_runtime_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    # Given
    config = {"system": {"adoption": {}}}
    config_path = tmp_path / "config.yaml"
    monkeypatch.setattr(
        config_editors,
        "write_user_config",
        lambda value: write_user_config(value, config_path),
    )
    _patch_input(monkeypatch, ["1", "5", "0"])

    # When
    config_editors.config_adoption(config)
    loaded = LLMRuntimeConfig(config_home=str(tmp_path))

    # Then
    assert loaded.system["adoption"]["max_elfies_per_user"] == 5
    assert "default_personality_style" not in loaded.system["adoption"]


def test_reset_config_preserves_provider_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = {
        "providers": {"openai": {"api_base": "https://example.invalid"}},
        "system": {"engine": {"tick_interval_sec": 9.0}},
    }
    saved: list[dict] = []
    monkeypatch.setattr(config_views, "read_user_config", lambda: config)
    monkeypatch.setattr(config_views, "write_user_config", saved.append)
    _patch_input(monkeypatch, ["yes", ""])

    config_views.reset_config()

    assert saved[0]["providers"] == config["providers"]
    assert saved[0]["system"]["engine"]["tick_interval_sec"] == 1.5


def test_config_providers_dispatches_provider_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected_provider_ids: list[str] = []
    monkeypatch.setattr(provider_menu, "clear_screen", lambda: None)
    monkeypatch.setattr(provider_menu, "print_banner", lambda: None)
    monkeypatch.setattr(provider_menu, "read_user_config", lambda: {})
    _patch_input(monkeypatch, ["1", "2", "0"])

    provider_menu.config_providers({}, selected_provider_ids.append)

    assert selected_provider_ids == ["openai"]


def test_config_providers_keeps_custom_openai_choice_last(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected_provider_ids: list[str] = []
    last_choice = len(provider_menu._ordered_provider_ids())
    monkeypatch.setattr(provider_menu, "clear_screen", lambda: None)
    monkeypatch.setattr(provider_menu, "print_banner", lambda: None)
    monkeypatch.setattr(provider_menu, "read_user_config", lambda: {})
    _patch_input(monkeypatch, ["1", str(last_choice), "0"])

    provider_menu.config_providers({}, selected_provider_ids.append)

    assert selected_provider_ids == ["custom_openai"]


def test_config_providers_displays_custom_provider_name_after_reload(
    monkeypatch: pytest.MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    config = {
        "providers": {
            "custom_openai": {
                "display_name": "My Proxy",
                "status": "active",
            }
        }
    }
    monkeypatch.setattr(provider_menu, "clear_screen", lambda: None)
    monkeypatch.setattr(provider_menu, "print_banner", lambda: None)
    monkeypatch.setattr(provider_menu, "read_user_config", lambda: config)
    _patch_input(monkeypatch, ["0"])

    provider_menu.config_providers({}, lambda provider_id: None)

    output = capsys.readouterr().out
    assert "My Proxy" in output
    assert "Custom OpenAI-compatible endpoint" not in output


def test_config_providers_tests_custom_provider_with_custom_name(
    monkeypatch: pytest.MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    config = {
        "providers": {
            "custom_openai": {
                "display_name": "My Proxy",
                "status": "active",
            }
        }
    }
    monkeypatch.setattr(provider_menu, "clear_screen", lambda: None)
    monkeypatch.setattr(provider_menu, "print_banner", lambda: None)
    monkeypatch.setattr(provider_menu, "read_user_config", lambda: config)
    monkeypatch.setattr(
        provider_menu.LLMRuntimeConfig,
        "load",
        lambda: type("Config", (), {"providers": config["providers"]})(),
    )
    monkeypatch.setattr(
        provider_menu,
        "verify_provider",
        lambda provider_id, runtime_config: {"status": "inactive", "error": "HTTP 400"},
    )
    _patch_input(monkeypatch, ["2", "", "0"])

    provider_menu.config_providers({}, lambda provider_id: None)

    output = capsys.readouterr().out
    assert "❌ My Proxy: HTTP 400" in output


def _patch_input(
    monkeypatch: pytest.MonkeyPatch,
    values: list[str],
) -> None:
    iterator = iter(values)

    def fake_input(prompt: str = "") -> str:
        return next(iterator)

    monkeypatch.setattr(builtins, "input", fake_input)
