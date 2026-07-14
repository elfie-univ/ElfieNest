"""首次运行时的兼容粮食目录。

业务调用者始终请求粮食。旧版模型字段只在尚未生成正式 ``foods.yaml`` 时，
由 Runtime 内部转换成临时配方；一旦存在正式粮食目录，这些字段不再参与路由。
"""

from __future__ import annotations

from runtime.config import LLMRuntimeConfig
from runtime.food.models import (
    FIXED_FOOD_KINDS,
    ExecutionProfile,
    FoodRecipe,
    ReasoningProfile,
)
from runtime.food.store import FoodCatalog


def build_compatibility_food_catalog(config: LLMRuntimeConfig) -> FoodCatalog:
    local = _model_ref("ollama", config.ollama_model_fast)
    cheap = _model_ref(config.cheap_provider, config.cheap_model)
    deep = _model_ref(config.deep_provider, config.deep_model)
    vision = _model_ref(config.multimodal_provider, config.multimodal_model)

    recipes = {
        "coarse": _recipe("coarse", local, ReasoningProfile.LOW),
        "standard": _recipe("standard", cheap, ReasoningProfile.BALANCED, local),
        "focus": _recipe("focus", deep, ReasoningProfile.DEEP, local),
        "creative": _recipe("creative", cheap, ReasoningProfile.BALANCED, local),
        "tool": _recipe(
            "tool",
            deep,
            ReasoningProfile.BALANCED,
            local,
            tools=("web_search", "local_file", "code_sandbox"),
        ),
        "vision": _recipe("vision", vision, ReasoningProfile.BALANCED, local),
        "premium": _recipe("premium", deep, ReasoningProfile.MAX, local),
        "emergency": _recipe("emergency", local, ReasoningProfile.LOW),
    }
    return FoodCatalog(
        version=0,
        generation_sources=("legacy_compatibility",),
        generation_note="尚无正式粮食目录，由 Runtime 内部兼容旧模型配置",
        recipes=recipes,
    )


def _recipe(
    food_key: str,
    model: str,
    reasoning: ReasoningProfile,
    fallback: str | None = None,
    *,
    tools: tuple[str, ...] = (),
) -> FoodRecipe:
    kind = FIXED_FOOD_KINDS[food_key]
    fallbacks = (
        (ExecutionProfile(fallback, ReasoningProfile.LOW),)
        if fallback and fallback != model
        else ()
    )
    return FoodRecipe(
        key=food_key,
        display_name=kind.display_name,
        description=kind.description,
        primary=ExecutionProfile(
            model=model,
            reasoning_profile=reasoning,
            tools=tools,
        ),
        technical_fallbacks=fallbacks,
        source="legacy_compatibility",
    )


def _model_ref(provider: str, model: str) -> str:
    normalized_provider = provider or "ollama"
    if "/" in model and model.split("/", 1)[0] == normalized_provider:
        return model
    return f"{normalized_provider}/{model}"
