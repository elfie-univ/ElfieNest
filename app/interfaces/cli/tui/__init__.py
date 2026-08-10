"""TUI entry points loaded lazily to keep command modules acyclic."""

__all__ = ["run_config_tui", "run_setup_wizard"]


def __getattr__(name: str) -> object:
    if name == "run_config_tui":
        from .config_app import run_config_tui

        return run_config_tui
    if name == "run_setup_wizard":
        from .setup_app import run_setup_wizard

        return run_setup_wizard
    raise AttributeError(name)
