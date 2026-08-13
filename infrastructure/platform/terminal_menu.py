"""Single-screen keyboard menu adapter."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, cast


@dataclass(frozen=True)
class MenuItem:
    key: str
    label: str
    hint: str = ""


class TerminalMenu:
    """Use arrow keys in TTY; fall back to line input for tests or redirection."""

    def __init__(
        self,
        *,
        input_fn: Callable[[str], str] = input,
        output_fn: Callable[[str], None] = print,
        key_reader: Callable[[], str] | None = None,
        clipboard_reader: Callable[[], str] | None = None,
        interactive: bool | None = None,
    ) -> None:
        self.input = input_fn
        self.output = output_fn
        self.key_reader = key_reader or _read_key
        self.clipboard_reader = clipboard_reader or _read_clipboard
        self.interactive = (
            sys.stdin.isatty() and sys.stdout.isatty()
            if interactive is None
            else interactive
        )

    def choose(
        self,
        title: str,
        items: Sequence[MenuItem],
        *,
        breadcrumb: str = "ElfieNest",
        back_label: str = "Back",
    ) -> str | None:
        if not items:
            return None
        if not self.interactive:
            return self._choose_line(title, items, breadcrumb, back_label)

        selected = 0
        while True:
            self._render(title, items, selected, breadcrumb, back_label)
            key = self.key_reader()
            if key == "up":
                selected = (selected - 1) % len(items)
            elif key == "down":
                selected = (selected + 1) % len(items)
            elif key in {"enter", "right"}:
                return items[selected].key
            elif key in {"left", "escape", "backspace", "0"}:
                return None
            elif key.isdigit():
                matched = next((item for item in items if item.key == key), None)
                if matched is not None:
                    return matched.key

    def clear(self) -> None:
        if self.interactive:
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()

    def action_header(self, title: str, breadcrumb: str) -> None:
        self.clear()
        self.output(f"{breadcrumb}\n{'─' * min(max(len(title) + 8, 24), 56)}")
        self.output(title)
        self.output("")

    def pause(self, message: str = "Press Enter or Left arrow to return...") -> None:
        if not self.interactive:
            return
        sys.stdout.write(f"\n\033[2m{message}\033[0m")
        sys.stdout.flush()
        while self.key_reader() not in {"enter", "left", "escape", "backspace"}:
            pass

    def read_text(
        self,
        prompt: str,
        *,
        default: str = "",
        masked: bool = False,
        line_input: Callable[[str], str] | None = None,
    ) -> str | None:
        """Read single-line text that can be cancelled by Esc.

        TTY mode uses raw keys, Esc cancels without Enter;
        redirection or test mode uses normal line input.
        """
        if not self.interactive:
            try:
                raw = (line_input or self.input)(prompt)
            except (EOFError, KeyboardInterrupt):
                return None
            return None if raw == "\x1b" else raw.strip() or default

        sys.stdout.write(prompt)
        sys.stdout.flush()
        chars: list[str] = []
        cursor = 0

        def redraw() -> None:
            visible = "•" * len(chars) if masked else "".join(chars)
            move_left = len(chars) - cursor
            sys.stdout.write(f"\r{prompt}{visible}\033[K")
            if move_left:
                sys.stdout.write(f"\033[{move_left}D")
            sys.stdout.flush()

        while True:
            key = self.key_reader()
            if key == "interrupt":
                sys.stdout.write("\n\033[2mCancelled.\033[0m\n")
                sys.stdout.flush()
                return None
            if key == "escape":
                sys.stdout.write("\n\033[2mCancelled.\033[0m\n")
                sys.stdout.flush()
                return None
            if key == "enter":
                sys.stdout.write("\n")
                sys.stdout.flush()
                return "".join(chars).strip() or default
            if key == "left":
                cursor = max(0, cursor - 1)
                redraw()
                continue
            if key == "right":
                cursor = min(len(chars), cursor + 1)
                redraw()
                continue
            if key == "backspace":
                if cursor:
                    del chars[cursor - 1]
                    cursor -= 1
                    redraw()
                continue
            if key == "paste":
                try:
                    pasted = self.clipboard_reader()
                except (OSError, RuntimeError, subprocess.SubprocessError):
                    sys.stdout.write("\a")
                    sys.stdout.flush()
                    continue
                pasted = pasted.strip().replace("\r", "").replace("\n", "")
                if pasted:
                    chars[cursor:cursor] = pasted
                    cursor += len(pasted)
                    redraw()
                continue
            if len(key) == 1 and key.isprintable():
                chars.insert(cursor, key)
                cursor += 1
                redraw()

    def confirm(
        self,
        prompt: str,
        *,
        accept_label: str = "Apply",
        reject_label: str = "Discard",
    ) -> bool:
        """Display confirmation buttons below current preview, safe default to discard."""
        if not self.interactive:
            try:
                answer = self.input(f"{prompt} [y/N]: ")
            except (EOFError, KeyboardInterrupt):
                return False
            return answer.strip().lower() == "y"

        accepted = False
        while True:
            reject = (
                f"\033[36;1m[ {reject_label} ]\033[0m"
                if not accepted
                else f"[ {reject_label} ]"
            )
            accept = (
                f"\033[36;1m[ {accept_label} ]\033[0m"
                if accepted
                else f"[ {accept_label} ]"
            )
            sys.stdout.write(
                f"\r\033[2K{prompt}  {reject}  {accept}"
                "  \033[2m←→ Select Enter Confirm Esc Discard\033[0m"
            )
            sys.stdout.flush()
            key = self.key_reader()
            if key in {"left", "right", "up", "down"}:
                accepted = not accepted
            elif key == "y":
                accepted = True
            elif key in {"n", "escape", "backspace"}:
                sys.stdout.write("\n")
                sys.stdout.flush()
                return False
            elif key == "enter":
                sys.stdout.write("\n")
                sys.stdout.flush()
                return accepted

    def _render(
        self,
        title: str,
        items: Sequence[MenuItem],
        selected: int,
        breadcrumb: str,
        back_label: str,
    ) -> None:
        self.clear()
        width = min(max((len(item.label) for item in items), default=20) + 18, 64)
        sys.stdout.write(f"\033[2m{breadcrumb}\033[0m\n")
        sys.stdout.write(f"\033[1m{title}\033[0m\n")
        sys.stdout.write("─" * width + "\n\n")
        for index, item in enumerate(items):
            marker = "❯" if index == selected else " "
            number = item.key if item.key.isdigit() else str(index + 1)
            hint = f"  \033[2m{item.hint}\033[0m" if item.hint else ""
            if index == selected:
                sys.stdout.write(
                    f"\033[36;1m{marker} {number}. {item.label}\033[0m{hint}\n"
                )
            else:
                sys.stdout.write(f"{marker} {number}. {item.label}{hint}\n")
        sys.stdout.write(
            f"\n\033[2m↑↓ Navigate   Enter/→ Select   ←/Esc {back_label}   Number Quick Select\033[0m\n"
        )
        sys.stdout.flush()

    def _choose_line(
        self,
        title: str,
        items: Sequence[MenuItem],
        breadcrumb: str,
        back_label: str,
    ) -> str | None:
        self.output(f"\n{breadcrumb} / {title}")
        for item in items:
            self.output(f"{item.key}. {item.label}")
        self.output(f"0. {back_label}")
        try:
            raw = self.input("Select: ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if raw == "0":
            return None
        return raw


def _read_key() -> str:
    if os.name == "nt":
        import msvcrt  # noqa: PLC0415

        msvcrt_module = cast(Any, msvcrt)
        read_wide_char = cast(Callable[[], str], msvcrt_module.getwch)
        char = read_wide_char()
        if char in {"\x00", "\xe0"}:
            return {
                "H": "up",
                "P": "down",
                "K": "left",
                "M": "right",
            }.get(read_wide_char(), "unknown")
        return _normalize_char(char)

    import termios  # noqa: PLC0415
    import tty  # noqa: PLC0415

    fd = sys.stdin.fileno()
    previous = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        char = _read_utf8_char(fd)
        if char == "\x1b":
            sequence = char
            if _stdin_has_data(fd, 0.08):
                sequence += os.read(fd, 1).decode(errors="ignore")
            if sequence == "\x1b[" and _stdin_has_data(fd, 0.08):
                sequence += os.read(fd, 1).decode(errors="ignore")
            return {
                "\x1b[A": "up",
                "\x1b[B": "down",
                "\x1b[C": "right",
                "\x1b[D": "left",
            }.get(sequence, "escape")
        return _normalize_char(char)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, previous)


def _stdin_has_data(fd: int, timeout: float = 0.01) -> bool:
    import select  # noqa: PLC0415

    readable, _, _ = select.select([fd], [], [], timeout)
    return bool(readable)


def _normalize_char(char: str) -> str:
    if char in {"\r", "\n"}:
        return "enter"
    if char in {"\x7f", "\b"}:
        return "backspace"
    if char == "\x1b":
        return "escape"
    if char == "\x16":
        return "paste"
    if char == "\x03":
        return "interrupt"
    return char


def _read_utf8_char(fd: int) -> str:
    """Read a complete UTF-8 character from raw TTY, avoiding Chinese paste character loss."""
    first = os.read(fd, 1)
    if not first:
        return ""
    lead = first[0]
    remaining = 0
    if lead & 0b1111_1000 == 0b1111_0000:
        remaining = 3
    elif lead & 0b1111_0000 == 0b1110_0000:
        remaining = 2
    elif lead & 0b1110_0000 == 0b1100_0000:
        remaining = 1
    data = first
    for _ in range(remaining):
        data += os.read(fd, 1)
    return data.decode("utf-8", errors="ignore")


def _read_clipboard() -> str:
    """Read from local clipboard when user presses Ctrl+V."""
    if sys.platform == "darwin":
        command = ["pbpaste"]
    elif os.name == "nt":
        command = ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"]
    elif shutil.which("wl-paste"):
        command = ["wl-paste", "--no-newline"]
    elif shutil.which("xclip"):
        command = ["xclip", "-selection", "clipboard", "-o"]
    else:
        raise RuntimeError("No available clipboard command on current system")
    completed = subprocess.run(  # noqa: S603
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=2,
    )
    if completed.returncode != 0:
        raise RuntimeError("Clipboard read failed")
    return completed.stdout
