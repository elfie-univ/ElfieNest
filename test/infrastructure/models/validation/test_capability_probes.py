from __future__ import annotations

from infrastructure.models.provider_records import ProviderModelRecord
from infrastructure.models.report_records import ValidationObservation
from infrastructure.models.validation.capability_probes import (
    capability_error_result,
    capability_probe_request,
    evaluate_capability_probe,
    project_endpoint_capabilities,
)


def _observation(details: dict[str, object]) -> ValidationObservation:
    return ValidationObservation(
        observation_id=1,
        run_id="run-1",
        subject_kind="model",
        subject_id="cloud/model",
        observed_at="2026-08-15T12:00:00+00:00",
        status="passed",
        latency_ms=10.0,
        time_to_first_token_ms=None,
        error_category=None,
        error_message=None,
        details=details,
    )


def test_capability_evaluation_requires_channel_specific_evidence() -> None:
    tools = evaluate_capability_probe("tools", "", {"tool_call_count": 1})
    vision = evaluate_capability_probe("vision", "ELFIENEST_VISION_OK", {})
    reasoning = evaluate_capability_probe(
        "reasoning", "ELFIENEST_REASONING_OK", {"reasoning_present": False}
    )

    assert tools.evidence == "verified"
    assert vision.state == "supported"
    assert reasoning.state == "unknown"


def test_provider_rejection_is_verified_unsupported_but_network_failure_unknown() -> (
    None
):
    unsupported = capability_error_result("tools", "invalid_request")
    unknown = capability_error_result("tools", "network_error")

    assert unsupported.state == "unsupported"
    assert unsupported.evidence == "verified"
    assert unknown.state == "unknown"


def test_projection_overlays_reported_probe_without_promoting_text_success() -> None:
    model = ProviderModelRecord("model", source="manual")
    observations = (
        _observation(
            {
                "evidence_kind": "capability",
                "capability": "tools",
                "capability_state": "supported",
                "capability_evidence": "verified",
            }
        ),
    )

    capabilities = project_endpoint_capabilities(model, observations)
    tools = next(item for item in capabilities if item.name == "tools")
    vision = next(item for item in capabilities if item.name == "vision")

    assert (tools.state, tools.evidence) == ("supported", "verified")
    assert vision.state == "unknown"


def test_probe_request_uses_semantic_options_and_provider_vision_shape() -> None:
    tools = capability_probe_request("tools", api_mode="chat_completions")
    vision = capability_probe_request("vision", api_mode="anthropic_messages")

    assert "tool_definitions" in tools.request_options
    assert tools.request_options["tool_definitions"][0]["function"]["name"] == (
        "elfienest_probe_noop"
    )
    assert vision.messages[0]["content"][1]["type"] == "image"


def test_projection_ignores_malformed_capability_values() -> None:
    model = ProviderModelRecord("model", source="manual")
    capabilities = project_endpoint_capabilities(
        model,
        (
            _observation(
                {
                    "evidence_kind": "capability",
                    "capability": "tools",
                    "capability_state": [],
                    "capability_evidence": {"unexpected": "object"},
                }
            ),
        ),
    )

    tools = next(item for item in capabilities if item.name == "tools")
    assert tools.state == "unknown"


def test_projection_uses_latest_valid_observation_for_each_capability() -> None:
    model = ProviderModelRecord("model", source="manual")
    older = _observation(
        {
            "evidence_kind": "capability",
            "capability": "vision",
            "capability_state": "supported",
            "capability_evidence": "verified",
        }
    )
    newer = ValidationObservation(
        **{
            **older.__dict__,
            "observation_id": 2,
            "observed_at": "2026-08-15T12:00:01+00:00",
            "details": {
                "evidence_kind": "capability",
                "capability": "vision",
                "capability_state": "unknown",
                "capability_evidence": "unknown",
            },
        }
    )

    capabilities = project_endpoint_capabilities(model, (older, newer))
    vision = next(item for item in capabilities if item.name == "vision")

    assert (vision.state, vision.evidence) == ("unknown", "unknown")
