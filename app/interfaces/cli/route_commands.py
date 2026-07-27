from __future__ import annotations

from typing import Optional

from ai_runtime.food.elfie_policy import load_elfie_food_policy


def dispatch_route(subcmd: Optional[str], elfie_id: Optional[str]) -> None:
    if subcmd == "show" and elfie_id:
        show_route(elfie_id)


def show_route(elfie_id: str) -> None:
    print(f"\n  🍚  {elfie_id} Food Permissions\n")
    policy = load_elfie_food_policy(elfie_id)
    print(f"  Default food: {policy.default_food}")
    print(f"  Allowed food: {', '.join(policy.allowed_foods)}")
    print(f"  Fallback food: {policy.fallback_food}")
    print("\n  Models are managed by Runtime food policy; Elfies do not select models directly.\n")
