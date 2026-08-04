from ai_runtime.config import LLMRuntimeConfig
from ai_runtime.food.executor import FoodExecutor
from ai_runtime.food.models import FoodPackage, ModelAssignment


class _Permission:
    def verify_action(self, *args, **kwargs):
        return None


def test_executor_uses_role_then_one_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    calls = []

    def caller(provider, model, messages, temperature, max_tokens, options):
        calls.append(f"{provider}/{model}")
        if model == "reason":
            raise RuntimeError("down")
        return "ok"

    config = LLMRuntimeConfig()
    config.providers["cloud_0001"] = {
        "api_mode": "chat_completions",
        "api_key": "test",
    }
    executor = FoodExecutor(
        config=config,
        search_plugin=None,
        permission_manager=_Permission(),
        file_access_plugin=None,
        model_caller=caller,
    )
    result = executor.execute(
        FoodPackage(
            "food_x",
            "X",
            primary=ModelAssignment("cloud_0001/main"),
            reasoning=ModelAssignment("cloud_0001/reason"),
            fallback=ModelAssignment("cloud_0001/backup"),
        ),
        [{"role": "user", "content": "hi"}],
        semantic_role="reasoning",
    )
    assert calls == ["cloud_0001/reason", "cloud_0001/backup"]
    assert result.model == "cloud_0001/backup"
    assert result.execution_stage == "fallback"
    assert len(result.attempts) == 2
