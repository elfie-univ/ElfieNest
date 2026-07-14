from runtime.config import LLMRuntimeConfig
from runtime.food.models import ExecutionProfile, FoodRecipe
from runtime.food.store import FoodCatalog
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
