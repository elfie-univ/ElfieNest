"""Elfie Lab 测试粮食的最小展示投影。"""

from __future__ import annotations

from typing import List, Literal, TypedDict

from devtools.elfie_lab.model_execution_foods import (
    ElfieLabModelEnvironment,
    food_connection_type,
    load_model_execution_food_catalog,
)
from elfie.brain.reasoning.food_port import FoodPort
from infrastructure.models.model_reference import parse_model_reference
from infrastructure.models.ollama.ollama_platform import DEFAULT_OLLAMA_ENDPOINT
from infrastructure.persistence.provider_connections import ProviderConnectionStore


class FoodStatusItem(TypedDict):
    """Stable Food row returned by the Lab API."""

    key: str
    subscription_id: str
    subscription_name: str
    display_name: str
    description: str
    model: str
    reasoning: str
    ready_for_attempt: bool
    unavailable_reason: str
    connection_type: Literal["ollama", "openai"]
    api_base: str
    models: list[str]
    primary_model: str
    reasoning_model: str
    vision_model: str
    tool_model: str
    fallback_model: str


def build_food_items(
    model_environment: ElfieLabModelEnvironment,
    food_store: FoodPort,
) -> List[FoodStatusItem]:
    """Build rows without performing model or connection validation."""
    connections = (
        ProviderConnectionStore(model_environment.providers_path).load().connections
    )
    connection_models = {
        connection_id: tuple(model.endpoint_model_id for model in connection.models)
        for connection_id, connection in connections.items()
    }
    connection_types = {
        connection_id: food_connection_type(
            catalog_id=connection.catalog_id,
            api_mode=connection.api_mode,
        )
        for connection_id, connection in connections.items()
    }
    api_bases = {
        connection_id: (
            connection.api_base
            or (
                DEFAULT_OLLAMA_ENDPOINT
                if connection_types[connection_id] == "ollama"
                else ""
            )
        )
        for connection_id, connection in connections.items()
    }
    catalog = load_model_execution_food_catalog(model_environment, food_store)
    foods: List[FoodStatusItem] = []

    def normalize_models(reference: str | None) -> tuple[str, ...]:
        if not reference:
            return ()
        try:
            reference_connection_id = parse_model_reference(reference).connection_id
            return connection_models.get(reference_connection_id, ())
        except ValueError:
            return ()

    def reference_connection_id(reference: str | None) -> str:
        if not reference:
            return ""
        try:
            return parse_model_reference(reference).connection_id
        except ValueError:
            return ""

    def connection_name(reference: str | None) -> str:
        identifier = reference_connection_id(reference)
        connection = connections.get(identifier)
        return connection.alias if connection is not None else ""

    def infer_connection_api_base(reference: str | None) -> str:
        if not reference:
            return ""
        try:
            return api_bases.get(parse_model_reference(reference).connection_id, "")
        except ValueError:
            return ""

    def infer_connection_type(reference: str | None) -> Literal["ollama", "openai"]:
        if not reference:
            return "openai"
        try:
            return connection_types.get(
                parse_model_reference(reference).connection_id,
                "openai",
            )
        except ValueError:
            return "openai"

    def endpoint_model_id(reference: str | None) -> str:
        if not reference:
            return ""
        try:
            return parse_model_reference(reference).model_id
        except ValueError:
            return ""

    for key, package in catalog.packages.items():
        if package.system_role is not None:
            continue
        primary_reference = package.primary.model if package.primary else ""
        reasoning_reference = package.reasoning.model if package.reasoning else ""
        vision_reference = package.vision.model if package.vision else ""
        tool_reference = package.tool.model if package.tool else ""
        fallback_reference = package.fallback.model if package.fallback else ""
        models = normalize_models(primary_reference)
        configured = bool(
            package.enabled
            and not package.archived
            and package.primary is not None
            and primary_reference
        )
        foods.append(
            {
                "key": key,
                "subscription_id": reference_connection_id(primary_reference),
                "subscription_name": connection_name(primary_reference),
                "display_name": package.display_name,
                "description": (
                    "已配置，可用于真实对话" if configured else "请先配置测试粮食"
                ),
                "model": primary_reference,
                "reasoning": "on" if package.reasoning else "off",
                "ready_for_attempt": configured,
                "unavailable_reason": "" if configured else "尚未配置测试粮食",
                "connection_type": infer_connection_type(primary_reference),
                "api_base": infer_connection_api_base(primary_reference),
                "models": list(models),
                "primary_model": endpoint_model_id(primary_reference),
                "reasoning_model": endpoint_model_id(reasoning_reference),
                "vision_model": endpoint_model_id(vision_reference),
                "tool_model": endpoint_model_id(tool_reference),
                "fallback_model": endpoint_model_id(fallback_reference),
            }
        )
    return foods


def find_food_item(
    food_key: str,
    model_environment: ElfieLabModelEnvironment,
    food_store: FoodPort,
) -> FoodStatusItem | None:
    """Resolve one normalized Food key from the Lab projection."""
    return {
        item["key"]: item for item in build_food_items(model_environment, food_store)
    }.get(food_key)
