from __future__ import annotations

from typing import Optional

from runtime.model_route import SCENE_SLOTS, load_model_route


def dispatch_route(subcmd: Optional[str], elfie_id: Optional[str]) -> None:
    if subcmd == "show" and elfie_id:
        show_route(elfie_id)


def show_route(elfie_id: str) -> None:
    print(f"\n  🗺️  {elfie_id} 场景路由\n")

    route = load_model_route(elfie_id)

    print(f"  {'场景':<10s} {'主模型':<30s} {'Fallback链':<30s} {'能量阈值':<8s}")
    print("  " + "-" * 85)

    for scene in SCENE_SLOTS:
        scene_route = route.scene_routes.get(scene)
        if not scene_route:
            continue

        if scene_route.fallbacks:
            fallback_str = " → ".join(scene_route.fallbacks)
        else:
            fallback_str = "(无)"
        threshold = f"{scene_route.energy_threshold}%"
        print(
            f"  {scene:<10s} {scene_route.primary:<30s} {fallback_str:<30s} {threshold:<8s}"
        )

    print()
