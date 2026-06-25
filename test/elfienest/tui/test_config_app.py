from __future__ import annotations

import builtins

import pytest
from _pytest.capture import CaptureFixture

from elfienest.tui import config_app, config_editors, provider_menu


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


def _patch_input(
    monkeypatch: pytest.MonkeyPatch,
    values: list[str],
) -> None:
    iterator = iter(values)

    def fake_input(prompt: str = "") -> str:
        return next(iterator)

    monkeypatch.setattr(builtins, "input", fake_input)
