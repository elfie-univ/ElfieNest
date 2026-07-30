from __future__ import annotations

from typing import Optional


def dispatch_route(subcmd: Optional[str], elfie_id: Optional[str]) -> None:
    if subcmd == "show" and elfie_id:
        show_route(elfie_id)


def show_route(elfie_id: str) -> None:
    print(f"\n  {elfie_id} uses the Nest DB Main-food assignment.")
    print("  Inspect or change it from the Elfie page.\n")
