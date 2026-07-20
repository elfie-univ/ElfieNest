from __future__ import annotations

from typing import Optional

from ai_runtime.food.elfie_policy import load_elfie_food_policy


def dispatch_route(subcmd: Optional[str], elfie_id: Optional[str]) -> None:
    if subcmd == "show" and elfie_id:
        show_route(elfie_id)


def show_route(elfie_id: str) -> None:
    print(f"\n  🍚  {elfie_id} 粮食权限\n")
    policy = load_elfie_food_policy(elfie_id)
    print(f"  默认粮食: {policy.default_food}")
    print(f"  允许粮食: {', '.join(policy.allowed_foods)}")
    print(f"  降级粮食: {policy.fallback_food}")
    print("\n  模型由 Runtime 粮食策略统一管理，精灵不再直接选择模型。\n")
