"""RuntimeAgent 的粮食策略契约测试。"""

from __future__ import annotations

from ai_runtime.food.models import ExecutionProfile, FoodRecipe
from ai_runtime.food.store import FoodCatalog
from ai_runtime.gateway.agent import RuntimeAgent
from ai_runtime.gateway.request import RuntimeRequest
from ai_runtime.storage.config_store import write_yaml_mapping
from ai_runtime.storage.data_home import get_provider_config_path
from ai_runtime.storage.runtime_config_bundle import write_runtime_config_bundle


def _configure_foods(agent: RuntimeAgent) -> None:
    agent.food_catalog_store.save(
        FoodCatalog(
            default_food="standard",
            fallback_food="coarse",
            recipes={
                key: FoodRecipe(key, key, "test", profile)
                for key, profile in {
                    "coarse": ExecutionProfile("ollama/coarse"),
                    "standard": ExecutionProfile("ollama/standard"),
                    "focus": ExecutionProfile("cloud/focus"),
                    "tool": ExecutionProfile(
                        "cloud/tool",
                        tools=("web_search", "local_file", "code_sandbox"),
                    ),
                }.items()
            },
        )
    )
    agent.config.providers["cloud"] = {"api_key": "test-placeholder"}


def test_runtime_agent_public_surface_is_food_only(monkeypatch, tmp_path):
    """Given a RuntimeAgent, Then direct model generation and ModelRouter are absent."""
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = RuntimeAgent()

    assert not hasattr(agent, "generate")
    assert not hasattr(agent, "router")
    assert hasattr(agent, "ask")
    assert hasattr(agent, "think")
    assert hasattr(agent, "run_with_food")


def test_runtime_agent_requires_formal_food_catalog(monkeypatch, tmp_path):
    """Given no food package, When asking, Then initialization is explicit."""
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = RuntimeAgent()

    try:
        agent.ask("hello")
    except RuntimeError as exc:
        assert "food-packages.yaml" in str(exc)
    else:
        raise AssertionError("缺少正式粮食目录时不应隐式生成兼容配方")


def test_runtime_agent_live_reload_watches_provider_document(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    write_runtime_config_bundle(
        {
            "providers": {
                "custom_gateway": {
                    "api_base": "https://before.example/v1",
                    "api_mode": "chat_completions",
                }
            }
        }
    )
    agent = RuntimeAgent(live_reload=True)

    write_yaml_mapping(
        get_provider_config_path(),
        {
            "version": 1,
            "providers": {
                "custom_gateway": {
                    "api_base": "https://after.example/v1",
                    "api_mode": "chat_completions",
                }
            },
        },
    )
    agent._reload_config_if_changed()

    assert (
        agent.config.providers["custom_gateway"]["api_base"]
        == "https://after.example/v1"
    )


def test_ask_uses_standard_food_for_normal_task(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = RuntimeAgent()
    _configure_foods(agent)
    calls: list[tuple[str, str]] = []
    agent._call_food_llm_api = lambda provider, model, *args: (
        calls.append((provider, model)) or "hello"
    )

    assert agent.ask("hello", energy=80.0, task_complexity=1) == "hello"
    assert calls == [("ollama", "standard")]


def test_low_energy_stays_in_the_configured_default_package(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = RuntimeAgent()
    _configure_foods(agent)
    calls: list[tuple[str, str]] = []
    agent._call_food_llm_api = lambda provider, model, *args: (
        calls.append((provider, model)) or "response"
    )

    assert agent.ask("hello", energy=20.0) == "response"
    assert calls == [("ollama", "standard")]


def test_think_keeps_food_key_and_never_routes_model_directly(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = RuntimeAgent()
    _configure_foods(agent)
    calls: list[tuple[str, str]] = []
    agent._call_food_llm_api = lambda provider, model, *args: (
        calls.append((provider, model)) or "focus result"
    )

    result = agent.think(
        RuntimeRequest(prompt="分析计划", food_key="focus", allowed_tools=())
    )

    assert result.food_requested == "focus"
    assert result.food_used == "focus"
    assert result.actual_model == "cloud/focus"
    assert calls == [("cloud", "focus")]


def test_complex_task_selects_deep_role_inside_the_same_package(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = RuntimeAgent()
    _configure_foods(agent)
    catalog = agent.food_catalog_store.load()
    recipes = dict(catalog.recipes)
    recipes["standard"] = FoodRecipe(
        "standard",
        "standard",
        "test",
        ExecutionProfile("ollama/standard"),
        deep=ExecutionProfile("cloud/standard-deep"),
    )
    agent.food_catalog_store.save(
        FoodCatalog(
            default_food="standard",
            fallback_food="coarse",
            recipes=recipes,
        )
    )
    agent._call_food_llm_api = lambda *args: "deep result"

    result = agent.think(
        RuntimeRequest(
            prompt="分析计划",
            task_complexity=agent.config.complexity_threshold_deep,
            allowed_tools=(),
        )
    )

    assert result.food_used == "standard"
    assert result.actual_model == "cloud/standard-deep"
    assert result.execution_stage == "deep"


def test_selected_package_failure_uses_global_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = RuntimeAgent()
    _configure_foods(agent)

    def call(provider, model, *args):
        if model == "standard":
            raise RuntimeError("subscription expired")
        return "fallback result"

    agent._call_food_llm_api = call

    result = agent.think(
        RuntimeRequest(prompt="hello", food_key="standard", allowed_tools=())
    )

    assert result.text == "fallback result"
    assert result.food_requested == "standard"
    assert result.food_used == "coarse"
    assert result.degraded is True
    assert result.execution_stage == "global_fallback:primary"
