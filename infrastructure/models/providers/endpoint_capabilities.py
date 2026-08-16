"""Endpoint-scoped capability facts and evidence levels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from infrastructure.models.provider_records import ProviderModelRecord

CapabilityName = Literal["tools", "vision", "reasoning", "structured_output"]
CapabilityState = Literal["supported", "unsupported", "unknown"]
CapabilityEvidence = Literal[
    "declared",
    "declared_by_user",
    "accepted",
    "verified",
    "unknown",
]


@dataclass(frozen=True)
class EndpointCapability:
    name: CapabilityName
    state: CapabilityState
    evidence: CapabilityEvidence


def endpoint_capabilities(model: ProviderModelRecord) -> tuple[EndpointCapability, ...]:
    """Project only the flags declared for this exact Provider Endpoint."""

    return tuple(
        _capability(model, name, value)
        for name, value in (
            ("tools", model.supports_tools),
            ("vision", model.supports_vision),
            ("reasoning", model.supports_reasoning),
            ("structured_output", model.supports_structured_output),
        )
    )


def _capability(
    model: ProviderModelRecord,
    name: CapabilityName,
    value: bool | None,
) -> EndpointCapability:
    if value is None:
        return EndpointCapability(name, "unknown", "unknown")
    evidence = model.capability_evidence.get(name)
    if evidence is None:
        evidence = "declared_by_user" if model.source == "manual" else "declared"
    return EndpointCapability(
        name,
        "supported" if value else "unsupported",
        evidence,
    )


__all__ = (
    "CapabilityEvidence",
    "CapabilityName",
    "CapabilityState",
    "EndpointCapability",
    "endpoint_capabilities",
)
