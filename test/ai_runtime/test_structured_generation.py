"""Structured generation boundary tests for the RuntimeAgent gateway."""

from __future__ import annotations

from pydantic import JsonValue

from ai_runtime.food.models import ExecutionProfile, FoodRecipe
from ai_runtime.food.store import FoodCatalog
from ai_runtime.gateway.agent import RuntimeAgent
from ai_runtime.gateway.request import (
    StructuredGenerationMode,
    StructuredRuntimeRequest,
)


def test_generate_structured_uses_one_selected_mode(monkeypatch, tmp_path):
    """Given a schema request, When generated, Then one food call gets schema options."""
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = RuntimeAgent()
    agent.food_catalog_store.save(
        FoodCatalog(
            recipes={
                "standard": FoodRecipe(
                    "standard",
                    "standard",
                    "test",
                    ExecutionProfile("openai/gpt-test"),
                )
            }
        )
    )
    agent.config.providers["openai"] = {"api_key": "test-placeholder"}
    calls: list[tuple[str, str, dict[str, JsonValue]]] = []

    def fake_call(provider, model, messages, temperature, max_tokens, options):
        calls.append((provider, model, options))
        return '{"ok": true}'

    agent._call_food_llm_api = fake_call

    result = agent.generate_structured(
        StructuredRuntimeRequest(
            prompt="Return JSON.",
            messages=({"role": "user", "content": "Return JSON."},),
            response_schema_name="DecisionPlan",
            response_schema={"type": "object"},
            selected_mode=StructuredGenerationMode.JSON_SCHEMA,
            allowed_tools=(),
        )
    )

    assert result.text == '{"ok": true}'
    assert result.selected_mode is StructuredGenerationMode.JSON_SCHEMA
    assert result.provider == "openai"
    assert result.model_key == "openai/gpt-test"
    assert calls == [
        (
            "openai",
            "gpt-test",
            {
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "DecisionPlan",
                        "schema": {"type": "object"},
                        "strict": True,
                    },
                }
            },
        )
    ]


def test_generate_structured_plain_json_does_not_claim_native(monkeypatch, tmp_path):
    """Given a plain provider request, When generated, Then JSON is requested as text."""
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = RuntimeAgent()
    agent.food_catalog_store.save(
        FoodCatalog(
            recipes={
                "standard": FoodRecipe(
                    "standard",
                    "standard",
                    "test",
                    ExecutionProfile("ollama/qwen3.5:0.8b"),
                )
            }
        )
    )
    calls: list[tuple[str, str, dict[str, JsonValue]]] = []
    agent._call_food_llm_api = lambda provider, model, messages, _t, _m, options: (
        calls.append((provider, model, options)) or "plain text"
    )

    result = agent.generate_structured(
        StructuredRuntimeRequest(
            prompt="Return JSON text.",
            messages=(),
            response_schema_name="DecisionPlan",
            response_schema={"type": "object"},
            selected_mode=StructuredGenerationMode.JSON_TEXT,
            allowed_tools=(),
        )
    )

    assert result.text == "plain text"
    assert result.selected_mode is StructuredGenerationMode.JSON_TEXT
    assert calls == [("ollama", "qwen3.5:0.8b", {})]
