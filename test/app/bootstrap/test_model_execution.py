"""Model execution stays inside Bootstrap without changing selection behavior."""

from types import SimpleNamespace

from app.bootstrap import model_execution as model_execution_bootstrap


class _FakeModelExecution:
    def __init__(self, config: object, **kwargs: object) -> None:
        self.config = config
        self.kwargs = kwargs
        self.warmup_calls: list[tuple[str, int, int, list[str]]] = []

    def ask(
        self,
        prompt: str,
        *,
        energy: int,
        task_complexity: int,
        allowed_skills: list[str],
    ) -> None:
        self.warmup_calls.append((prompt, energy, task_complexity, allowed_skills))


def test_model_execution_receives_existing_food_and_warmup_dependencies(
    monkeypatch,
) -> None:
    config = SimpleNamespace(system={"engine": {"tick_interval_sec": 2.25}})
    repository = object()
    loader = object()
    monkeypatch.setattr(
        model_execution_bootstrap,
        "load_model_execution_config",
        lambda **_kwargs: config,
    )
    monkeypatch.setattr(
        model_execution_bootstrap, "ModelExecutionAgent", _FakeModelExecution
    )
    monkeypatch.setattr(
        model_execution_bootstrap,
        "SQLiteFoodAdapter",
        lambda db_path: (repository, db_path),
    )
    monkeypatch.setattr(
        model_execution_bootstrap,
        "build_food_service",
        lambda db_path: ("food-service", db_path),
    )
    monkeypatch.setattr(
        model_execution_bootstrap,
        "final_main_food_loader",
        lambda service: (loader, service),
    )

    services = model_execution_bootstrap.build_model_execution_services(
        "/tmp/nest.db",
        live_reload=True,
        resolve_main_food=True,
    )

    assert isinstance(services.execution, _FakeModelExecution)
    assert services.execution.kwargs["ports"] is not None
    assert services.execution.kwargs["live_reload"] is True
    assert services.execution.kwargs["main_food_loader"] == (
        loader,
        ("food-service", "/tmp/nest.db"),
    )
    assert services.execution.kwargs["food_catalog_repository"] == (
        repository,
        "/tmp/nest.db",
    )
    assert services.tick_interval_sec == 2.25
    assert services.warmup is not None
    services.warmup()
    assert services.execution.warmup_calls == [("hello", 100, 1, [])]
