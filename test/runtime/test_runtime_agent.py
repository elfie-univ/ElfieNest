"""RuntimeAgent 的粮食策略契约测试。"""

from __future__ import annotations

from runtime.food.models import ExecutionProfile, FoodRecipe
from runtime.food.store import FoodCatalog
from runtime.gateway.agent import RuntimeAgent
from runtime.gateway.request import RuntimeRequest


def _configure_foods(agent: RuntimeAgent) -> None:
    agent.food_catalog_store.save(
        FoodCatalog(
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
            }
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
    """Given no foods.yaml, When asking, Then initialization is explicit."""
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = RuntimeAgent()

    try:
        agent.ask("hello")
    except RuntimeError as exc:
        assert "foods.yaml" in str(exc)
    else:
        raise AssertionError("缺少正式粮食目录时不应隐式生成兼容配方")


def test_ask_uses_standard_food_for_normal_task(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = RuntimeAgent()
    _configure_foods(agent)
    calls: list[tuple[str, str]] = []
    agent._call_food_llm_api = lambda provider, model, *args: calls.append(
        (provider, model)
    ) or "hello"

    assert agent.ask("hello", energy=80.0, task_complexity=1) == "hello"
    assert calls == [("ollama", "standard")]


def test_ask_uses_coarse_food_for_low_energy(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = RuntimeAgent()
    _configure_foods(agent)
    calls: list[tuple[str, str]] = []
    agent._call_food_llm_api = lambda provider, model, *args: calls.append(
        (provider, model)
    ) or "response"

    assert agent.ask("hello", energy=20.0) == "response"
    assert calls == [("ollama", "coarse")]


def test_think_keeps_food_key_and_never_routes_model_directly(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = RuntimeAgent()
    _configure_foods(agent)
    calls: list[tuple[str, str]] = []
    agent._call_food_llm_api = lambda provider, model, *args: calls.append(
        (provider, model)
    ) or "focus result"

    result = agent.think(
        RuntimeRequest(prompt="分析计划", food_key="focus", allowed_tools=())
    )

    assert result.food_requested == "focus"
    assert result.food_used == "focus"
    assert result.actual_model == "cloud/focus"
    assert calls == [("cloud", "focus")]


def test_task_route_can_only_select_a_food_key(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = RuntimeAgent()
    _configure_foods(agent)
    agent.config.runtime_policy = {"task_routes": {"reasoning": "focus"}}
    agent._call_food_llm_api = lambda *args: "focus result"

    result = agent.think(
        RuntimeRequest(
            prompt="分析计划",
            metadata=(("task_type", "reasoning"),),
            allowed_tools=(),
        )
    )

    assert result.food_used == "focus"
    assert result.actual_model == "cloud/focus"
