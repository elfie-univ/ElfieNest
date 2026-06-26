from runtime.gateway.agent import RuntimeAgent
from runtime.gateway.request import RuntimeRequest, RuntimeResult


def test_think_uses_request_and_returns_runtime_result():
    agent = RuntimeAgent()

    request = RuntimeRequest(
        prompt="Hello",
        energy=75.0,
        task_complexity=1,
        allowed_tools=("web_search", "code_sandbox"),
    )

    def fake_generate(**kwargs):
        assert kwargs["model_key"] == "local_fast"
        assert kwargs["messages"] == [{"role": "user", "content": "Hello"}]
        assert kwargs["allowed_skills"] == ["web_search", "code_sandbox"]
        return "Hi"

    agent.generate = fake_generate

    result = agent.think(request)

    assert isinstance(result, RuntimeResult)
    assert result.text == "Hi"
    assert result.model_key == "local_fast"
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


def test_think_uses_food_policy_task_type_from_metadata():
    agent = RuntimeAgent()

    request = RuntimeRequest(
        prompt="分析一下这个计划",
        energy=90.0,
        task_complexity=1,
        allowed_tools=(),
        metadata=(("task_type", "reasoning"),),
    )

    def fake_generate(**kwargs):
        assert kwargs["model_key"] == "remote_deep"
        return "分析结果"

    agent.generate = fake_generate

    result = agent.think(request)

    assert result.text == "分析结果"
    assert result.model_key == "remote_deep"
    assert result.decision["food_policy"]["task_type"] == "reasoning"
    assert result.decision["food_policy"]["group_key"] == "premium"
