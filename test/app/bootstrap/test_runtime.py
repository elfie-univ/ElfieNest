"""Runtime composition stays inside Bootstrap without changing selection behavior."""

from types import SimpleNamespace

from app.bootstrap import runtime as runtime_bootstrap
from infrastructure.models.fallback_runtime import FallbackRuntimeAdapter


class _FakeRuntime:
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


def test_fallback_runtime_preserves_configured_tick_interval(monkeypatch) -> None:
    monkeypatch.setattr(
        runtime_bootstrap,
        "LLMRuntimeConfig",
        lambda **_kwargs: SimpleNamespace(
            system={"engine": {"tick_interval_sec": 2.25}}
        ),
    )

    services = runtime_bootstrap.build_runtime_services(
        ":memory:",
        use_fallback=True,
        live_reload=True,
        resolve_main_food=False,
    )

    assert isinstance(services.runtime, FallbackRuntimeAdapter)
    assert services.tick_interval_sec == 2.25
    assert services.main_food_loader is None
    assert services.warmup is None


def test_model_runtime_receives_existing_food_and_warmup_dependencies(
    monkeypatch,
) -> None:
    config = SimpleNamespace(system={"engine": {}})
    repository = object()
    loader = object()
    monkeypatch.setattr(
        runtime_bootstrap,
        "LLMRuntimeConfig",
        lambda **_kwargs: config,
    )
    monkeypatch.setattr(runtime_bootstrap, "RuntimeAgent", _FakeRuntime)
    monkeypatch.setattr(
        runtime_bootstrap,
        "SQLiteFoodPackageRepository",
        lambda db_path: (repository, db_path),
    )
    monkeypatch.setattr(
        runtime_bootstrap,
        "build_food_service",
        lambda db_path: ("food-service", db_path),
    )
    monkeypatch.setattr(
        runtime_bootstrap,
        "final_main_food_loader",
        lambda service: (loader, service),
    )

    services = runtime_bootstrap.build_runtime_services(
        "/tmp/nest.db",
        use_fallback=False,
        live_reload=True,
        resolve_main_food=True,
    )

    assert isinstance(services.runtime, _FakeRuntime)
    assert services.runtime.kwargs == {
        "live_reload": True,
        "main_food_loader": (loader, ("food-service", "/tmp/nest.db")),
        "food_catalog_repository": (repository, "/tmp/nest.db"),
    }
    assert services.tick_interval_sec == 1.5
    assert services.warmup is not None
    services.warmup()
    assert services.runtime.warmup_calls == [("hello", 100, 1, [])]
