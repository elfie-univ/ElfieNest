from ai_runtime.gateway.agent import RuntimeAgent
from ai_runtime.gateway.request import RuntimeRequest, RuntimeResult
from ai_runtime.food.models import ExecutionProfile, FoodRecipe
from ai_runtime.food.store import FoodCatalog


def _save_food(agent, food_key, model):
    agent.food_catalog_store.save(
        FoodCatalog(
            recipes={
                food_key: FoodRecipe(
                    food_key, food_key, "test", ExecutionProfile(model)
                )
            }
        )
    )


def test_think_uses_request_and_returns_runtime_result(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = RuntimeAgent()
    _save_food(agent, "standard", "ollama/food-standard")

    request = RuntimeRequest(
        prompt="Hello",
        energy=75.0,
        task_complexity=1,
        allowed_tools=("web_search", "code_sandbox"),
    )

    def fake_call(provider, model, messages, temperature, max_tokens, options):
        assert (provider, model) == ("ollama", "food-standard")
        assert messages == [{"role": "user", "content": "Hello"}]
        return "Hi"

    agent._call_food_llm_api = fake_call

    result = agent.think(request)

    assert isinstance(result, RuntimeResult)
    assert result.text == "Hi"
    assert result.model_key == "ollama/food-standard"
    assert result.food_used == "standard"
    assert result.mode == "local"
    assert result.degraded is False


def test_ask_keeps_returning_plain_text():
    agent = RuntimeAgent()

    def fake_think(request):
        assert request.prompt == "Hello"
        return RuntimeResult(
            text="Hi",
            mode="local",
            model_key="local_fast",
            decision={"mode": "local"},
        )

    agent.think = fake_think

    assert agent.ask("Hello") == "Hi"


def test_think_maps_legacy_task_type_to_food(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = RuntimeAgent()
    _save_food(agent, "focus", "cloud/reasoner")
    agent.config.providers["cloud"] = {"api_key": "test-placeholder"}

    request = RuntimeRequest(
        prompt="分析一下这个计划",
        energy=90.0,
        task_complexity=1,
        allowed_tools=(),
        metadata=(("task_type", "reasoning"),),
    )

    def fake_call(provider, model, messages, temperature, max_tokens, options):
        assert (provider, model) == ("cloud", "reasoner")
        return "分析结果"

    agent._call_food_llm_api = fake_call

    result = agent.think(request)

    assert result.text == "分析结果"
    assert result.model_key == "cloud/reasoner"
    assert result.food_used == "focus"
    assert result.decision["food"]["actual"] == "focus"


def test_runtime_task_route_can_only_override_with_food_key(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = RuntimeAgent()
    _save_food(agent, "premium", "ollama/premium")
    agent.config.runtime_policy = {"task_routes": {"reasoning": "premium"}}
    agent._call_food_llm_api = lambda *args: "premium answer"

    result = agent.think(
        RuntimeRequest(
            prompt="分析计划",
            metadata=(("task_type", "reasoning"),),
            allowed_tools=(),
        )
    )

    assert result.food_used == "premium"
