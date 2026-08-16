from __future__ import annotations

from infrastructure.models.validation.provider_capability_probes import (
    CapabilityProbeResponse,
    run_capability_probe,
)
from test.support.model_execution import model_execution_config


def test_tool_probe_requires_an_observed_local_tool_call() -> None:
    calls: list[dict[str, object]] = []

    def caller(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return CapabilityProbeResponse(
            text="",
            metadata={"tool_called": True},
        )

    result = run_capability_probe(
        model_execution_config(),
        "openai_api_0001",
        "gpt-test",
        "tools",
        model_caller=caller,
    )

    assert result.state == "supported"
    assert result.evidence == "verified"
    assert calls[0]["kwargs"]["request_options"]["tool_definitions"]


def test_vision_probe_does_not_promote_plain_text_to_verified() -> None:
    def caller(*args, **kwargs):
        return CapabilityProbeResponse(text="OK", metadata={})

    result = run_capability_probe(
        model_execution_config(),
        "openai_api_0001",
        "gpt-test",
        "vision",
        model_caller=caller,
    )

    assert result.state == "supported"
    assert result.evidence == "accepted"


def test_structured_probe_requires_parseable_json() -> None:
    result = run_capability_probe(
        model_execution_config(),
        "openai_api_0001",
        "gpt-test",
        "structured_output",
        model_caller=lambda *args, **kwargs: CapabilityProbeResponse(
            text="not json", metadata={}
        ),
    )

    assert result.state == "unsupported"
    assert result.evidence == "verified"
