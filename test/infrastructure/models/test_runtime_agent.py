import pytest

from elfie.brain.reasoning.food_port import (
    FoodAssignment,
    FoodCatalog,
    FoodPackage,
    NoAvailableFoodError,
)
from infrastructure.models.runtime_agent import RuntimeAgent
from infrastructure.models.runtime_config import LLMRuntimeConfig
from infrastructure.models.runtime_contracts import (
    StructuredGenerationMode,
    StructuredRuntimeRequest,
)


def test_runtime_never_selects_arbitrary_custom_food(monkeypatch):
    monkeypatch.setattr(
        RuntimeAgent, "_package_usable", staticmethod(lambda package: False)
    )
    with pytest.raises(NoAvailableFoodError) as error:
        RuntimeAgent._select_food_key(FoodCatalog(), "food_missing")
    assert error.value.code == "no_available_food"


def test_ollama_json_text_requests_explicit_json_format() -> None:
    request = StructuredRuntimeRequest(
        prompt="{}",
        messages=(),
        response_schema_name="DecisionPlan",
        response_schema={"type": "object"},
        selected_mode=StructuredGenerationMode.JSON_TEXT,
        allowed_tools=(),
        provider="ollama",
        model_key="ollama/qwen2.5:0.5b",
    )

    assert RuntimeAgent._structured_request_options(
        request, StructuredGenerationMode.JSON_TEXT
    ) == {"format": "json"}

    request = request.model_copy(update={"provider": "ollama_0001"})
    assert RuntimeAgent._structured_request_options(
        request, StructuredGenerationMode.JSON_TEXT
    ) == {"format": "json"}


def test_ollama_connection_advertises_json_mode_for_decision_decoding(
    monkeypatch,
) -> None:
    agent = object.__new__(RuntimeAgent)
    agent.config = LLMRuntimeConfig(providers={"ollama_0001": {"api_mode": "ollama"}})
    agent._load_food_catalog = lambda: FoodCatalog(
        global_default_food_id="qa_food",
        packages={
            "qa_food": FoodPackage(
                key="qa_food",
                display_name="QA",
                primary=FoodAssignment("ollama_0001/qwen2.5:0.5b"),
            )
        },
    )
    monkeypatch.setattr(agent, "_package_usable", lambda package: True)

    capabilities = agent.structured_capabilities()

    assert capabilities.supports_json_mode is True
    assert capabilities.supports_json_schema is False
    assert capabilities.supports_tool_calling is False


def test_openai_compatible_connection_advertises_prompt_constrained_json_mode(
    monkeypatch,
) -> None:
    agent = object.__new__(RuntimeAgent)
    agent.config = LLMRuntimeConfig(
        providers={"custom_0001": {"api_mode": "chat_completions"}}
    )
    agent._load_food_catalog = lambda: FoodCatalog(
        global_default_food_id="qa_food",
        packages={
            "qa_food": FoodPackage(
                key="qa_food",
                display_name="QA",
                primary=FoodAssignment("custom_0001/model"),
            )
        },
    )
    monkeypatch.setattr(agent, "_package_usable", lambda package: True)

    capabilities = agent.structured_capabilities()

    assert capabilities.supports_json_schema is False
    assert capabilities.supports_json_mode is True


def test_json_text_injects_schema_without_mutating_original_messages() -> None:
    request = StructuredRuntimeRequest(
        prompt="{}",
        messages=(),
        response_schema_name="DecisionPlan",
        response_schema={"type": "object", "required": ["intents"]},
        selected_mode=StructuredGenerationMode.JSON_TEXT,
        allowed_tools=(),
        provider="custom_0001",
        model_key="custom_0001/model",
    )
    original = [{"role": "system", "content": "You are Elfie."}]

    constrained = RuntimeAgent._structured_messages(
        request,
        StructuredGenerationMode.JSON_TEXT,
        original,
    )

    assert original == [{"role": "system", "content": "You are Elfie."}]
    assert "Return only one JSON value" in constrained[0]["content"]
    assert '"required":["intents"]' in constrained[0]["content"]
