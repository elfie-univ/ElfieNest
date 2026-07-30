from __future__ import annotations

from typing import Optional

from ai_runtime.storage.data_home import get_db_path
from app.infrastructure.persistence.elfie_repository import ElfieRepository


def dispatch_route(subcmd: Optional[str], elfie_id: Optional[str]) -> None:
    if subcmd == "show" and elfie_id:
        show_route(elfie_id)


def show_route(elfie_id: str) -> None:
    print(f"\n  🍚  {elfie_id} Food Permissions\n")
    elfie = ElfieRepository(str(get_db_path())).get(elfie_id)
    if elfie is None:
        print("  Elfie not found.\n")
        return
    default_food = elfie.main_food or "standard"
    fallback_food = elfie.emergency_food or "coarse"
    allowed_foods = tuple(
        dict.fromkeys((default_food, *elfie.other_foods, fallback_food))
    )
    print(f"  Default food: {default_food}")
    print(f"  Allowed food: {', '.join(allowed_foods)}")
    print(f"  Fallback food: {fallback_food}")
    print(
        "\n  Models are managed by Runtime food policy; Elfies do not choose models directly.\n"
    )
