from __future__ import annotations

import builtins
from dataclasses import dataclass

from ai_runtime.lab.menu import TerminalMenu
from app.bootstrap.lifecycle import create_lifecycle_facade
from app.features.accounts import GetOwnerAccountQuery, OwnerAccountResult
from app.interfaces.cli import owner_commands

LIFECYCLE = create_lifecycle_facade()


@dataclass
class OwnerServiceStub:
    account: OwnerAccountResult

    def get_owner_account(self, query: GetOwnerAccountQuery) -> OwnerAccountResult:
        _ = query
        return self.account


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
        lambda *_args, **_kwargs: calls.append("recover") or 0,
    )

    # When
    result = owner_commands.run_owner_menu(
        LIFECYCLE,
        OwnerServiceStub(
            OwnerAccountResult(
                user_id=7,
                account_id="owner",
                display_name=None,
                created_at="2026-07-16T01:02:03Z",
                updated_at="2026-07-16T04:05:06Z",
            )
        ),
    )

    # Then
    output = capsys.readouterr().out
    assert result == 0
    assert calls == ["view", "recover"]
    assert "View Owner Account Information" in output
    assert "Recover Owner Account" in output
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
    service = OwnerServiceStub(
        OwnerAccountResult(
            user_id=7,
            account_id="owner",
            display_name=None,
            created_at="2026-07-16T01:02:03Z",
            updated_at="2026-07-16T04:05:06Z",
        )
    )

    # When
    result = owner_commands.show_owner_account_page(menu, service)

    # Then
    output = capsys.readouterr().out
    assert result == 0
    assert "ElfieNest / Owner / View Account" in output
    assert "User ID: 7" in output
    assert "Login account: owner" in output
    assert "Username:" not in output
    assert "Password status: Set (not viewable)" in output


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
    service = OwnerServiceStub(
        OwnerAccountResult(
            user_id=7,
            account_id="owner",
            display_name=None,
            created_at="2026-07-16T01:02:03Z",
            updated_at="2026-07-16T04:05:06Z",
        )
    )

    # When
    result = owner_commands.recover_owner_interactive(
        LIFECYCLE, service, "/tmp/missing.db", menu=menu
    )

    # Then
    output = capsys.readouterr().out
    assert result == 1
    assert calls == []
    assert "Recover Owner Account" in output
    assert "Cancelled" in output
