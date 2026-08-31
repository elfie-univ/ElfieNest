from __future__ import annotations

import pytest

from app.features.configuration.food import StoredModelEvidence
from elfie.brain.reasoning.food_port import (
    FOOD_COMMON_ID,
    FOOD_EMERGENCY_ID,
    FoodAssignment,
    FoodCatalog,
    FoodPackage,
    MainFoodSelection,
    NoAvailableFoodError,
)
from infrastructure.models.model_execution_agent import ModelExecutionAgent
from infrastructure.models.model_execution_contracts import (
    ModelExecutionRequest,
    StructuredGenerationMode,
    StructuredModelExecutionRequest,
)
from infrastructure.persistence.provider_connections import (
    ProviderConnection,
    ProviderConnectionStore,
    ProviderModelRecord,
)
from test.support.model_execution import model_execution_config
from test.support.model_execution_agent import model_execution_agent_ports


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
) -> ModelExecutionAgent:
    _configure_models()
    agent = ModelExecutionAgent(
        model_execution_config(),
        ports=model_execution_agent_ports(),
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
        ModelExecutionRequest(
            prompt="hello",
            elfie_id="00000001",
            food_key="food_not_authoritative",
            allowed_tools=(),
        )
    )

    # Then: it executes only the persisted main food.
    assert result.food_used == "food_main"
    assert result.actual_model == "ollama_0001/main"


