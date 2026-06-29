from __future__ import annotations

import builtins

import pytest
from _pytest.capture import CaptureFixture

from elfienest.cli.tui import config_app, config_editors, provider_menu


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
    assert "配置菜单" in output
    assert "再见" in output


def test_config_llm_saves_updated_cheap_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = {"system": {"llm": {"default_cheap_model": "old-model"}}}
    saved_configs: list[dict[str, object]] = []
    monkeypatch.setattr(config_editors, "clear_screen", lambda: None)
    monkeypatch.setattr(config_editors, "print_banner", lambda: None)
    monkeypatch.setattr(config_editors, "write_user_config", saved_configs.append)
    _patch_input(monkeypatch, ["1", "new-model", "0", ""])

    config_editors.config_llm(config)

    assert config["system"]["llm"]["default_cheap_model"] == "new-model"
    assert saved_configs == [config]


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
                "display_name": "我的代理",
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
    assert "我的代理" in output
    assert "自定义 OpenAI 兼容接口" not in output


def test_config_providers_tests_custom_provider_with_custom_name(
    monkeypatch: pytest.MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    config = {
        "providers": {
            "custom_openai": {
                "display_name": "我的代理",
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
    assert "❌ 我的代理: HTTP 400" in output


def _patch_input(
    monkeypatch: pytest.MonkeyPatch,
    values: list[str],
) -> None:
    iterator = iter(values)

    def fake_input(prompt: str = "") -> str:
        return next(iterator)

    monkeypatch.setattr(builtins, "input", fake_input)
