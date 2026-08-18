"""TUI entry points loaded lazily to keep command modules acyclic."""

__all__ = ["run_config_tui"]


def __getattr__(name: str) -> object:
    if name == "run_config_tui":
        from .config_app import run_config_tui

        return run_config_tui
    raise AttributeError(name)
