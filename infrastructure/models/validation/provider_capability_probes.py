"""Small, endpoint-scoped capability probes.

The probe runner deliberately uses the same semantic request options as normal
model execution.  It never executes a returned tool call and it only promotes
an endpoint capability when the response contains evidence that the requested
channel was actually exercised.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Literal, Mapping, Union

from pydantic import JsonValue

from infrastructure.models.inference.llm_api import (
    LLMCallResult,
    call_llm_api_result,
)
from infrastructure.models.model_execution_config import ModelExecutionConfig
from infrastructure.models.provider_errors import classify_provider_error

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
class CapabilityProbeResponse:
    """Transport result used by the probe runner and deterministic tests."""

    text: str
    metadata: Mapping[str, JsonValue]


@dataclass(frozen=True)
class CapabilityProbeResult:
    capability: CapabilityName
    state: CapabilityState
    evidence: CapabilityEvidence
    status: Literal["passed", "failed"]
    latency_ms: float
    error: str | None = None
    error_code: str | None = None
    error_scope: str | None = None
    error_category: str | None = None


ModelCaller = Callable[..., Union[str, CapabilityProbeResponse, LLMCallResult]]

_IMAGE_DATA = base64.b64encode(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010804000000"
        "b51c0c020000000b4944415478da6364f80f000101010018c638d90000000049454e44ae426082"
    )
).decode("ascii")
_CAPABILITIES: tuple[CapabilityName, ...] = (
    "tools",
    "vision",
    "reasoning",
    "structured_output",
)


def run_capability_probe(
    config: ModelExecutionConfig,
    provider_id: str,
    model_name: str,
    capability: CapabilityName,
    *,
    model_caller: ModelCaller = call_llm_api_result,
) -> CapabilityProbeResult:
    """Probe one exact endpoint without executing external side effects."""

    if capability not in _CAPABILITIES:
        raise ValueError(f"不支持的模型能力: {capability}")
    messages, options, thinking = _probe_request(capability)
    started = time.perf_counter()
    try:
        raw = model_caller(
            config,
            provider_id,
            model_name,
            messages,
            0.0,
            32,
            thinking=thinking,
            request_options=options,
        )
        response = _coerce_response(raw)
        latency_ms = (time.perf_counter() - started) * 1000.0
        return _interpret_success(capability, response, latency_ms)
    except Exception as error:
        classification = classify_provider_error(error)
        return CapabilityProbeResult(
            capability=capability,
            state=(
                "unsupported"
                if classification.code
                in {"invalid_request", "tool_schema_invalid", "model_not_entitled"}
                else "unknown"
            ),
            evidence=(
                "verified"
                if classification.code
                in {"invalid_request", "tool_schema_invalid", "model_not_entitled"}
                else "unknown"
            ),
            status="failed",
            latency_ms=(time.perf_counter() - started) * 1000.0,
            error=str(error),
            error_code=classification.code,
            error_scope=classification.scope,
            error_category=classification.category,
        )


def run_capability_probes(
    config: ModelExecutionConfig,
    provider_id: str,
    model_name: str,
    capabilities: tuple[CapabilityName, ...] | None = None,
    *,
    model_caller: ModelCaller = call_llm_api_result,
) -> tuple[CapabilityProbeResult, ...]:
    selected = capabilities or _CAPABILITIES
    if len(selected) > len(_CAPABILITIES):
        raise ValueError("能力探测数量超过上限")
    if len(set(selected)) != len(selected):
        raise ValueError("能力探测不能重复")
    return tuple(
        run_capability_probe(
            config,
            provider_id,
            model_name,
            capability,
            model_caller=model_caller,
        )
        for capability in selected
    )


def _probe_request(
    capability: CapabilityName,
) -> tuple[list[dict[str, Any]], dict[str, Any], bool]:
    if capability == "tools":
        definition = {
            "type": "function",
            "function": {
                "name": "probe_local_noop",
                "description": "A local no-op used only to verify tool calling.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
        }
        return (
            [
                {
                    "role": "user",
                    "content": "Call probe_local_noop once; do not explain.",
                }
            ],
            {"tool_definitions": [definition]},
            False,
        )
    if capability == "vision":
        return (
            [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Describe the image in one word: RED.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{_IMAGE_DATA}"
                            },
                        },
                    ],
                }
            ],
            {},
            False,
        )
    if capability == "reasoning":
        return (
            [
                {
                    "role": "user",
                    "content": "Use the configured reasoning mode, then reply OK.",
                }
            ],
            {"reasoning_mode": "medium"},
            True,
        )
    return (
        [
            {
                "role": "user",
                "content": 'Return exactly JSON matching {"ok":true}.',
            }
        ],
        {"response_format": {"type": "json_object"}},
        False,
    )


def _coerce_response(
    raw: str | CapabilityProbeResponse | LLMCallResult,
) -> CapabilityProbeResponse:
    if isinstance(raw, CapabilityProbeResponse):
        return raw
    if isinstance(raw, LLMCallResult):
        return CapabilityProbeResponse(raw.text, raw.metadata)
    return CapabilityProbeResponse(str(raw), {})


def _interpret_success(
    capability: CapabilityName,
    response: CapabilityProbeResponse,
    latency_ms: float,
) -> CapabilityProbeResult:
    text = response.text.strip()
    metadata = response.metadata
    if capability == "tools":
        verified = metadata.get("tool_called") is True
        return CapabilityProbeResult(
            capability,
            "supported",
            "verified" if verified else "accepted",
            "passed",
            latency_ms,
        )
    if capability == "vision":
        verified = metadata.get("image_observed") is True
        return CapabilityProbeResult(
            capability,
            "supported",
            "verified" if verified else "accepted",
            "passed",
            latency_ms,
        )
    if capability == "reasoning":
        verified = metadata.get("reasoning_observed") is True
        return CapabilityProbeResult(
            capability,
            "supported",
            "verified" if verified else "accepted",
            "passed",
            latency_ms,
        )
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        payload = None
    supported = isinstance(payload, Mapping) and payload.get("ok") is True
    return CapabilityProbeResult(
        capability,
        "supported" if supported else "unsupported",
        "verified",
        "passed" if supported else "failed",
        latency_ms,
        error=None if supported else "结构化输出没有返回可解析的 JSON",
    )


__all__ = (
    "CapabilityProbeResponse",
    "CapabilityProbeResult",
    "run_capability_probe",
    "run_capability_probes",
)
