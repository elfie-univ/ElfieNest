"""Strict HTTP DTOs for the administrator Runtime projection."""

from __future__ import annotations

from typing import Dict, Literal, Optional, Tuple, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
)

_STRICT = ConfigDict(extra="forbid", frozen=True)
ModelExecutionMetadataValue = Union[StrictStr, StrictBool, StrictInt, StrictFloat]


class ModelExecutionEventResponse(BaseModel):
    model_config = _STRICT

    event_type: Literal[
        "model_call",
        "tool_call",
        "permission_decision",
        "fallback",
        "provider_verify",
        "food_decision",
    ]
    status: Literal["ok", "error"]
    subject: StrictStr
    metadata: Dict[StrictStr, ModelExecutionMetadataValue]


class ModelExecutionObserverResponse(BaseModel):
    model_config = _STRICT

    event_count: StrictInt
    last_event: Optional[ModelExecutionEventResponse]


class RuntimeLifecycleComponentResponse(BaseModel):
    model_config = _STRICT

    component: StrictStr
    state: StrictStr
    detail: StrictStr
    pid: Optional[StrictInt]
    executable: Optional[StrictStr]
    birth_identity: Optional[StrictStr]


class RuntimeLifecycleEndpointResponse(BaseModel):
    model_config = _STRICT

    name: StrictStr
    scheme: StrictStr
    host: StrictStr
    port: StrictInt
    protocol_version: StrictStr


class RuntimeLifecycleFailureResponse(BaseModel):
    model_config = _STRICT

    code: StrictStr
    detail: StrictStr
    phase: StrictStr


class RuntimeLifecycleTimingResponse(BaseModel):
    model_config = _STRICT

    phase: StrictStr
    duration_ms: Optional[StrictInt]
    elapsed_ms: Optional[StrictInt]


class RuntimeLifecycleProjectionResponse(BaseModel):
    """The sanitized, versioned lifecycle projection used by status surfaces."""

    model_config = _STRICT

    schema_version: StrictInt
    instance_id: StrictStr
    generation: StrictInt
    revision: StrictInt
    tier: StrictStr
    phase: StrictStr
    subphase: StrictStr
    desired_target: StrictStr
    reached_target: Optional[StrictStr]
    components: Tuple[RuntimeLifecycleComponentResponse, ...]
    endpoints: Tuple[RuntimeLifecycleEndpointResponse, ...]
    model_state: StrictStr
    model_common_state: StrictStr
    model_emergency_state: StrictStr
    model_revision: Optional[StrictInt]
    failures: Tuple[RuntimeLifecycleFailureResponse, ...]
    timings: Tuple[RuntimeLifecycleTimingResponse, ...]
    protocol_versions: Tuple[StrictStr, ...]


class RuntimeStatusResponse(BaseModel):
    model_config = _STRICT

    status: Literal["ok"]
    observer: ModelExecutionObserverResponse
    lifecycle: Optional[RuntimeLifecycleProjectionResponse] = None


class MobileAccessResponse(BaseModel):
    model_config = _STRICT

    available: StrictBool
    network_name: Optional[StrictStr]
    urls: Tuple[StrictStr, ...]


class RuntimeErrorDetails(BaseModel):
    model_config = _STRICT


class RuntimeErrorItem(BaseModel):
    model_config = _STRICT

    code: StrictStr
    message: StrictStr
    details: RuntimeErrorDetails


class RuntimeErrorResponse(BaseModel):
    model_config = _STRICT

    error: RuntimeErrorItem


__all__ = (
    "MobileAccessResponse",
    "RuntimeErrorDetails",
    "RuntimeErrorItem",
    "RuntimeErrorResponse",
    "ModelExecutionEventResponse",
    "ModelExecutionObserverResponse",
    "RuntimeLifecycleProjectionResponse",
    "RuntimeStatusResponse",
)
