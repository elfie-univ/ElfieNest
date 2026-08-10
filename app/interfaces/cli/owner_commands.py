"""Local Owner account menu."""

from __future__ import annotations

import getpass
import warnings
from pathlib import Path
from typing import Optional

from ai_runtime.lab.menu import MenuItem, TerminalMenu
from ai_runtime.storage.data_home import get_db_path
from app.features.accounts import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    AccountsError,
    AccountsService,
    GetOwnerAccountQuery,
    PasswordPolicyError,
    RecoverOwnerAccountCommand,
    validate_password_strength,
)
from app.interfaces.cli.tui.common import input_password, input_text
from app.orchestration.lifecycle import LifecycleFacade, RecoveryInProgressError

MIN_OWNER_ACCOUNT_ID_LENGTH = 3
MAX_OWNER_ACCOUNT_ID_LENGTH = 32
MIN_OWNER_PASSWORD_LENGTH = MIN_PASSWORD_LENGTH
MAX_OWNER_PASSWORD_LENGTH = MAX_PASSWORD_LENGTH


def show_owner_account(service: AccountsService) -> int:
    try:
        account = service.get_owner_account(GetOwnerAccountQuery())
    except AccountsError as error:
        print(f"  ❌ Cannot read Owner account: {error}")
        return 1
    print("  👤 Owner Account Information")
    print("  " + "=" * 45)
    print(f"  User ID: {account.user_id}")
    print(f"  Login account: {account.account_id}")
    print(f"  Display name: {account.display_name or 'unset'}")
    print(f"  Password status: {account.password_status}")
    print(f"  Created at: {account.created_at or 'unknown'}")
    print(f"  Last updated: {account.updated_at or 'unknown'}")
    print()
    return 0


def show_owner_account_page(
    menu: TerminalMenu,
    service: AccountsService,
) -> int:
    menu.action_header("Owner Account Information", "ElfieNest / Owner / View Account")
    exit_code = show_owner_account(service)
    menu.pause("Press Enter, ← or Esc to return to Owner menu…")
    return exit_code


def recover_owner_interactive(
    lifecycle: LifecycleFacade,
    service: AccountsService,
    db_path: Optional[str] = None,
    *,
    menu: TerminalMenu | None = None,
) -> int:
    owner_menu = menu or TerminalMenu(input_fn=input, output_fn=print)
    if menu is not None:
        owner_menu.action_header(
            "Recover Owner Account", "ElfieNest / Owner / Recover Account"
        )
        print(
            "  This operation will modify both Owner login account and password, and revoke old sessions."
        )
        print("  Press Esc, ← or choose Back to cancel.")
        print()
        if not owner_menu.confirm(
            "Start recovery?",
            accept_label="Start Recovery",
            reject_label="Back",
        ):
            print("  Cancelled, no changes made")
            return 1

    path = db_path or str(get_db_path())
    if not Path(path).expanduser().is_file():
        print(
            f"  ❌ Cannot recover Owner: database not found ({Path(path).expanduser()})"
        )
        return 1
    if menu is None:
        account_id = input_text("  New Owner login account")
    else:
        account_id = owner_menu.read_text("  New Owner login account (Esc to cancel): ")
    if not account_id:
        print("  ❌ Cancelled, no changes made")
        return 1
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            if menu is None:
                first = input_password("  New Owner password")
                second = input_password("  Re-enter new Owner password")
            else:
                first = owner_menu.read_text(
                    "  New Owner password (Esc to cancel): ",
                    masked=True,
                )
                second = owner_menu.read_text(
                    "  Re-enter new Owner password (Esc to cancel): ",
                    masked=True,
                )
    except (EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        print("  ❌ Password input interrupted, no changes made")
        return 1
    if first is None or second is None:
        print("  ❌ Cancelled, no changes made")
        return 1
    if first != second:
        print("  ❌ Passwords do not match, no changes made")
        return 1
    if (
        not MIN_OWNER_ACCOUNT_ID_LENGTH
        <= len(account_id.strip())
        <= MAX_OWNER_ACCOUNT_ID_LENGTH
    ):
        print(
            f"  ❌ New login account must be {MIN_OWNER_ACCOUNT_ID_LENGTH}-{MAX_OWNER_ACCOUNT_ID_LENGTH} characters"
        )
        return 1
    try:
        validate_password_strength(first)
    except PasswordPolicyError:
        print(
            f"  ❌ New password must be {MIN_OWNER_PASSWORD_LENGTH}-{MAX_OWNER_PASSWORD_LENGTH} characters"
        )
        return 1
    try:
        with lifecycle.owner_recovery(Path(path).resolve().parent):
            account = service.recover_owner_account(
                RecoverOwnerAccountCommand(
                    account_id=account_id,
                    new_password=first,
                )
            )
    except (AccountsError, OSError, RecoveryInProgressError) as error:
        print(f"  ❌ Owner recovery failed: {error}")
        return 1
    print(f"  ✅ Owner account recovered: {account.account_id}")
    print("  Old sessions revoked. Use new login account and password to access Web.")
    return 0


def run_owner_menu(
    lifecycle: LifecycleFacade,
    service: AccountsService,
    db_path: Optional[str] = None,
) -> int:
    menu = TerminalMenu(input_fn=input, output_fn=print)
    last_exit_code = 0
    while True:
        try:
            choice = menu.choose(
                "Owner Account",
                (
                    MenuItem("1", "View Owner Account Information"),
                    MenuItem("2", "Recover Owner Account"),
                ),
                breadcrumb="ElfieNest / Owner",
                back_label="Back to Home",
            )
        except (EOFError, KeyboardInterrupt):
            return 1
        if choice is None:
            return last_exit_code
        if choice == "1":
            last_exit_code = show_owner_account_page(menu, service)
        elif choice == "2":
            last_exit_code = recover_owner_interactive(
                lifecycle,
                service,
                db_path,
                menu=menu,
            )
