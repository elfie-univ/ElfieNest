"""Elfie Lab 测试粮食的最小展示投影。"""

from __future__ import annotations

from typing import List, TypedDict

from devtools.elfie_lab.runtime_foods import (
    ElfieLabRuntime,
    load_runtime_food_catalog,
)
from elfie.brain.reasoning.food_port import FoodPackage, FoodPort, system_food_packages


class FoodStatusItem(TypedDict):
    """Stable Food row returned by the Lab API."""

    key: str
    display_name: str
    description: str
    model: str
    reasoning: str
    ready_for_attempt: bool
    unavailable_reason: str


def build_food_items(
    runtime: ElfieLabRuntime,
    food_store: FoodPort,
) -> List[FoodStatusItem]:
    """Build rows without performing model or connection validation."""
    catalog = load_runtime_food_catalog(runtime, food_store)
    foods: List[FoodStatusItem] = []
    for key, package in catalog.packages.items():
        primary_model = package.primary.model if package.primary else ""
        configured = bool(
            package.enabled
            and not package.archived
            and package.primary is not None
            and primary_model
        )
        foods.append(
            {
                "key": key,
                "display_name": package.display_name,
                "description": (
                    "已配置，首次真实对话时尝试连接"
                    if configured
                    else "请先配置测试粮食"
                ),
                "model": primary_model,
                "reasoning": "on" if package.reasoning else "off",
                "ready_for_attempt": configured,
                "unavailable_reason": "" if configured else "尚未配置测试粮食",
            }
        )
    if not foods:
        foods = [
            unconfigured_food_item(package)
            for package in system_food_packages().values()
        ]
    return foods


def unconfigured_food_item(package: FoodPackage) -> FoodStatusItem:
    """Expose an unavailable system Food before Lab configuration."""
    return {
        "key": package.key,
        "display_name": package.display_name,
        "description": "请先配置测试粮食",
        "model": "",
        "reasoning": "",
        "ready_for_attempt": False,
        "unavailable_reason": "尚未配置测试粮食",
    }


def find_food_item(
    food_key: str,
    runtime: ElfieLabRuntime,
    food_store: FoodPort,
) -> FoodStatusItem | None:
    """Resolve one normalized Food key from the Lab projection."""
    return {item["key"]: item for item in build_food_items(runtime, food_store)}.get(
        food_key
    )
