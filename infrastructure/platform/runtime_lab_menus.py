"""Adapter preserving the existing Runtime Lab tool and Food submenus."""

from __future__ import annotations

from ai_runtime.lab.cli import RuntimeLab


class RuntimeLabMenusAdapter:
    def __init__(self) -> None:
        self._lab = RuntimeLab()

    def tool_menu(self) -> None:
        self._lab.tool_menu()

    def food_menu(self) -> None:
        self._lab.food_menu()


__all__ = ("RuntimeLabMenusAdapter",)
