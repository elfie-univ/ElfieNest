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


class RuntimeStatusResponse(BaseModel):
    model_config = _STRICT

    status: Literal["ok"]
    observer: ModelExecutionObserverResponse


class MobileAccessResponse(BaseModel):
    model_config = _STRICT

    available: StrictBool
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
    "RuntimeStatusResponse",
)
