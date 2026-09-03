from elfie.brain.reasoning.tool_port import ToolCall
from infrastructure.models.inference.llm_api import LLMCallResult
from infrastructure.models.validation.agent_validation import ModelAgentValidationRunner
from infrastructure.models.validation.validation_models import CheckStatus
from test.support.model_execution import model_execution_config


def _runner(config, **kwargs):
    from app.bootstrap.system_wiring.model_execution import (
        build_agent_validation_composition,
    )

    composition = build_agent_validation_composition()
    return ModelAgentValidationRunner(
        config,
        tool_port_factory=composition.tool_port_factory,
        **kwargs,
    )


def scripted_model(provider, model, messages, temperature, max_tokens, options):
    del provider, model, temperature, max_tokens
    assert options["tool_definitions"][0]["function"]["name"] == "local_file"
    if len(messages) == 1:
        return LLMCallResult(
            text="",
            usage={},
            metadata={},
            tool_calls=(
                ToolCall(
                    call_id="call-local-file",
                    tool_key="local_file",
                    arguments={
                        "operation": "read",
                        "resource_id": "probe.txt",
                    },
                ),
            ),
        )
    assert messages[-1]["role"] == "tool"
    assert "ELFIE_LOCAL_FILE_OK" in messages[-1]["content"]
    return LLMCallResult(text="工具结果已收到，最终回答完成。", usage={}, metadata={})


def test_model_agent_runner_proves_native_tool_protocol_with_deterministic_model(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    runner = _runner(model_execution_config(), model_caller=scripted_model)

    suite = runner.verify("fake", "model")

    assert suite.passed is True
    assert {result.status for result in suite.results} == {CheckStatus.PASSED}
    assert all(result.details["tool_called"] for result in suite.results)
    assert all(result.details["observation_received"] for result in suite.results)


def test_model_agent_runner_rejects_text_marker_or_plain_text_model(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    runner = _runner(
        model_execution_config(),
        model_caller=lambda *args: "[READ_FILE]probe.txt[/READ_FILE]",
    )

    result = runner.verify_tool("fake", "model", "local_file")

    assert result.status is CheckStatus.FAILED
    assert result.details["tool_called"] is False


def test_model_agent_runner_exposes_each_default_provider_trace(monkeypatch, tmp_path):
    from infrastructure.models.inference.llm_api import API_DISPATCH

    def fake_dispatch(
        api_base,
        api_key,
        model_name,
        messages,
        temperature,
        max_tokens,
        provider,
        *,
        request_options=None,
        response_capture=None,
        return_metadata=False,
    ):
        del api_base, api_key, model_name, temperature, max_tokens, provider
        assert request_options["tools"][0]["function"]["name"] == "local_file"
        if len(messages) == 1:
            response = (
                "",
                {},
                {
                    "tool_called": True,
                    "tool_calls": [
                        {
                            "call_id": "call-trace",
                            "name": "local_file",
                            "arguments": {
                                "operation": "read",
                                "resource_id": "probe.txt",
                            },
                        }
                    ],
                },
            )
        else:
            response = ("trace final", {}, {})
        return response if return_metadata else response[:2]

    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    monkeypatch.setitem(API_DISPATCH, "chat_completions", fake_dispatch)
    config = model_execution_config()
    config.providers["fake"] = {
        "api_base": "https://api.fake.test",
        "api_key": "",
        "api_mode": "chat_completions",
    }
    runner = _runner(config)

    result = runner.verify_tool("fake", "model", "local_file")

    assert result.status is CheckStatus.PASSED
    assert len(runner.traces) == 2
    assert runner.traces[0]["request"]["messages"][0]["content"]
    assert runner.traces[0]["response"]["metadata"]["tool_called"] is True
    assert runner.traces[1]["response"]["text"] == "trace final"