def test_runtime_uses_a_saved_food_package_change_without_reconstruction(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    # Given: one long-lived model executor using the current main food package.
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = _agent(monkeypatch, MainFoodSelection("food_main"))
    monkeypatch.setattr(agent, "_call_food_llm_api", lambda *_args: "ok")
    first = agent.think(
        ModelExecutionRequest(prompt="first", elfie_id="00000001", allowed_tools=())
    )

    # When: management saves another primary model into the same package.
    repository = agent.food_catalog_repository
    assert isinstance(repository, _InMemoryFoodPort)
    repository.update(
        FoodPackage(
            "food_main",
            "主粮",
            primary=FoodAssignment("ollama_0001/reason"),
        )
    )
    second = agent.think(
        ModelExecutionRequest(prompt="second", elfie_id="00000001", allowed_tools=())
    )

    # Then: the next request reads the saved package without rebuilding or restart.
    assert first.actual_model == "ollama_0001/main"
    assert second.actual_model == "ollama_0001/reason"


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
        ModelExecutionRequest(prompt="hello", elfie_id="00000001", allowed_tools=())
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
        ModelExecutionAgent,
        "_package_usable",
        staticmethod(lambda package: package.key == FOOD_EMERGENCY_ID),
    )
    monkeypatch.setattr(agent, "_call_food_llm_api", lambda *_args: "emergency")

    result = agent.generate_structured(
        StructuredModelExecutionRequest(
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


def test_structured_runtime_can_fail_fast_without_emergency_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = _agent(monkeypatch, MainFoodSelection("food_main"))
    monkeypatch.setattr(
        ModelExecutionAgent,
        "_package_usable",
        staticmethod(lambda package: package.key in {"food_main", FOOD_EMERGENCY_ID}),
    )
    calls: list[str] = []

    def caller(provider, model, messages, temperature, max_tokens, options, thinking):
        calls.append(model)
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(agent, "_call_food_llm_api", caller)

    with pytest.raises(NoAvailableFoodError):
        agent.generate_structured(
            StructuredModelExecutionRequest(
                prompt="structured",
                messages=(),
                response_schema_name="answer",
                response_schema={"type": "object"},
                selected_mode=StructuredGenerationMode.JSON_TEXT,
                allowed_tools=(),
                food_key="food_main",
                allow_fallback=False,
            )
        )

    assert calls == ["main"]


def _adoption_agent(evidence: StoredModelEvidence) -> ModelExecutionAgent:
    ports = model_execution_agent_ports()
    ports.model_evidence_source = lambda: {evidence.reference: evidence}
    catalog = FoodCatalog(
        packages={
            FOOD_COMMON_ID: FoodPackage(
                FOOD_COMMON_ID,
                "常用粮",
                system_role="common",
                primary=FoodAssignment(evidence.reference),
            ),
            FOOD_EMERGENCY_ID: FoodPackage(
                FOOD_EMERGENCY_ID,
                "保底粮",
                system_role="emergency",
                primary=FoodAssignment("ollama/emergency:0.5b"),
            ),
        }
    )
    agent = ModelExecutionAgent(
        model_execution_config(),
        ports=ports,
        food_catalog_repository=_InMemoryFoodPort(catalog),
    )
    provider = evidence.reference.split("/", 1)[0]
    agent.config.providers.setdefault(provider, {})["status"] = "active"
    return agent


def test_adoption_rejects_remote_evidence_that_is_no_longer_fresh() -> None:
    agent = _adoption_agent(
        StoredModelEvidence(
            reference="openai/gpt-5.2",
            display_name="GPT-5.2",
            capabilities=frozenset({"text"}),
            verified=False,
            local=False,
            status="stale",
            fresh=False,
        )
    )

    with pytest.raises(NoAvailableFoodError):
        agent.adoption_capabilities()


def test_adoption_structured_generation_uses_a_bounded_provider_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = _adoption_agent(
        StoredModelEvidence(
            reference="openai/gpt-5.2",
            display_name="GPT-5.2",
            capabilities=frozenset({"text"}),
            verified=True,
            local=False,
            status="verified",
            fresh=True,
        )
    )
    calls: list[tuple[object, ...]] = []

    def caller(*args):
        calls.append(args)
        return "{}"

    monkeypatch.setattr(agent, "_call_food_llm_api", caller)

    request = StructuredModelExecutionRequest(
        prompt="structured",
        messages=(),
        response_schema_name="answer",
        response_schema={"type": "object"},
        selected_mode=StructuredGenerationMode.JSON_TEXT,
        allowed_tools=(),
    )
    agent.generate_adoption_structured(request)

    assert calls
    assert calls[0][-1] == 20.0

    agent.generate_adoption_structured(
        request.model_copy(update={"timeout_seconds": 4.5})
    )

    assert calls[-1][-1] == 4.5


@pytest.mark.parametrize(
    "evidence",
    (
        StoredModelEvidence(
            reference="ollama/qwen3:32b",
            display_name="Qwen3 32B",
            capabilities=frozenset({"text"}),
            verified=True,
            local=True,
            status="verified",
            fresh=True,
        ),
        StoredModelEvidence(
            reference="openai/gpt-5.2",
            display_name="GPT-5.2",
            capabilities=frozenset({"text"}),
            verified=False,
            local=False,
            status="failed",
            fresh=False,
        ),
    ),
)
def test_adoption_rejects_local_models_and_latest_failed_remote_evidence(
    evidence: StoredModelEvidence,
) -> None:
    agent = _adoption_agent(evidence)

    with pytest.raises(NoAvailableFoodError):
        agent.adoption_capabilities()


def test_structured_runtime_maps_reasoning_mode_to_provider_thinking(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = _agent(monkeypatch, MainFoodSelection("food_main"))
    thinking_values: list[bool] = []

    def caller(*args):
        thinking_values.append(args[6])
        return "ok"

    monkeypatch.setattr(agent, "_call_food_llm_api", caller)
    base_request = StructuredModelExecutionRequest(
        prompt="structured",
        messages=(),
        response_schema_name="answer",
        response_schema={"type": "object"},
        selected_mode=StructuredGenerationMode.JSON_TEXT,
        allowed_tools=(),
        food_key="food_main",
    )

    agent.generate_structured(base_request)
    agent.generate_structured(
        base_request.model_copy(update={"reasoning_mode": "long"})
    )

    assert thinking_values == [False, True]


def test_runtime_does_not_upgrade_primary_to_reasoning_from_task_complexity(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    # Given: an explicit primary request with an available reasoning role.
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = _agent(monkeypatch, MainFoodSelection("food_main"))
    monkeypatch.setattr(agent, "_call_food_llm_api", lambda *_args: "primary response")

    # When: the caller supplies high complexity without requesting reasoning.
    result = agent.think(
        ModelExecutionRequest(
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
    agent = ModelExecutionAgent(
        model_execution_config(),
        ports=model_execution_agent_ports(),
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
        ModelExecutionAgent,
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
        ModelExecutionRequest(
            prompt="normal",
            elfie_id="00000001",
            allowed_tools=requested_tools,
        )
    )
    agent.generate_structured(
        StructuredModelExecutionRequest(
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


def test_brain_owned_structured_prompt_is_not_augmented_by_provider_injectors(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = _agent(monkeypatch, MainFoodSelection("food_main"))
    monkeypatch.setattr(agent, "_call_food_llm_api", lambda *_args: "ok")
    injected: list[tuple[list[dict[str, object]], list[str]]] = []

    def prompt_injector(messages, tools):
        injected.append((messages, tools))
        return messages

    agent._ports.prompt_injector = prompt_injector  # noqa: SLF001 - boundary seam
    system_prompt = "[APPLICATION_FRAME]\nframe\n\n[IDENTITY_CORE]\nidentity"
    result = agent.generate_structured(
        StructuredModelExecutionRequest(
            prompt="structured",
            messages=({"role": "system", "content": system_prompt},),
            response_schema_name="answer",
            response_schema={"type": "object"},
            selected_mode=StructuredGenerationMode.JSON_TEXT,
            allowed_tools=("web_search",),
            food_key="food_main",
            brain_owned_system_prompt=True,
        )
    )

    assert result.text == "ok"
    assert injected == []
