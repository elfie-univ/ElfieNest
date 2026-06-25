from __future__ import annotations

import getpass
import os
from typing import Optional


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
