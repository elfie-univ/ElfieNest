from app.bootstrap.system_wiring.model_execution import (
    build_agent_validation_composition,
)
from infrastructure.models.validation.agent_validation import ModelAgentValidationRunner
from infrastructure.models.validation.validation_models import CheckStatus
from test.support.model_execution import model_execution_config


def _runner(config, **kwargs):
    composition = build_agent_validation_composition()
    return ModelAgentValidationRunner(
        config,
        tool_port_factory=composition.tool_port_factory,
        tool_loop_factory=composition.tool_loop_factory,
        prompt_injector=composition.prompt_injector,
        **kwargs,
    )


def scripted_model(provider, model, messages, temperature, max_tokens):
    if len(messages) == 1:
        content = messages[0]["content"]
        if "代码工具" in content:
            return "[CODE]print(123 * 456)[/CODE]"
        return "[READ_FILE]probe.txt[/READ_FILE]"
    return "工具结果已收到，最终回答完成。"


def test_model_agent_runner_proves_model_tool_loop_with_deterministic_model(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    runner = _runner(model_execution_config(), model_caller=scripted_model)

    suite = runner.verify("fake", "model")

    assert suite.passed is True
    assert {result.status for result in suite.results} == {CheckStatus.PASSED}
    assert all(result.details["tool_called"] for result in suite.results)


def test_model_agent_runner_reports_model_that_does_not_call_tools(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    runner = _runner(
        model_execution_config(),
        model_caller=lambda *args: "我直接回答，不调用工具。",
    )

    result = runner.verify_tool("fake", "model", "local_file")

    assert result.status is CheckStatus.FAILED
    assert result.details["tool_called"] is False
