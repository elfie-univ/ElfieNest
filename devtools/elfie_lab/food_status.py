"""Elfie Lab 粮食目录的可用性展示投影。"""

from __future__ import annotations

from typing import List, Optional, TypedDict

from ai_runtime.food.models import FoodPackage, system_food_packages
from ai_runtime.food.store import FoodCatalogRepository
from devtools.elfie_lab.runtime_foods import (
    list_installed_ollama_models,
    load_runtime_food_catalog,
    model_availability,
)
from devtools.runtime_lab import RuntimeLabConfigStore


class FoodStatusItem(TypedDict):
    """Stable food readiness row returned by the Lab API."""

    key: str
    display_name: str
    description: str
    model: str
    reasoning: str
    primary_ready: bool
    fallback_ready: bool
    fallback_model: Optional[str]
    ready_for_attempt: bool
    credential_ready: bool
    unavailable_reason: str
    setup_commands: List[str]


def build_food_items(
    runtime_store: RuntimeLabConfigStore,
    food_store: FoodCatalogRepository,
    configure_runtime_command: str,
) -> List[FoodStatusItem]:
    """Build runtime food readiness rows for the Lab API."""
    config = runtime_store.load_runtime_config()
    catalog = load_runtime_food_catalog(runtime_store, food_store)
    installed_models = list_installed_ollama_models(config)
    foods: List[FoodStatusItem] = []
    for key, package in catalog.packages.items():
        primary_model = package.primary.model if package.primary else ""
        primary = model_availability(
            primary_model,
            config,
            installed_models,
            configure_runtime_command,
        )
        fallback_state = (
            model_availability(
                package.fallback.model,
                config,
                installed_models,
                configure_runtime_command,
            )
            if package.fallback is not None and package.fallback.model
            else None
        )
        fallback_model = (
            package.fallback.model
            if package.fallback and package.fallback.model
            else None
        )
        fallback_ready = bool(fallback_state and fallback_state["ready"])
        ready_for_attempt = bool(primary["ready"] or fallback_ready)
        setup_commands = []
        for item in [primary, fallback_state] if fallback_state else [primary]:
            command = str(item.get("command", ""))
            if command and command not in setup_commands:
                setup_commands.append(command)
        foods.append(
            {
                "key": key,
                "display_name": package.display_name,
                "description": "",
                "model": primary_model,
                "reasoning": "on" if package.reasoning else "off",
                "primary_ready": primary["ready"],
                "fallback_ready": fallback_ready,
                "fallback_model": fallback_model,
                "ready_for_attempt": ready_for_attempt,
                "credential_ready": ready_for_attempt,
                "unavailable_reason": (
                    ""
                    if ready_for_attempt
                    else str(primary.get("reason", "粮食尚未就绪"))
                ),
                "setup_commands": setup_commands,
            }
        )
    if not foods:
        foods = [
            unconfigured_food_item(package)
            for package in system_food_packages().values()
        ]
    return foods


def unconfigured_food_item(package: FoodPackage) -> FoodStatusItem:
    """Expose an unavailable system food before the Lab catalog is configured."""
    return {
        "key": package.key,
        "display_name": package.display_name,
        "description": "",
        "model": "",
        "reasoning": "",
        "primary_ready": False,
        "fallback_ready": False,
        "fallback_model": None,
        "ready_for_attempt": False,
        "credential_ready": False,
        "unavailable_reason": "粮食目录尚未初始化",
        "setup_commands": [],
    }


def find_food_item(
    food_key: str,
    runtime_store: RuntimeLabConfigStore,
    food_store: FoodCatalogRepository,
    configure_runtime_command: str,
) -> FoodStatusItem | None:
    """Resolve one normalized food key from the same rows exposed by the API."""
    return {
        item["key"]: item
        for item in build_food_items(
            runtime_store,
            food_store,
            configure_runtime_command,
        )
    }.get(food_key)
