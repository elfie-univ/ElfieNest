"""Strict response contract for the unversioned process health probe."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, StrictStr


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ok"]
    engine_ready: StrictBool
    godot_web_ready: StrictBool
    godot_runtime_ready: StrictBool
    instance_id: StrictStr = "unavailable"
    generation: StrictInt = 0


__all__ = ("HealthResponse",)
