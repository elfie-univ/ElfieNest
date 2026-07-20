"""用已验证模型为粮食规划提供脱敏建议。"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any

from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.food.models import FIXED_FOOD_KINDS
from ai_runtime.food.planner import ModelEvidence
from ai_runtime.gateway.llm_api import call_llm_api


class LLMFoodPlanningAdvisor:
    def __init__(
        self,
        config: LLMRuntimeConfig,
        planning_model: str,
        *,
        model_caller: Callable[..., str] = call_llm_api,
    ) -> None:
        self.config = config
        self.planning_model = planning_model
        self.model_caller = model_caller

    def recommend(
        self,
        food_keys: Sequence[str],
        evidence: Sequence[ModelEvidence],
    ) -> dict[str, str]:
        provider, model = self.planning_model.split("/", 1)
        facts = [item.to_fingerprint_dict() for item in evidence]
        foods = {
            key: {
                "name": FIXED_FOOD_KINDS[key].display_name,
                "description": FIXED_FOOD_KINDS[key].description,
                "required_capabilities": list(
                    FIXED_FOOD_KINDS[key].required_capabilities
                ),
            }
            for key in food_keys
            if key in FIXED_FOOD_KINDS
        }
        prompt = (
            "你是 ElfieNest Runtime 的粮食配方规划器。"
            "只能从 models 中选择 verified=true 且能力满足要求的模型。"
            "不要创造模型，不要输出解释，只输出 JSON 对象，格式为"
            '{"food_key":"provider/model"}。\n'
            f"foods={json.dumps(foods, ensure_ascii=False)}\n"
            f"models={json.dumps(facts, ensure_ascii=False)}"
        )
        response = self.model_caller(
            self.config,
            provider,
            model,
            [{"role": "user", "content": prompt}],
            0.2,
            1200,
        )
        payload = _parse_json_object(response)
        return {
            str(food_key): str(model_id)
            for food_key, model_id in payload.items()
            if isinstance(food_key, str) and isinstance(model_id, str)
        }


def select_planning_model(
    config: LLMRuntimeConfig,
    evidence: Sequence[ModelEvidence],
) -> str | None:
    candidates = []
    for item in evidence:
        if not item.verified or "text" not in item.capabilities:
            continue
        provider = item.model.split("/", 1)[0]
        provider_config = config.providers.get(provider, {})
        if provider == "ollama" or provider_config.get("api_key"):
            candidates.append(item)
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: (
            "reasoning" in item.capabilities,
            item.cost_grade,
            -(item.latency_ms or 1_000_000),
        ),
    ).model


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(
            line for line in lines if not line.strip().startswith("```")
        ).strip()
        if text.startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("粮食规划模型没有返回 JSON 对象")
    payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("粮食规划结果必须是 JSON 对象")
    return payload
