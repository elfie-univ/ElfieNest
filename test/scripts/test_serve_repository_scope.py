"""Regression coverage for the service engine bootstrap scope."""

import inspect

from ai_runtime.gateway.request import (
    StructuredGenerationMode,
    StructuredRuntimeRequest,
)
from scripts import serve


def test_engine_worker_uses_module_repository_without_uninitialized_closure() -> None:
    # Given: the service entry point defines a worker that constructs the engine.
    cell_variables = serve.main.__code__.co_cellvars

    # When: the worker resolves the repository constructor.

    # Then: the constructor is not captured as an uninitialized main-local cell.
    assert "SQLiteNestStateRepository" not in cell_variables


def test_fallback_agent_satisfies_the_structured_runtime_contract() -> None:
    # Given: the service must remain able to run cognition without a model provider.
    fallback = serve.FallbackAgent()
    request = StructuredRuntimeRequest(
        prompt="hello",
        messages=(),
        response_schema_name="DecisionPlan",
        response_schema={"type": "object"},
        selected_mode=StructuredGenerationMode.JSON_TEXT,
        allowed_tools=(),
        provider="fallback",
        model_key="fallback/local",
    )

    # When: orchestration requests structured generation.
    capabilities = fallback.structured_capabilities()
    result = fallback.generate_structured(request)

    # Then: the fallback provides the adapter's complete public protocol.
    assert capabilities.provider == "fallback"
    assert result.provider == "fallback"
    assert result.model_key == "fallback/local"
    assert result.text


def test_serve_does_not_call_the_removed_runtime_owned_ollama_manager() -> None:
    # Given: public Ollama startup belongs to lifecycle orchestration.
    main_source = inspect.getsource(serve.main)

    # When: the service worker builds the Runtime agent.

    # Then: it cannot silently fall back because of a deleted Runtime attribute.
    assert "ollama_manager.ensure_service_started" not in main_source
