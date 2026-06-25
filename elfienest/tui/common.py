from __future__ import annotations

import getpass
import os
from typing import Optional

try:
    import rich.box as rich_box
    from rich.console import Console
    from rich.panel import Panel
except ImportError:
    rich_box = None
    Console = None
    Panel = None


def rich_console() -> Optional[Console]:
    if Console is None:
        return None
    return Console()


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


def print_tui_panel(title: str, subtitle: Optional[str] = None) -> bool:
    console = rich_console()
    if console is None or Panel is None or rich_box is None:
        return False

    body = f"[cyan bold]{title}[/cyan bold]"
    if subtitle:
        body += f"\n[yellow]{subtitle}[/yellow]"
    console.print(Panel.fit(body, box=rich_box.DOUBLE, padding=(1, 4)))
    return True


def print_success_panel(lines: list[str]) -> bool:
    console = rich_console()
    if console is None or Panel is None:
        return False

    content = "\n".join(lines)
    console.print(Panel(content, border_style="green", expand=False))
    return True


def clear_screen() -> None:
    os.system("clear" if os.name == "posix" else "cls")


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
