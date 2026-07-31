from __future__ import annotations

from ai_runtime.lab.menu import MenuItem, TerminalMenu
from app.features.configuration.user_config import UserConfig, write_user_config
from app.interfaces.cli.tui.common import clear_screen, print_banner


def config_llm(config: UserConfig) -> None:
    _ = config
    clear_screen()
    print_banner()
    print("  🤖 LLM and Food Strategy")
    print("  " + "=" * 45)
    print()
    print("  Provider connections, models and food packages are managed in AI Runtime.")
    try:
        input("Press Enter to return...")
    except (EOFError, KeyboardInterrupt):
        return


def config_engine(config: UserConfig) -> None:
    menu = TerminalMenu(input_fn=input, output_fn=print)
    while True:
        engine = config.setdefault("system", {}).setdefault("engine", {})
        choice = menu.choose(
            "Engine Parameters",
            (
                MenuItem(
                    "1", f"Tick interval (sec): {engine.get('tick_interval_sec', 1.5)}"
                ),
                MenuItem(
                    "2", f"Max elfies per room: {engine.get('max_elfies_per_room', 10)}"
                ),
            ),
            breadcrumb="ElfieNest / Config / App / Engine",
            back_label="Save and return",
        )
        if choice is None:
            write_user_config(config)
            return
        if choice == "1":
            _set_float(
                menu,
                engine,
                "tick_interval_sec",
                "Enter tick interval (sec)",
                1.5,
                minimum=0.01,
            )
        elif choice == "2":
            _set_int(
                menu,
                engine,
                "max_elfies_per_room",
                "Enter max elfies per room",
                10,
                minimum=1,
                maximum=32,
            )


def config_security(config: UserConfig) -> None:
    menu = TerminalMenu(input_fn=input, output_fn=print)
    while True:
        security = config.setdefault("system", {}).setdefault("security", {})
        rate_limit = security.setdefault("rate_limit", {})
        choice = menu.choose(
            "Session and Security",
            (
                MenuItem(
                    "1", f"Session TTL (days): {security.get('session_ttl_days', 7)}"
                ),
                MenuItem(
                    "2", f"Max login attempts: {rate_limit.get('max_attempts', 5)}"
                ),
                MenuItem(
                    "3",
                    f"Rate limit window (sec): {rate_limit.get('window_seconds', 300)}",
                ),
            ),
            breadcrumb="ElfieNest / Config / Owner and Security",
            back_label="Save and return",
        )
        if choice is None:
            write_user_config(config)
            return
        if choice == "1":
            _set_int(
                menu,
                security,
                "session_ttl_days",
                "Enter session TTL (days)",
                7,
                minimum=1,
                maximum=90,
            )
        elif choice == "2":
            _set_int(
                menu,
                rate_limit,
                "max_attempts",
                "Enter max failed attempts in window",
                5,
                minimum=1,
                maximum=100,
            )
        elif choice == "3":
            _set_int(
                menu,
                rate_limit,
                "window_seconds",
                "Enter rate limit window (sec)",
                300,
                minimum=1,
                maximum=3600,
            )


def config_adoption(config: UserConfig) -> None:
    menu = TerminalMenu(input_fn=input, output_fn=print)
    while True:
        adoption = config.setdefault("system", {}).setdefault("adoption", {})
        allowed = adoption.setdefault("allowed_species_ids", ["dog", "fox"])
        enabled = adoption.setdefault("personality_presets_enabled", {})
        if not enabled:
            enabled.update(dict.fromkeys(_PERSONALITY_PRESETS, True))
        choice = menu.choose(
            "Elfie Adoption",
            (
                MenuItem(
                    "1",
                    f"Max elfies per user: {adoption.get('max_elfies_per_user', 3)}",
                ),
                MenuItem("2", f"Allowed species: {', '.join(allowed)}"),
                MenuItem("3", "Personality preset toggles"),
            ),
            breadcrumb="ElfieNest / Config / App / Elfie Adoption",
            back_label="Save and return",
        )
        if choice is None:
            write_user_config(config)
            return
        if choice == "1":
            _set_int(
                menu,
                adoption,
                "max_elfies_per_user",
                "Enter max elfies per user",
                3,
                minimum=1,
                maximum=32,
            )
        elif choice == "2":
            _toggle_species_menu(menu, adoption)
        elif choice == "3":
            _toggle_personality_menu(menu, enabled)


_PERSONALITY_PRESETS = ("Energetic", "Calm", "Curious", "Timid", "Tsundere", "Random")


def _toggle_species_menu(menu: TerminalMenu, adoption: UserConfig) -> None:
    labels = {"dog": "Dog", "fox": "Fox"}
    while True:
        allowed = adoption.setdefault("allowed_species_ids", ["dog", "fox"])
        choice = menu.choose(
            "Allowed Elfie Species",
            tuple(
                MenuItem(
                    str(index),
                    f"{labels[key]}: {'enabled' if key in allowed else 'disabled'}",
                )
                for index, key in enumerate(labels, 1)
            ),
            breadcrumb="ElfieNest / Config / App / Elfie Adoption / Species",
            back_label="Back to adoption config",
        )
        if choice is None:
            return
        if choice not in {"1", "2"}:
            continue
        key = tuple(labels)[int(choice) - 1]
        if key in allowed and len(allowed) == 1:
            continue
        if key in allowed:
            allowed.remove(key)
        else:
            allowed.append(key)


def _toggle_personality_menu(menu: TerminalMenu, enabled: UserConfig) -> None:
    while True:
        choice = menu.choose(
            "Personality Preset Toggles",
            tuple(
                MenuItem(
                    str(index),
                    f"{name}: {'enabled' if enabled.get(name, True) else 'disabled'}",
                )
                for index, name in enumerate(_PERSONALITY_PRESETS, 1)
            ),
            breadcrumb="ElfieNest / Config / App / Elfie Adoption / Personality",
            back_label="Back to adoption config",
        )
        if choice is None:
            return
        if not choice.isdigit() or not 1 <= int(choice) <= len(_PERSONALITY_PRESETS):
            continue
        name = _PERSONALITY_PRESETS[int(choice) - 1]
        if sum(bool(value) for value in enabled.values()) == 1 and enabled.get(
            name, True
        ):
            continue
        enabled[name] = not enabled.get(name, True)


def _set_float(
    menu: TerminalMenu,
    section: UserConfig,
    key: str,
    prompt: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> None:
    try:
        raw = menu.read_text(
            f"{prompt} [{section.get(key, default)}]: ", default=str(default)
        )
        if raw is None:
            return
        value = float(raw)
        if minimum is not None and value < minimum:
            raise ValueError
        if maximum is not None and value > maximum:
            raise ValueError
    except (TypeError, ValueError):
        print("❌ Invalid input")
        return
    section[key] = value


def _set_int(
    menu: TerminalMenu,
    section: UserConfig,
    key: str,
    prompt: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> None:
    try:
        raw = menu.read_text(
            f"{prompt} [{section.get(key, default)}]: ", default=str(default)
        )
        if raw is None:
            return
        value = int(raw)
        if minimum is not None and value < minimum:
            raise ValueError
        if maximum is not None and value > maximum:
            raise ValueError
    except (TypeError, ValueError):
        print("❌ Invalid input")
        return
    section[key] = value
