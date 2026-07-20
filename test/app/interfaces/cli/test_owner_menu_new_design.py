from __future__ import annotations

import builtins

from app.interfaces.cli import owner_commands
from app.features.administration.owner_service import OwnerAccount
from ai_runtime.lab.menu import TerminalMenu


def test_owner_menu_has_three_items_and_shares_actions(monkeypatch, capsys) -> None:
    # Given
    choices = iter(("1", "2", "0"))
    calls: list[str] = []
    monkeypatch.setattr(builtins, "input", lambda _prompt: next(choices))
    monkeypatch.setattr(
        owner_commands,
        "show_owner_account",
        lambda *_args: calls.append("view") or 0,
    )
    monkeypatch.setattr(
        owner_commands,
        "recover_owner_interactive",
        lambda **_kwargs: calls.append("recover") or 0,
    )

    # When
    result = owner_commands.run_owner_menu()

    # Then
    output = capsys.readouterr().out
    assert result == 0
    assert calls == ["view", "recover"]
    assert "查看 Owner 账号信息" in output
    assert "恢复 Owner 账号" in output
    assert "Owner" in output


def test_owner_account_view_is_a_detail_page_with_pause(monkeypatch, capsys) -> None:
    # Given
    keys = iter(("escape",))
    menu = TerminalMenu(
        input_fn=input,
        output_fn=print,
        key_reader=lambda: next(keys),
        interactive=True,
    )
    monkeypatch.setattr(
        owner_commands,
        "get_owner_account",
        lambda _path=None: OwnerAccount(
            user_id=7,
            username="owner",
            created_at="2026-07-16T01:02:03Z",
            updated_at="2026-07-16T04:05:06Z",
        ),
    )

    # When
    result = owner_commands.show_owner_account_page(menu)

    # Then
    output = capsys.readouterr().out
    assert result == 0
    assert "ElfieNest / Owner / 查看账号" in output
    assert "User ID: 7" in output
    assert "登录名: owner" in output
    assert "密码状态: 已设置" in output


def test_owner_recovery_can_be_cancelled_before_input(monkeypatch, capsys) -> None:
    # Given
    keys = iter(("escape",))
    menu = TerminalMenu(
        input_fn=input,
        output_fn=print,
        key_reader=lambda: next(keys),
        interactive=True,
    )
    calls: list[str] = []
    monkeypatch.setattr(
        owner_commands,
        "recover_owner_account",
        lambda *args: calls.append("recover"),
    )

    # When
    result = owner_commands.recover_owner_interactive("/tmp/missing.db", menu=menu)

    # Then
    output = capsys.readouterr().out
    assert result == 1
    assert calls == []
    assert "恢复 Owner 账号" in output
    assert "已取消" in output
