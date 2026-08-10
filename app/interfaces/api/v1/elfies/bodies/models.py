"""Strict HTTP DTOs for one Elfie's external bodies."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.features.bodies import BodyCredentialResult, BodyResult


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BodyEnrollmentRequest(StrictModel):
    display_name: str = Field(min_length=1, max_length=120)
    body_type: str = Field(min_length=1, max_length=80)


class BodyResponse(StrictModel):
    body_id: str
    display_name: str
    body_type: str
    status: str
    last_heartbeat_at: Optional[float]

    @classmethod
    def from_result(cls, result: BodyResult) -> BodyResponse:
        return cls(
            body_id=result.body_id,
            display_name=result.display_name,
            body_type=result.body_type,
            status=result.status,
            last_heartbeat_at=result.last_heartbeat_at,
        )


class BodiesResponse(StrictModel):
    items: tuple[BodyResponse, ...]


class BodyCredentialResponse(StrictModel):
    body_id: str
    bearer_token: str

    @classmethod
    def from_result(cls, result: BodyCredentialResult) -> BodyCredentialResponse:
        return cls(body_id=result.body_id, bearer_token=result.bearer_token)


class BodyErrorDetails(StrictModel):
    pass


class BodyErrorItem(StrictModel):
    code: str
    message: str
    details: BodyErrorDetails


class BodyErrorResponse(StrictModel):
    error: BodyErrorItem


__all__ = (
    "BodiesResponse",
    "BodyCredentialResponse",
    "BodyEnrollmentRequest",
    "BodyErrorItem",
    "BodyErrorDetails",
    "BodyErrorResponse",
    "BodyResponse",
)
