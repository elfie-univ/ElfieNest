"""Regression coverage for the service engine bootstrap scope."""

import inspect

from scripts import serve


def test_engine_worker_uses_module_repository_without_uninitialized_closure() -> None:
    # Given: the service entry point defines a worker that constructs the engine.
    cell_variables = serve.main.__code__.co_cellvars

    # When: the worker resolves the repository constructor.

    # Then: the constructor is not captured as an uninitialized main-local cell.
    assert "SQLiteNestStateRepository" not in cell_variables


def test_service_does_not_create_a_default_elfie() -> None:
    # Given: the production service entrypoint is inspected before startup.
    source = inspect.getsource(serve)

    # Then: an empty Nest stays empty until the Owner completes adoption.
    assert "seed_single_elfie" not in source
    assert "Aifei" not in source


def test_serve_does_not_call_the_removed_runtime_owned_ollama_manager() -> None:
    # Given: public Ollama startup belongs to lifecycle orchestration.
    main_source = inspect.getsource(serve.main)

    # When: the service worker builds the Runtime agent.

    # Then: it cannot silently fall back because of a deleted Runtime attribute.
    assert "ollama_manager.ensure_service_started" not in main_source


def test_service_entrypoint_uses_bootstrap_instead_of_concrete_adapters() -> None:
    source = inspect.getsource(serve)

    assert "ModelExecutionAgent(" not in source
    assert "ModelExecutionConfig(" not in source
    assert "SQLiteFoodPackageRepository(" not in source
    assert "SQLiteElfiesProjectionAdapter(" not in source
    assert "ElfieFactory(" not in source
    assert "init_db(" not in source


def test_production_engine_loop_has_no_fixed_tick_expiry() -> None:
    main_source = inspect.getsource(serve.main)

    assert "ticks_to_run=None" in main_source
    assert "ticks_to_run=100000" not in main_source


def test_api_exception_logging_does_not_persist_query_values() -> None:
    from app.interfaces.api import app as api_app

    source = inspect.getsource(api_app.create_http_application)

    assert 'request.scope.get("route")' in source
    assert 'getattr(route, "path", "<unmatched>")' in source
    assert "request.method, route_template" in source
    assert "request.method, request.url.path" not in source


def test_uvicorn_errors_stay_on_the_rotated_core_log_handler() -> None:
    main_source = inspect.getsource(serve.main)

    assert "log_config=None" in main_source


def test_server_runtime_keeps_live_reload_when_configured_model_cannot_warm_up(
    monkeypatch,
) -> None:
    def fail_warmup() -> None:
        raise RuntimeError("provider unavailable")

    # Given: configuration loads, but the selected provider is unreachable.
    configured = serve.ModelExecutionServices(
        execution=object(),
        tick_interval_sec=1.5,
        warmup=fail_warmup,
    )
    calls: list[tuple[bool, bool]] = []

    def build(_db_path: str, *, live_reload: bool, resolve_main_food: bool):
        calls.append((live_reload, resolve_main_food))
        return configured

    monkeypatch.setattr(serve, "build_model_execution_services", build)

    # When
    selected = serve.build_server_model_execution_services(":memory:")

    # Then: the configured live-reloading runtime remains installed so a model
    # package saved after startup can recover on the very next request.
    assert calls == [(True, True)]
    assert selected is configured
