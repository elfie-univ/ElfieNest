from __future__ import annotations

import pytest

from elfie.brain.food_port import (
    FOOD_EMERGENCY_ID,
    FoodAssignment,
    FoodCatalog,
    FoodPackage,
    MainFoodSelection,
    NoAvailableFoodError,
)
from infrastructure.models.runtime_agent import RuntimeAgent
from infrastructure.models.runtime_config import LLMRuntimeConfig
from infrastructure.models.runtime_contracts import (
    RuntimeRequest,
    StructuredGenerationMode,
    StructuredRuntimeRequest,
)
from infrastructure.persistence.provider_connections import (
    ProviderConnection,
    ProviderConnectionStore,
    ProviderModelRecord,
)
from test.support.runtime_agent import runtime_agent_ports


class _InMemoryFoodPort:
    def __init__(self, catalog: FoodCatalog) -> None:
        self._catalog = catalog

    def load(self) -> FoodCatalog:
        return self._catalog

    def list(self) -> tuple[FoodPackage, ...]:
        return self._catalog.ordered_packages()

    def get(self, food_key: str) -> FoodPackage | None:
        return self._catalog.packages.get(food_key)

    def create(self, package: FoodPackage) -> FoodPackage:
        if package.key in self._catalog.packages:
            raise ValueError(f"duplicate food: {package.key}")
        self._catalog = FoodCatalog(
            packages={**self._catalog.packages, package.key: package}
        )
        return package

    def update(self, package: FoodPackage) -> FoodPackage:
        if package.key not in self._catalog.packages:
            raise ValueError(f"missing food: {package.key}")
        self._catalog = FoodCatalog(
            packages={**self._catalog.packages, package.key: package}
        )
        return package

    def delete(self, food_key: str) -> None:
        if food_key not in self._catalog.packages:
            raise ValueError(f"missing food: {food_key}")
        self._catalog = FoodCatalog(
            packages={
                key: package
                for key, package in self._catalog.packages.items()
                if key != food_key
            }
        )


class _WebSearchToolPort:
    def available_tool_keys(self) -> tuple[str, ...]:
        return ("web_search",)

    def execute(self, request):
        raise AssertionError(f"tool should not execute in this prompt test: {request}")


def _configure_models() -> None:
    ProviderConnectionStore().replace(
        ProviderConnection(
            connection_id="ollama_0001",
            catalog_id="ollama",
            alias="Ollama",
            models=(
                ProviderModelRecord("main"),
                ProviderModelRecord("reason"),
                ProviderModelRecord("emergency"),
            ),
        )
    )


def _catalog() -> FoodCatalog:
    return FoodCatalog(
        packages={
            FOOD_EMERGENCY_ID: FoodPackage(
                FOOD_EMERGENCY_ID,
                "保底粮",
                system_role="emergency",
                primary=FoodAssignment("ollama_0001/emergency"),
            ),
            "food_main": FoodPackage(
                "food_main",
                "主粮",
                primary=FoodAssignment("ollama_0001/main"),
                reasoning=FoodAssignment("ollama_0001/reason"),
            ),
        }
    )


def _agent(
    monkeypatch: pytest.MonkeyPatch, selection: MainFoodSelection
) -> RuntimeAgent:
    _configure_models()
    agent = RuntimeAgent(
        LLMRuntimeConfig(),
        ports=runtime_agent_ports(),
        main_food_loader=lambda _elfie_id: selection,
        food_catalog_repository=_InMemoryFoodPort(_catalog()),
        tool_port=_WebSearchToolPort(),
    )
    monkeypatch.setattr(agent, "_package_usable", lambda package: True)
    return agent


