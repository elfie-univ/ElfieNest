"""Elfie Lab 粮食目录的可用性展示投影。"""

from __future__ import annotations

from typing import List, TypedDict

from ai_runtime.food.models import FIXED_FOOD_KINDS, FoodKind
from ai_runtime.food.store import FoodCatalogStore
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
    fallback_models: List[str]
    ready_for_attempt: bool
    credential_ready: bool
    unavailable_reason: str
    setup_commands: List[str]


def build_food_items(
    runtime_store: RuntimeLabConfigStore,
    food_store: FoodCatalogStore,
    configure_runtime_command: str,
) -> List[FoodStatusItem]:
    """Build runtime food readiness rows for the Lab API."""
    config = runtime_store.load_runtime_config()
    catalog = load_runtime_food_catalog(runtime_store, food_store)
    installed_models = list_installed_ollama_models(config)
    foods: List[FoodStatusItem] = []
    for key, recipe in catalog.recipes.items():
        primary = model_availability(
            recipe.primary.model,
            config,
            installed_models,
            configure_runtime_command,
        )
        fallback_states = [
            model_availability(
                profile.model,
                config,
                installed_models,
                configure_runtime_command,
            )
            for profile in recipe.technical_fallbacks
            if profile.model
        ]
        fallback_models = [
            profile.model for profile in recipe.technical_fallbacks if profile.model
        ]
        fallback_ready = any(item["ready"] for item in fallback_states)
        ready_for_attempt = bool(primary["ready"] or fallback_ready)
        setup_commands = []
        for item in [primary, *fallback_states]:
            command = str(item.get("command", ""))
            if command and command not in setup_commands:
                setup_commands.append(command)
        foods.append(
            {
                "key": key,
                "display_name": recipe.display_name,
                "description": recipe.description,
                "model": recipe.primary.model,
                "reasoning": recipe.primary.reasoning_profile.value,
                "primary_ready": primary["ready"],
                "fallback_ready": fallback_ready,
                "fallback_models": fallback_models,
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
        foods = [unconfigured_food_item(kind) for kind in FIXED_FOOD_KINDS.values()]
    return [mock_food_item(), *foods]


def mock_food_item() -> FoodStatusItem:
    """Return the offline food row without reading runtime configuration."""
    return {
        "key": "mock",
        "display_name": "模拟粮",
        "description": "离线可用，不调用任何外部服务",
        "model": "elfie-mock",
        "reasoning": "off",
        "primary_ready": True,
        "fallback_ready": False,
        "fallback_models": [],
        "ready_for_attempt": True,
        "credential_ready": True,
        "unavailable_reason": "",
        "setup_commands": [],
    }


def unconfigured_food_item(kind: FoodKind) -> FoodStatusItem:
    """Expose an unavailable fixed food when the Lab catalog has not been initialized."""
    return {
        "key": kind.key,
        "display_name": kind.display_name,
        "description": kind.description,
        "model": "",
        "reasoning": "",
        "primary_ready": False,
        "fallback_ready": False,
        "fallback_models": [],
        "ready_for_attempt": False,
        "credential_ready": False,
        "unavailable_reason": "粮食目录尚未初始化",
        "setup_commands": [],
    }


def find_food_item(
    food_key: str,
    runtime_store: RuntimeLabConfigStore,
    food_store: FoodCatalogStore,
    configure_runtime_command: str,
) -> FoodStatusItem | None:
    """Resolve one normalized food key from the same rows exposed by the API."""
    if food_key == "mock":
        return mock_food_item()
    return {
        item["key"]: item
        for item in build_food_items(
            runtime_store,
            food_store,
            configure_runtime_command,
        )
    }.get(food_key)
