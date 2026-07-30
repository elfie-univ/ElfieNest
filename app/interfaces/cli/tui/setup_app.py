"""Terminal setup wizard: reuse Web's five-step Setup state and feature service."""

from __future__ import annotations

from ai_runtime.storage.data_home import get_config_path, get_db_path
from app.features.configuration.runtime_store import (
    read_runtime_config,
    write_runtime_config,
)
from app.features.setup.ollama import OllamaSetupService
from app.features.setup.progress import complete_setup_step, get_setup_progress
from app.features.setup.service import (
    SetupAlreadyCompleteError,
    create_first_owner_account,
)
from app.infrastructure.ollama_platform import OllamaPlatformAdapter
from app.infrastructure.persistence.nest_repository import SQLiteNestRepository
from app.infrastructure.persistence.store import get_db, init_db
from app.interfaces.cli.tui.common import (
    clear_screen,
    input_password,
    input_text,
    print_banner,
    print_success_panel,
    print_tui_panel,
    rich_console,
)


def run_setup_wizard() -> None:
    clear_screen()
    print_banner()
    print_tui_panel("ElfieNest Setup", "Initialization wizard before first launch")
    db_path = str(get_db_path())
    init_db(db_path)

    progress = get_setup_progress(db_path)

    if progress.complete:
        print("  ✅ System initialized")
        print()
        print("  Setup completed the following steps:")
        print("    1. Owner account")
        print("    2. Device and offline support")
        print("    3. Nest settings")
        print("    4. Model and food")
        print("    5. Confirmation")
        print()
        print("  💡 To re-run Setup, use 'uninstall' to clean data first")
        print()
        return

    if progress.current_step == 1:
        print(f"  Current step: {progress.current_step}/5 - Create Owner account")
    else:
        print(f"  Current step: {progress.current_step}/5")

    print()
    print("  Continue Setup wizard?")

    try:
        choice = input("  [y/N]: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\n  Cancelled.")
        return

    if choice != "y":
        print("\n  Cancelled. Run 'elfienest setup' later to continue.")
        return

    print()
    if not _complete_owner(db_path):
        return
    if not _complete_ollama(db_path):
        return
    if not _complete_nest(db_path):
        return
    if not _complete_model(db_path):
        return
    _complete_confirmation(db_path)


def _complete_owner(db_path: str) -> bool:
    progress = get_setup_progress(db_path)
    if progress.current_step != 1:
        return True
    _print_step("1/5", "Create Owner account")
    username = input_text("  Owner login name", "owner") or "owner"
    display_name = input_text("  Owner display name", username) or username
    password = input_password("  Owner password")
    if password is None:
        print(
            "  ❌ Cannot safely input Owner password in this terminal, setup cancelled"
        )
        return False
    if not 3 <= len(username.strip()) <= 32 or not 6 <= len(password) <= 128:
        print("  ❌ Owner credentials do not meet requirements, setup cancelled")
        return False
    try:
        create_first_owner_account(
            db_path,
            username=username.strip(),
            password=password,
            display_name=display_name.strip(),
        )
    except SetupAlreadyCompleteError as error:
        print(f"  ⚠️  Owner already exists or creation failed: {error}")
        return False
    print(f"  ✅ Owner '{username.strip()}' created successfully")
    return True


