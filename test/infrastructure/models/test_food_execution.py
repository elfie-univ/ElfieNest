import pytest

from elfie.brain.reasoning.food_port import FoodAssignment, FoodPackage
from infrastructure.models.food_execution import FoodExecutionError, FoodExecutor
from infrastructure.models.model_execution_config import ModelExecutionConfig
from infrastructure.tools import DisabledToolPort
from infrastructure.tools.execution.loop import PortToolLoop
from infrastructure.tools.execution.skills_prompt import inject_skills_system_prompt


def test_executor_uses_role_then_one_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    calls = []

    def caller(provider, model, messages, temperature, max_tokens, options):
        calls.append(f"{provider}/{model}")
        if model == "reason":
            raise RuntimeError("down")
        return "ok"

    config = ModelExecutionConfig()
    config.providers["cloud_0001"] = {
        "api_mode": "chat_completions",
        "api_key": "test",
    }
    executor = FoodExecutor(
        config=config,
        tool_port=DisabledToolPort(),
        model_caller=caller,
        tool_loop_factory=lambda port, allowed, scope: PortToolLoop(
            port, allowed_tool_keys=allowed, scope_id=scope
        ),
        prompt_injector=inject_skills_system_prompt,
    )
    result = executor.execute(
        FoodPackage(
            "food_x",
            "X",
            primary=FoodAssignment("cloud_0001/main"),
            reasoning=FoodAssignment("cloud_0001/reason"),
            fallback=FoodAssignment("cloud_0001/backup"),
        ),
        [{"role": "user", "content": "hi"}],
        semantic_role="reasoning",
    )
    assert calls == ["cloud_0001/reason", "cloud_0001/backup"]
    assert result.model == "cloud_0001/backup"
    assert result.execution_stage == "fallback"
    assert len(result.attempts) == 2


def test_executor_can_fail_fast_without_package_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    calls = []

    def caller(provider, model, messages, temperature, max_tokens, options):
        calls.append(f"{provider}/{model}")
        raise RuntimeError("down")

    config = ModelExecutionConfig()
    config.providers["cloud_0001"] = {
        "api_mode": "chat_completions",
        "api_key": "test",
    }
    executor = FoodExecutor(
        config=config,
        tool_port=DisabledToolPort(),
        model_caller=caller,
        tool_loop_factory=lambda port, allowed, scope: PortToolLoop(
            port, allowed_tool_keys=allowed, scope_id=scope
        ),
        prompt_injector=inject_skills_system_prompt,
    )

    with pytest.raises(FoodExecutionError):
        executor.execute(
            FoodPackage(
                "food_x",
                "X",
                primary=FoodAssignment("cloud_0001/main"),
                fallback=FoodAssignment("cloud_0001/backup"),
            ),
            [{"role": "user", "content": "hi"}],
            allow_fallback=False,
        )

    assert calls == ["cloud_0001/main"]
