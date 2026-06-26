from __future__ import annotations

import getpass
import os
from typing import Optional

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
except ImportError:
    Console = None
    Panel = None
    Text = None


def print_banner() -> None:
    cyan = "\033[1;36m"
    yellow = "\033[1;33m"
    reset = "\033[0m"
    banner = (
        f"{cyan}███████╗██╗     ███████╗██╗███████╗     {yellow}███╗   ██╗███████╗███████╗████████╗{reset}\n"
        f"{cyan}██╔════╝██║     ██╔════╝██║██╔════╝     {yellow}████╗  ██║██╔════╝██╔════╝╚══██╔══╝{reset}\n"
        f"{cyan}█████╗  ██║     █████╗  ██║█████╗       {yellow}██╔██╗ ██║█████╗  ███████╗   ██║   {reset}\n"
        f"{cyan}██╔══╝  ██║     ██╔══╝  ██║██╔══╝       {yellow}██║╚██╗██║██╔══╝  ╚════██║   ██║   {reset}\n"
        f"{cyan}███████╗███████╗██║     ██║███████╗     {yellow}██║ ╚████║███████╗███████║   ██║   {reset}\n"
        f"{cyan}╚══════╝╚══════╝╚═╝     ╚═╝╚══════╝     {yellow}╚═╝  ╚═══╝╚══════╝╚══════╝   ╚═╝   {reset}\n"
        "\n            🦊 仿生生命体系统 - Embodied AI Creature Simulation\n"
    )
    print(banner)


def clear_screen() -> None:
    os.system("clear" if os.name == "posix" else "cls")


def rich_console() -> Optional[Console]:
    if Console is None:
        return None
    return Console()


def print_tui_panel(title: str, subtitle: Optional[str] = None) -> None:
    console = rich_console()
    if console is None or Panel is None or Text is None:
        print(f"  {title}")
        print("  " + "=" * 45)
        if subtitle:
            print(f"  {subtitle}")
        print()
        return

    content = Text(title, style="bold cyan")
    if subtitle:
        content.append("\n")
        content.append(subtitle, style="dim")
    console.print(
        Panel(
            content,
            border_style="cyan",
            padding=(1, 2),
            width=72,
        )
    )


def print_success_panel(lines: list[str]) -> None:
    console = rich_console()
    if console is None or Panel is None or Text is None:
        print("  " + "=" * 45)
        for line in lines:
            print(f"  {line}")
        print()
        return

    content = Text()
    for index, line in enumerate(lines):
        if index > 0:
            content.append("\n")
        content.append(line, style="green" if index == 0 else "white")
    console.print(
        Panel(
            content,
            title="Done",
            border_style="green",
            padding=(1, 2),
            width=72,
        )
    )


def input_text(prompt: str, default: Optional[str] = None) -> Optional[str]:
    hint = f" [{default}]" if default else ""
    try:
        value = input(f"{prompt}{hint}: ").strip()
        return value if value else default
    except KeyboardInterrupt:
        return default


def input_password(prompt: str) -> Optional[str]:
    try:
        return getpass.getpass(prompt + ": ")
    except KeyboardInterrupt:
        return None
