"""Strict HTTP DTOs for the administrator Runtime projection."""

from __future__ import annotations

from typing import Dict, Literal, Optional, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
)

_STRICT = ConfigDict(extra="forbid", frozen=True)
RuntimeMetadataValue = Union[StrictStr, StrictBool, StrictInt, StrictFloat]


class RuntimeEventResponse(BaseModel):
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
    metadata: Dict[StrictStr, RuntimeMetadataValue]


class RuntimeObserverResponse(BaseModel):
    model_config = _STRICT

    event_count: StrictInt
    last_event: Optional[RuntimeEventResponse]


class RuntimeStatusResponse(BaseModel):
    model_config = _STRICT

    status: Literal["ok"]
    observer: RuntimeObserverResponse


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
    "RuntimeErrorDetails",
    "RuntimeErrorItem",
    "RuntimeErrorResponse",
    "RuntimeEventResponse",
    "RuntimeObserverResponse",
    "RuntimeStatusResponse",
)
