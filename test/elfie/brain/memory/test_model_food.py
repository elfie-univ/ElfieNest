from datetime import datetime, timezone

from elfie.brain.memory.model_food import ModelPortMemoryAdapter, ask_memory_model
from elfie.brain.reasoning.model_port import (
    ModelGenerationCapabilities,
    ModelGenerationResult,
    StructuredOutputMode,
)


class FoodRuntime:
    def __init__(self):
        self.kwargs = None

    def ask_with_food(self, **kwargs):
        self.kwargs = kwargs
        return "memory-result"


def test_memory_work_uses_food_interface_without_model_details():
    runtime = FoodRuntime()

    result = ask_memory_model(
        runtime,
        "整理记忆",
        elfie_id="elfie-1",
        semantic_role="reasoning",
        complexity=2,
    )

    assert result == "memory-result"
    assert runtime.kwargs["food_key"] is None
    assert runtime.kwargs["semantic_role"] == "reasoning"
    assert runtime.kwargs["scene"] == "memory"
    assert "elfie_config_dir" not in runtime.kwargs
    assert "model" not in runtime.kwargs


class PrimaryModel:
    def __init__(self):
        self.requests = []

    def capabilities(self):
        return ModelGenerationCapabilities(
            provider="fake",
            model_key="primary",
            supports_json_schema=True,
            supports_tool_calling=False,
            supports_json_mode=True,
            supports_plain_text=True,
            max_output_tokens=2048,
        )

    def generate(self, request):
        self.requests.append(request)
        return ModelGenerationResult(
            text='{"nodes":[],"mentions":[],"assertions":[]}',
            selected_mode=StructuredOutputMode.JSON_SCHEMA,
            provider="fake",
            model_key="primary",
        )


def test_brain_model_adapter_keeps_memory_on_primary_model_boundary():
    primary = PrimaryModel()
    adapter = ModelPortMemoryAdapter(
        primary,
        elfie_id="elfie-1",
        clock=lambda: datetime(2026, 8, 29, tzinfo=timezone.utc),
    )

    result = adapter.ask_with_food(
        "整理这条 Episode",
        food_key=None,
        elfie_id="elfie-1",
        scene="memory",
        semantic_role="memory_consolidation",
        energy=50.0,
        task_complexity=2,
        allowed_tools=[],
    )

    assert result.startswith("{")
    request = primary.requests[0]
    assert request.source_domain.value == "internal"
    assert request.response_schema.name == "MemoryProjection"
    assert request.allowed_tools == ()
