from __future__ import annotations

from typing import Optional

from ai_runtime.storage.data_home import get_db_path
from app.infrastructure.persistence.elfie_repository import ElfieRepository


def dispatch_route(subcmd: Optional[str], elfie_id: Optional[str]) -> None:
    if subcmd == "show" and elfie_id:
        show_route(elfie_id)


def show_route(elfie_id: str) -> None:
    print(f"\n  🍚  {elfie_id} Main Food\n")
    elfie = ElfieRepository(str(get_db_path())).get(elfie_id)
    if elfie is None:
        print("  Elfie not found.\n")
        return
    print(f"  Main food: {elfie.main_food_id or 'food_common'}")
    print(
        "\n  Models are managed by Runtime food packages; Elfies do not choose models directly.\n"
    )
