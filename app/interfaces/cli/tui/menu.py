"""Terminal presentation Port and menu DTOs owned by the CLI Interface."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class MenuItem:
    key: str
    label: str
    hint: str = ""


class TerminalMenuPort(Protocol):
    interactive: bool

    def choose(
        self,
        title: str,
        items: Sequence[MenuItem],
        *,
        breadcrumb: str = "ElfieNest",
        back_label: str = "Back",
    ) -> str | None: ...

    def clear(self) -> None: ...

    def action_header(self, title: str, breadcrumb: str) -> None: ...

    def pause(
        self, message: str = "Press Enter or Left arrow to return..."
    ) -> None: ...

    def read_text(
        self,
        prompt: str,
        *,
        default: str = "",
        masked: bool = False,
        line_input: Callable[[str], str] | None = None,
    ) -> str | None: ...

    def confirm(
        self,
        prompt: str,
        *,
        accept_label: str = "Apply",
        reject_label: str = "Discard",
    ) -> bool: ...


__all__ = ("MenuItem", "TerminalMenuPort")
