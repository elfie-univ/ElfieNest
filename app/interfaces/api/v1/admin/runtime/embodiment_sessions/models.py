"""Strict HTTP DTOs for the administrator Embodiment-session projection."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, StrictStr

_STRICT = ConfigDict(extra="forbid", frozen=True)


class EmbodimentSessionResponse(BaseModel):
    model_config = _STRICT

    elfie_id: StrictStr
    state: Literal[
        "at_nest",
        "switching_to_hosted",
        "hosted",
        "returning_to_nest",
        "offline",
    ]
    body_id: Optional[StrictStr]


class EmbodimentSessionsResponse(BaseModel):
    model_config = _STRICT

    items: tuple[EmbodimentSessionResponse, ...]


class EmbodimentSessionsErrorDetails(BaseModel):
    model_config = _STRICT


class EmbodimentSessionsErrorItem(BaseModel):
    model_config = _STRICT

    code: StrictStr
    message: StrictStr
    details: EmbodimentSessionsErrorDetails


class EmbodimentSessionsErrorResponse(BaseModel):
    model_config = _STRICT

    error: EmbodimentSessionsErrorItem


__all__ = (
    "EmbodimentSessionResponse",
    "EmbodimentSessionsErrorDetails",
    "EmbodimentSessionsErrorItem",
    "EmbodimentSessionsErrorResponse",
    "EmbodimentSessionsResponse",
)