def test_runtime_uses_the_injected_main_food_for_an_elfie(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    # Given: an Elfie whose final-record main food is usable.
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = _agent(monkeypatch, MainFoodSelection("food_main"))
    monkeypatch.setattr(agent, "_call_food_llm_api", lambda *_args: "main response")

    # When: the Runtime receives a request carrying an arbitrary caller food ID.
    result = agent.think(
        RuntimeRequest(
            prompt="hello",
            elfie_id="00000001",
            food_key="food_not_authoritative",
            allowed_tools=(),
        )
    )

    # Then: it executes only the persisted main food.
    assert result.food_used == "food_main"
    assert result.actual_model == "ollama_0001/main"


def test_runtime_uses_emergency_when_the_persisted_main_food_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    # Given: an Elfie with a retained but unavailable selected food.
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = _agent(monkeypatch, MainFoodSelection("food_main", unavailable=True))
    monkeypatch.setattr(
        agent,
        "_package_usable",
        lambda package: package.key == FOOD_EMERGENCY_ID,
    )
    monkeypatch.setattr(
        agent, "_call_food_llm_api", lambda *_args: "emergency response"
    )

    # When: the Runtime executes the request.
    result = agent.think(
        RuntimeRequest(prompt="hello", elfie_id="00000001", allowed_tools=())
    )

    # Then: it starts with the one global emergency package.
    assert result.food_used == FOOD_EMERGENCY_ID
    assert result.actual_model == "ollama_0001/emergency"


def test_structured_runtime_uses_emergency_when_main_food_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = _agent(monkeypatch, MainFoodSelection("food_main"))
    monkeypatch.setattr(
        RuntimeAgent,
        "_package_usable",
        staticmethod(lambda package: package.key == FOOD_EMERGENCY_ID),
    )
    monkeypatch.setattr(agent, "_call_food_llm_api", lambda *_args: "emergency")

    result = agent.generate_structured(
        StructuredRuntimeRequest(
            prompt="structured",
            messages=(),
            response_schema_name="answer",
            response_schema={"type": "object"},
            selected_mode=StructuredGenerationMode.JSON_TEXT,
            allowed_tools=(),
            food_key="food_main",
            food_unavailable=True,
        )
    )

    assert result.model_key == "ollama_0001/emergency"


def test_runtime_does_not_upgrade_primary_to_reasoning_from_task_complexity(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    # Given: an explicit primary request with an available reasoning role.
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = _agent(monkeypatch, MainFoodSelection("food_main"))
    monkeypatch.setattr(agent, "_call_food_llm_api", lambda *_args: "primary response")

    # When: the caller supplies high complexity without requesting reasoning.
    result = agent.think(
        RuntimeRequest(
            prompt="hello",
            elfie_id="00000001",
            semantic_role="primary",
            task_complexity=99,
            allowed_tools=(),
        )
    )

    # Then: the semantic role remains primary.
    assert result.actual_model == "ollama_0001/main"
    assert result.execution_stage == "primary"


def test_runtime_returns_typed_error_for_an_unconfigured_clean_catalog(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    # Given: a clean Runtime home with only disabled system food.
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    _configure_models()
    agent = RuntimeAgent(
        LLMRuntimeConfig(),
        ports=runtime_agent_ports(),
        food_catalog_repository=_InMemoryFoodPort(FoodCatalog()),
    )

    # When/Then: no provider call is attempted without a usable food.
    with pytest.raises(NoAvailableFoodError) as error:
        agent.ask("你好")
    assert error.value.code == "no_available_food"


def test_normal_and_structured_requests_share_the_safe_tool_intersection(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = _agent(monkeypatch, MainFoodSelection("food_main"))
    monkeypatch.setattr(
        RuntimeAgent,
        "_package_usable",
        staticmethod(lambda _package: True),
    )
    captured_messages: list[list[dict[str, object]]] = []

    def caller(*args):
        captured_messages.append(args[2])
        return "ok"

    monkeypatch.setattr(agent, "_call_food_llm_api", caller)
    requested_tools = ("code_sandbox", "web_search", "local_file")

    agent.think(
        RuntimeRequest(
            prompt="normal",
            elfie_id="00000001",
            allowed_tools=requested_tools,
        )
    )
    agent.generate_structured(
        StructuredRuntimeRequest(
            prompt="structured",
            messages=(),
            response_schema_name="answer",
            response_schema={"type": "object"},
            selected_mode=StructuredGenerationMode.JSON_TEXT,
            allowed_tools=requested_tools,
            food_key="food_main",
        )
    )

    assert len(captured_messages) == 2
    for messages in captured_messages:
        rendered = "\n".join(str(message["content"]) for message in messages)
        assert "[SEARCH]" in rendered
        assert "[CODE]" not in rendered
        assert "[READ_FILE]" not in rendered
