"""Local Owner account menu."""

from __future__ import annotations

import getpass
import warnings
from pathlib import Path
from typing import Optional

from ai_runtime.lab.menu import MenuItem, TerminalMenu
from ai_runtime.storage.data_home import get_db_path
from app.features.administration.owner_service import (
    MAX_OWNER_PASSWORD_LENGTH,
    MIN_OWNER_PASSWORD_LENGTH,
    OwnerServiceError,
    get_owner_account,
    recover_owner_account,
)
from app.interfaces.cli.tui.common import input_password, input_text
from app.orchestration.lifecycle.recovery_lock import (
    RecoveryInProgressError,
    owner_recovery_lock,
)


def show_owner_account(db_path: Optional[str] = None) -> int:
    path = db_path or str(get_db_path())
    try:
        account = get_owner_account(path)
    except OwnerServiceError as error:
        print(f"  ❌ Cannot read Owner account: {error}")
        return 1
    print("  👤 Owner Account Information")
    print("  " + "=" * 45)
    print(f"  User ID: {account.user_id}")
    print(f"  Username: {account.username}")
    print(f"  Password status: {account.password_status}")
    print(f"  Created at: {account.created_at or 'unknown'}")
    print(f"  Last updated: {account.updated_at or 'unknown'}")
    print()
    return 0


def show_owner_account_page(
    menu: TerminalMenu,
    db_path: Optional[str] = None,
) -> int:
    menu.action_header("Owner Account Information", "ElfieNest / Owner / View Account")
    exit_code = show_owner_account(db_path)
    menu.pause("Press Enter, ← or Esc to return to Owner menu…")
    return exit_code


def recover_owner_interactive(
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
            "  This operation will modify both Owner username and password, and revoke old sessions."
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
        username = input_text("  New Owner username")
    else:
        username = owner_menu.read_text("  New Owner username (Esc to cancel): ")
    if not username:
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
    if not MIN_OWNER_PASSWORD_LENGTH <= len(first) <= MAX_OWNER_PASSWORD_LENGTH:
        print(
            f"  ❌ New password must be {MIN_OWNER_PASSWORD_LENGTH}-{MAX_OWNER_PASSWORD_LENGTH} characters"
        )
        return 1
    try:
        with owner_recovery_lock(Path(path).resolve().parent):
            account = recover_owner_account(path, username, first)
    except (OwnerServiceError, OSError, RecoveryInProgressError) as error:
        print(f"  ❌ Owner recovery failed: {error}")
        return 1
    print(f"  ✅ Owner account recovered: {account.username}")
    print("  Old sessions revoked. Use new username and password to access Web.")
    return 0


def run_owner_menu() -> int:
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
            last_exit_code = show_owner_account_page(menu)
        elif choice == "2":
            last_exit_code = recover_owner_interactive(menu=menu)
