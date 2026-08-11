"""Uninstall and data cleanup commands."""

from __future__ import annotations

from pathlib import Path

from app.interfaces.cli.tui.common import clear_screen, print_banner, print_tui_panel
from app.interfaces.cli.tui.menu import MenuItem, TerminalMenuPort
from app.orchestration.lifecycle import LifecycleFacade


def run_uninstall_menu(
    lifecycle: LifecycleFacade,
    menu: TerminalMenuPort,
) -> int:
    """Interactive uninstall menu, returns exit code."""
    clear_screen()
    print_banner()
    print_tui_panel(
        "Uninstall Wizard",
        "Choose what to clean up; reinstall and run Setup after uninstall",
    )

    state = lifecycle.uninstall_state()
    elfie_home = state.data_home

    choice = menu.choose(
        "Uninstall Options",
        (
            MenuItem(
                "1",
                "Uninstall app only (keep all data and config)",
                "App files managed by installer",
            ),
            MenuItem(
                "2",
                "Uninstall and delete config",
                _status_hint(
                    [state.config_exists, state.env_exists],
                    ["configs/runtime.yaml", "configs/auth.env"],
                ),
            ),
            MenuItem(
                "3",
                "Uninstall and delete all data",
                _status_hint([state.home_exists], [str(elfie_home)]),
            ),
        ),
        breadcrumb="ElfieNest / Uninstall",
        back_label="Cancel",
    )

    if choice is None:
        print("\nCancelled.")
        return 0

    if choice == "1":
        print("\n⚠️  Use installer or package manager to uninstall app.")
        print("   This command only handles data directory, not app files.")
        print("\nTip: All data preserved, ready to use after reinstall.")
        return 0

    if choice == "2":
        return _delete_config(lifecycle, elfie_home)

    if choice == "3":
        return _delete_all(lifecycle, elfie_home, state.home_exists)

    return 2


def _status_hint(exists_checks: list[bool | None], names: list[str]) -> str:
    if not any(exists_checks):
        return "(not exists)"

    items = []
    for i, name in enumerate(names):
        if i < len(exists_checks) and exists_checks[i]:
            items.append(name)

    if not items:
        return "(not exists)"

    return f"Will delete: {', '.join(items)}"


def _delete_config(lifecycle: LifecycleFacade, elfie_home: Path) -> int:
    print("\n⚠️  Will delete Runtime config and API Keys, keep database and elfie data.")
    print(f"   Config directory: {elfie_home}")
    print()

    confirm = input("Type 'yes' to confirm: ").strip()
    if confirm.lower() != "yes":
        print("\nCancelled.")
        return 0

    deleted = []
    try:
        if lifecycle.delete_local_config():
            deleted.append("configs/")
    except OSError as error:
        print(f"\n❌ Failed to delete config directory: {error}")
        return 1

    if deleted:
        print(f"\n✅ Deleted: {', '.join(deleted)}")
        print("   Default config will be used after service restart.")
    else:
        print("\nℹ️  Config files not found, nothing to delete.")

    return 0


def _delete_all(
    lifecycle: LifecycleFacade,
    elfie_home: Path,
    home_exists: bool,
) -> int:
    print("\n⚠️  Will delete all data, including:")
    print("   - Config files (configs/runtime.yaml, configs/auth.env)")
    print("   - Databases (nest.db, history.sqlite, knowledge.sqlite)")
    print("   - Elfie workspaces (elfies/)")
    print("   - All other user data")
    print()
    print(f"   Data directory: {elfie_home}")
    print()

    confirm = input("Type 'yes' to confirm: ").strip()
    if confirm.lower() != "yes":
        print("\nCancelled.")
        return 0

    if not home_exists:
        print("\nℹ️  Data directory not found, nothing to delete.")
        return 0

    try:
        lifecycle.delete_all_local_data()
    except OSError as error:
        print(f"\n❌ Delete failed: {error}")
        return 1

    print(f"\n✅ Data directory deleted: {elfie_home}")
    print("   Setup wizard will run after reinstall.")

    return 0
