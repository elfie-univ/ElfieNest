from runtime.config import LLMRuntimeConfig
from runtime.food.models import ExecutionProfile, FoodRecipe
from runtime.food.store import FoodCatalog
from runtime.food.elfie_policy import ElfieFoodPolicy, save_elfie_food_policy
from runtime.gateway.agent import RuntimeAgent
from runtime.gateway.request import RuntimeRequest


def test_runtime_agent_accepts_food_interface_without_exposing_reasoning(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    config = LLMRuntimeConfig()
    agent = RuntimeAgent(config)
    agent.food_catalog_store.save(
        FoodCatalog(
            recipes={
                "standard": FoodRecipe(
                    "standard",
                    "标准粮",
                    "默认",
                    ExecutionProfile("ollama/food-model"),
                ),
                "coarse": FoodRecipe(
                    "coarse",
                    "粗粮",
                    "本地",
                    ExecutionProfile("ollama/local"),
                ),
            }
        )
    )
    monkeypatch.setattr(agent, "_call_food_llm_api", lambda *args: "food response")

    result = agent.think(
        RuntimeRequest(prompt="hello", food_key="standard", allowed_tools=())
    )

    assert result.text == "food response"
    assert result.food_used == "standard"
    assert result.actual_model == "ollama/food-model"
    assert result.execution_stage == "primary"
    assert result.decision["food"]["actual"] == "standard"


def test_unauthorized_upgrade_uses_deep_profile_inside_allowed_food(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = RuntimeAgent(LLMRuntimeConfig())
    agent.food_catalog_store.save(
        FoodCatalog(
            recipes={
                "standard": FoodRecipe(
                    "standard",
                    "标准粮",
                    "默认",
                    ExecutionProfile("ollama/normal"),
                    deep=ExecutionProfile("ollama/standard-deep"),
                ),
                "coarse": FoodRecipe(
                    "coarse",
                    "粗粮",
                    "本地",
                    ExecutionProfile("ollama/local"),
                ),
            }
        )
    )
    monkeypatch.setattr(agent, "_call_food_llm_api", lambda *args: "deep response")

    result = agent.think(
        RuntimeRequest(
            prompt="hard",
            elfie_id="elfie-1",
            food_key="premium",
            scene="emotion_peak",
            allowed_tools=(),
        )
    )

    assert result.food_requested == "premium"
    assert result.food_used == "standard"
    assert result.food_clamped is True
    assert result.actual_model == "ollama/standard-deep"
    assert result.execution_stage == "deep"


def test_runtime_reads_policy_from_elfie_actual_config_directory(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path / "global"))
    config_dir = tmp_path / "custom-elfie"
    save_elfie_food_policy(
        ElfieFoodPolicy(
            "elfie-1",
            "focus",
            ("coarse", "standard", "focus"),
            "coarse",
        ),
        config_dir,
    )
    agent = RuntimeAgent(LLMRuntimeConfig())
    agent.food_catalog_store.save(
        FoodCatalog(
            recipes={
                "coarse": FoodRecipe(
                    "coarse", "粗粮", "", ExecutionProfile("ollama/coarse")
                ),
                "standard": FoodRecipe(
                    "standard", "标准粮", "", ExecutionProfile("ollama/standard")
                ),
                "focus": FoodRecipe(
                    "focus", "清醒粮", "", ExecutionProfile("ollama/focus")
                ),
            }
        )
    )
    agent._call_food_llm_api = lambda *args: "focused"

    result = agent.run_with_food(
        prompt="分析",
        food_key="focus",
        elfie_id="elfie-1",
        elfie_config_dir=str(config_dir),
        allowed_skills=[],
    )

    assert result.food_used == "focus"
    assert result.actual_model == "ollama/focus"


def test_missing_food_file_uses_internal_compatibility_food_not_legacy_router(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = RuntimeAgent(LLMRuntimeConfig())
    calls = []
    agent._call_food_llm_api = lambda provider, model, *args: calls.append(
        (provider, model)
    ) or "ok"
    monkeypatch.setattr(
        agent.router,
        "route_request",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("旧模型路由不应被调用")
        ),
    )

    result = agent.ask("你好")

    assert result == "ok"
    assert calls == [("ollama", agent.config.cheap_model)]
    assert not (tmp_path / "foods.yaml").exists()
