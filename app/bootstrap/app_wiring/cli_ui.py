"""Composition for the concrete terminal presentation adapter."""

from typing import cast

from app.interfaces.cli.tui.menu import TerminalMenuPort
from infrastructure.platform.terminal_menu import TerminalMenu


def build_terminal_menu() -> TerminalMenuPort:
    return cast(
        TerminalMenuPort,
        TerminalMenu(input_fn=input, output_fn=print),
    )


__all__ = ("build_terminal_menu",)