def _complete_ollama(db_path: str) -> bool:
    progress = get_setup_progress(db_path)
    if progress.current_step != 2:
        return True
    _print_step("2/5", "Device and offline support")
    print(
        "  Ollama is a local backup when offline or cloud unavailable, can maintain basic elfie capabilities."
    )
    print(
        "  Optional: bind existing public Ollama, install from official site, or skip for now."
    )
    choice = (
        (input_text("  Choose [skip/bind/install]", "skip") or "skip").strip().lower()
    )
    if choice == "skip":
        complete_setup_step(db_path, step=2, decision="skipped")
        return True
    if choice == "bind":
        endpoint = input_text("  Existing Ollama endpoint", "http://127.0.0.1:11434")
        if not endpoint:
            print("  ❌ Endpoint required")
            return False
        try:
            _ollama_service().bind_existing(db_path=db_path, endpoint=endpoint.strip())
        except (RuntimeError, ValueError) as error:
            print(f"  ❌ Cannot bind Ollama: {error}")
            return False
        return True
    if choice == "install":
        confirmed = (
            input_text(
                "  Confirm download and run installer from official Ollama site? [y/N]",
                "n",
            )
            or "n"
        ).lower()
        if confirmed != "y":
            print("  Ollama installation cancelled")
            return False
        try:
            _ollama_service().install_official(
                db_path=db_path,
                endpoint="http://127.0.0.1:11434",
                user_confirmed=True,
            )
        except (RuntimeError, ValueError, PermissionError) as error:
            print(f"  ❌ Official Ollama installation failed: {error}")
            return False
        return True
    print("  ❌ Invalid choice; Setup state unchanged")
    return False


def _complete_nest(db_path: str) -> bool:
    progress = get_setup_progress(db_path)
    if progress.current_step != 3:
        return True
    _print_step("3/5", "Nest settings")
    raw = input_text("  Bed count (4-32)", "4") or "4"
    try:
        bed_count = int(raw)
    except ValueError:
        print("  ❌ Bed count must be integer")
        return False
    if not 4 <= bed_count <= 32:
        print("  ❌ Bed count must be between 4 and 32")
        return False
    with get_db(db_path) as conn:
        SQLiteNestRepository(conn).set_desired_bed_count(bed_count)
        conn.commit()
    complete_setup_step(db_path, step=3)
    return True


def _complete_model(db_path: str) -> bool:
    progress = get_setup_progress(db_path)
    if progress.current_step != 4:
        return True
    _print_step("4/5", "Model and food")
    choice = (
        (input_text("  Choose [skip/existing/pull]", "skip") or "skip").strip().lower()
    )
    if choice == "skip":
        complete_setup_step(db_path, step=4, decision="skipped")
        return True
    model_reference = input_text("  Model (provider_id/model_id)", "")
    if not model_reference:
        print("  ❌ Full provider_id/model_id required")
        return False
    try:
        service = _ollama_service()
        if choice == "existing":
            service.configure_installed_model(
                db_path=db_path,
                model_reference=model_reference.strip(),
            )
            return True
        if choice == "pull":
            confirmed = (
                input_text("  Confirm downloading this model? [y/N]", "n") or "n"
            ).lower()
            if confirmed != "y":
                print("  Model download cancelled")
                return False
            service.pull_and_configure_model(
                db_path=db_path,
                model_reference=model_reference.strip(),
            )
            return True
    except (RuntimeError, ValueError) as error:
        print(f"  ❌ Model configuration failed: {error}")
        return False
    print("  ❌ Invalid choice; Setup state unchanged")
    return False


def _complete_confirmation(db_path: str) -> None:
    progress = get_setup_progress(db_path)
    if progress.current_step != 5 or progress.complete:
        return
    _print_step("5/5", "Confirmation")
    confirmed = (
        input_text("  Complete initialization and enter admin menu? [y/N]", "y") or "y"
    ).lower()
    if confirmed != "y":
        print("  Current progress saved; continue later.")
        return
    complete_setup_step(db_path, step=5)
    print_success_panel(["Setup complete!", "Start service: elfienest"])


def _ollama_service() -> OllamaSetupService:
    config_path = get_config_path()
    return OllamaSetupService(
        adapter=OllamaPlatformAdapter(),
        read_config=lambda: read_runtime_config(config_path),
        write_config=lambda config: write_runtime_config(config_path, config),
    )


def _print_step(step: str, title: str) -> None:
    console = rich_console()
    if console is None:
        print(f"  【Step {step}】{title}")
        return
    console.print(f"  [bold magenta]Step {step}[/] [white]{title}[/]")
