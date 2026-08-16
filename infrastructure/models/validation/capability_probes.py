"""Side-effect-free, channel-specific model capability probes."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Literal, Mapping

from infrastructure.models.provider_records import ProviderModelRecord
from infrastructure.models.providers.endpoint_capabilities import (
    CapabilityEvidence,
    CapabilityName,
    EndpointCapability,
    endpoint_capabilities,
)
from infrastructure.models.report_records import ValidationObservation

CapabilityState = Literal["supported", "unsupported", "unknown"]

_VISION_PIXEL = base64.b64encode(
    bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cf00000004000101a2a0ed0000000049454e44ae426082")
).decode("ascii")


@dataclass(frozen=True)
class CapabilityProbeRequest:
    messages: list[dict[str, Any]]
    request_options: dict[str, Any]
    thinking: bool = False


@dataclass(frozen=True)
class CapabilityProbeResult:
    capability: CapabilityName
    state: CapabilityState
    evidence: CapabilityEvidence
    reason_code: str
    details: Mapping[str, Any]


def capability_probe_request(
    capability: CapabilityName,
    *,
    api_mode: str,
) -> CapabilityProbeRequest:
    """Build one bounded request using semantic options, not wire payloads."""

    if capability == "tools":
        return CapabilityProbeRequest(
            messages=[
                {
                    "role": "user",
                    "content": "Call the local no-op function exactly once; do not call any external action.",
                }
            ],
            request_options={
                "tool_definitions": [
                    {
                        "type": "function",
                        "function": {
                            "name": "elfienest_probe_noop",
                            "description": "A local capability probe with no side effect.",
                            "parameters": {
                                "type": "object",
                                "properties": {},
                                "additionalProperties": False,
                            },
                        },
                    }
                ],
                "tool_choice": {
                    "type": "function",
                    "function": {"name": "elfienest_probe_noop"},
                },
            },
        )
    if capability == "vision":
        return CapabilityProbeRequest(
            messages=[{"role": "user", "content": _vision_content(api_mode)}],
            request_options={},
        )
    if capability == "reasoning":
        return CapabilityProbeRequest(
            messages=[
                {
                    "role": "user",
                    "content": "Return exactly the word ELFIENEST_REASONING_OK.",
                }
            ],
            request_options={"reasoning_mode": "low"},
            thinking=True,
        )
    if capability == "structured_output":
        return CapabilityProbeRequest(
            messages=[
                {
                    "role": "user",
                    "content": "Return the requested JSON object and no other text.",
                }
            ],
            request_options={
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "elfienest_probe",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {"probe": {"const": "ok"}},
                            "required": ["probe"],
                            "additionalProperties": False,
                        },
                    },
                }
            },
        )
    raise ValueError(f"unknown model capability: {capability}")


def evaluate_capability_probe(
    capability: CapabilityName,
    response_text: str,
    response_metadata: Mapping[str, Any],
) -> CapabilityProbeResult:
    """Promote evidence only when the response proves the requested channel."""

    if capability == "tools":
        count = response_metadata.get("tool_call_count")
        if isinstance(count, int) and count > 0:
            return _verified(capability, "tool_call_observed", tool_call_count=count)
        return _unknown(capability, "tool_call_not_observed")
    if capability == "vision":
        if "ELFIENEST_VISION_OK" in response_text:
            return _verified(capability, "vision_marker_observed")
        return _unknown(capability, "vision_marker_not_observed")
    if capability == "reasoning":
        if response_metadata.get("reasoning_present") is True:
            return _verified(capability, "reasoning_trace_observed")
        return _unknown(capability, "reasoning_trace_not_observed")
    if capability == "structured_output":
        try:
            decoded = json.loads(response_text.strip())
        except (TypeError, ValueError):
            decoded = None
        if isinstance(decoded, dict) and decoded.get("probe") == "ok":
            return _verified(capability, "structured_json_observed")
        return _unknown(capability, "structured_json_not_observed")
    raise ValueError(f"unknown model capability: {capability}")


def capability_error_result(
    capability: CapabilityName,
    error_code: str,
) -> CapabilityProbeResult:
    """Map a typed Provider rejection without widening it to model health."""

    unsupported = {
        "invalid_request",
        "tool_not_supported",
        "vision_not_supported",
        "reasoning_not_supported",
        "structured_output_not_supported",
        "unsupported_capability",
    }
    if error_code in unsupported:
        return CapabilityProbeResult(
            capability,
            "unsupported",
            "verified",
            error_code,
            {"verified": True, "provider_rejected_channel": True},
        )
    return CapabilityProbeResult(
        capability,
        "unknown",
        "unknown",
        error_code or "capability_probe_failed",
        {"verified": False},
    )


def project_endpoint_capabilities(
    model: ProviderModelRecord,
    observations: tuple[ValidationObservation, ...],
    *,
    config_fingerprint: str | None = None,
) -> tuple[EndpointCapability, ...]:
    """Overlay verified channel observations on stable endpoint declarations."""

    projected = {item.name: item for item in endpoint_capabilities(model)}
    seen_capabilities: set[str] = set()
    for observation in sorted(
        observations,
        key=lambda item: (item.observed_at, item.observation_id),
        reverse=True,
    ):
        if observation.details.get("evidence_kind") != "capability":
            continue
        if (
            config_fingerprint is not None
            and observation.details.get("config_fingerprint")
            not in {None, config_fingerprint}
        ):
            continue
        raw_name = observation.details.get("capability")
        raw_state = observation.details.get("capability_state")
        raw_evidence = observation.details.get("capability_evidence")
        if (
            not isinstance(raw_name, str)
            or raw_name not in projected
            or not isinstance(raw_state, str)
            or raw_state not in {"supported", "unsupported", "unknown"}
            or not isinstance(raw_evidence, str)
            or raw_evidence not in {"accepted", "verified", "unknown"}
        ):
            continue
        # Observations are newest first.  Once a valid record for a channel
        # has been considered, older records must not resurrect stale health.
        if raw_name in seen_capabilities:
            continue
        seen_capabilities.add(raw_name)
        if projected[raw_name].evidence in {"verified", "accepted"}:
            continue
        projected[raw_name] = EndpointCapability(
            raw_name,
            raw_state,
            raw_evidence,
        )
    return tuple(projected[name] for name in ("tools", "vision", "reasoning", "structured_output"))


def _vision_content(api_mode: str) -> Any:
    prompt = "Inspect the image and return exactly ELFIENEST_VISION_OK if you can read it."
    if api_mode == "anthropic_messages":
        return [
            {"type": "text", "text": prompt},
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": _VISION_PIXEL,
                },
            },
        ]
    if api_mode == "ollama":
        return prompt
    if api_mode == "codex_responses":
        return [
            {"type": "input_text", "text": prompt},
            {"type": "input_image", "image_url": f"data:image/png;base64,{_VISION_PIXEL}"},
        ]
    return [
        {"type": "text", "text": prompt},
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{_VISION_PIXEL}"},
        },
    ]


def _verified(capability: CapabilityName, reason: str, **details: Any) -> CapabilityProbeResult:
    return CapabilityProbeResult(
        capability,
        "supported",
        "verified",
        reason,
        {"verified": True, **details},
    )


def _unknown(capability: CapabilityName, reason: str) -> CapabilityProbeResult:
    return CapabilityProbeResult(
        capability,
        "unknown",
        "unknown",
        reason,
        {"verified": False},
    )


__all__ = (
    "CapabilityProbeRequest",
    "CapabilityProbeResult",
    "capability_error_result",
    "capability_probe_request",
    "evaluate_capability_probe",
    "project_endpoint_capabilities",
)
