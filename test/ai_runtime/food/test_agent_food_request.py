import pytest

from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.food.elfie_policy import ElfieFoodPolicy, save_elfie_food_policy
from ai_runtime.food.models import ExecutionProfile, FoodRecipe
from ai_runtime.food.store import FoodCatalog
from ai_runtime.gateway.agent import RuntimeAgent
from ai_runtime.gateway.request import RuntimeRequest


def test_runtime_agent_does_not_expose_direct_model_generation(monkeypatch, tmp_path):
    """Given a runtime agent, When inspecting its public surface, Then only food APIs exist."""
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = RuntimeAgent(LLMRuntimeConfig())

    assert not hasattr(agent, "generate")
    assert not hasattr(agent, "router")


def test_runtime_agent_requires_formal_food_catalog(monkeypatch, tmp_path):
    """Given no food package, When a request runs, Then initialization is explicit."""
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = RuntimeAgent(LLMRuntimeConfig())

    with pytest.raises(RuntimeError, match="food-packages.yaml"):
        agent.ask("你好")


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


def test_complex_request_uses_deep_profile_inside_selected_food(monkeypatch, tmp_path):
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
            elfie_id="elfie_test_1",
            food_key="standard",
            scene="emotion_peak",
            task_complexity=agent.config.complexity_threshold_deep,
            allowed_tools=(),
        )
    )

    assert result.food_requested == "standard"
    assert result.food_used == "standard"
    assert result.food_clamped is False
    assert result.actual_model == "ollama/standard-deep"
    assert result.execution_stage == "deep"


def test_runtime_does_not_read_package_policy_from_elfie_workspace(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path / "global"))
    config_dir = tmp_path / "custom-elfie"
    save_elfie_food_policy(
        ElfieFoodPolicy(
            "elfie-1",
            "coarse",
            ("coarse",),
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


def test_missing_food_file_requires_explicit_initialization(monkeypatch, tmp_path):
    """Given missing food package, Then no compatibility recipe is created."""
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    agent = RuntimeAgent(LLMRuntimeConfig())

    with pytest.raises(RuntimeError, match="food-packages.yaml"):
        agent.ask("你好")

    assert not (tmp_path / "configs" / "food-packages.yaml").exists()
