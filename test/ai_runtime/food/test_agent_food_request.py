import pytest

from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.food.elfie_policy import ElfieFoodPolicy
from ai_runtime.food.models import FoodPackage, ModelAssignment
from ai_runtime.food.store import FoodCatalog
from ai_runtime.gateway.agent import RuntimeAgent
from ai_runtime.gateway.request import RuntimeRequest
from ai_runtime.storage.provider_connections import (
    ProviderConnection,
    ProviderConnectionStore,
    ProviderModelRecord,
)


def _setup_provider_connections():
    store = ProviderConnectionStore()
    store.replace(
        ProviderConnection(
            connection_id="ollama_0001",
            catalog_id="ollama",
            alias="Ollama",
            models=(
                ProviderModelRecord("food-model"),
                ProviderModelRecord("local"),
                ProviderModelRecord("coarse"),
                ProviderModelRecord("standard"),
                ProviderModelRecord("focus"),
            ),
        )
    )
    store.replace(
        ProviderConnection(
            connection_id="cloud_0001",
            catalog_id="cloud",
            alias="Cloud",
            models=(
                ProviderModelRecord("standard"),
                ProviderModelRecord("focus"),
                ProviderModelRecord("normal"),
                ProviderModelRecord("standard-reasoning"),
            ),
        )
    )


class _Runtime:
    def ask_with_food(self, **kwargs):
        self.kwargs = kwargs
        return "ok"


def test_runtime_agent_creates_default_catalog_when_missing(monkeypatch, tmp_path):
    """Given no foods.yaml, When a request runs, Then a default catalog is created."""
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    _setup_provider_connections()
    agent = RuntimeAgent(LLMRuntimeConfig())

    with pytest.raises(ValueError, match="尚未配置"):
        agent.ask("你好")

    assert (tmp_path / "configs" / "food-packages.yaml").exists()


def test_runtime_agent_accepts_food_interface_without_exposing_reasoning(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    _setup_provider_connections()
    config = LLMRuntimeConfig()
    agent = RuntimeAgent(config)
    agent.food_catalog_store.save(
        FoodCatalog(
            packages={
                "standard": FoodPackage(
                    key="standard",
                    display_name="标准粮",
                    primary=ModelAssignment(model="ollama_0001/food-model"),
                ),
                "coarse": FoodPackage(
                    key="coarse",
                    display_name="粗粮",
                    primary=ModelAssignment(model="ollama_0001/local"),
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
    assert result.actual_model == "ollama_0001/food-model"
    assert result.execution_stage == "primary"
    assert result.decision["food"]["actual"] == "standard"


def test_unauthorized_upgrade_uses_reasoning_role_inside_allowed_food(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    _setup_provider_connections()
    agent = RuntimeAgent(LLMRuntimeConfig())
    agent.food_catalog_store.save(
        FoodCatalog(
            packages={
                "standard": FoodPackage(
                    key="standard",
                    display_name="标准粮",
                    primary=ModelAssignment(model="cloud_0001/normal"),
                    reasoning=ModelAssignment(model="cloud_0001/standard-reasoning"),
                ),
                "coarse": FoodPackage(
                    key="coarse",
                    display_name="粗粮",
                    primary=ModelAssignment(model="ollama_0001/local"),
                ),
            }
        )
    )
    monkeypatch.setattr(agent, "_call_food_llm_api", lambda *args: "reasoning response")

    result = agent.think(
        RuntimeRequest(
            prompt="hard",
            elfie_id="00000001",
            food_key="premium",
            scene="emotion_peak",
            allowed_tools=(),
        )
    )

    assert result.food_requested == "premium"
    assert result.food_used == "standard"
    assert result.food_clamped is True
    assert result.actual_model == "cloud_0001/standard-reasoning"
    assert result.execution_stage == "reasoning"


def test_runtime_reads_policy_from_injected_final_store(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path / "global"))
    _setup_provider_connections()
    policy = ElfieFoodPolicy(
        "00000001",
        "focus",
        ("coarse", "standard", "focus"),
        "coarse",
    )
    agent = RuntimeAgent(
        LLMRuntimeConfig(),
        food_policy_loader=lambda elfie_id: policy,
    )
    agent.food_catalog_store.save(
        FoodCatalog(
            packages={
                "coarse": FoodPackage(
                    key="coarse",
                    display_name="粗粮",
                    primary=ModelAssignment(model="ollama_0001/coarse"),
                ),
                "standard": FoodPackage(
                    key="standard",
                    display_name="标准粮",
                    primary=ModelAssignment(model="cloud_0001/standard"),
                ),
                "focus": FoodPackage(
                    key="focus",
                    display_name="清醒粮",
                    primary=ModelAssignment(model="cloud_0001/focus"),
                ),
            }
        )
    )
    agent._call_food_llm_api = lambda *args: "focused"

    result = agent.run_with_food(
        prompt="分析",
        food_key="focus",
        elfie_id="00000001",
        allowed_skills=[],
    )

    assert result.food_used == "focus"
    assert result.actual_model == "cloud_0001/focus"


def test_missing_food_file_requires_explicit_initialization(monkeypatch, tmp_path):
    """Given missing foods.yaml, When asking, Then no compatibility recipe is created."""
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    _setup_provider_connections()
    agent = RuntimeAgent(LLMRuntimeConfig())

    with pytest.raises(ValueError, match="尚未配置"):
        agent.ask("你好")

    assert (tmp_path / "configs" / "food-packages.yaml").exists()
