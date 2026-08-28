"""Strict HTTP DTOs for the versioned Observer boundary."""

from __future__ import annotations

from typing import Annotated, Dict, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from app.orchestration.observer import RuntimeMockMotion

_STRICT = ConfigDict(extra="forbid", frozen=True)


class RoomSubscriptionRequest(BaseModel):
    model_config = _STRICT

    kind: Literal["room"]
    room_id: str = Field(min_length=1)
    elfie_id: None = None


class ElfieSubscriptionRequest(BaseModel):
    model_config = _STRICT

    kind: Literal["elfie"]
    elfie_id: str = Field(min_length=1)
    room_id: None = None


ObserverSubscriptionRequest = Annotated[
    Union[RoomSubscriptionRequest, ElfieSubscriptionRequest],
    Field(discriminator="kind"),
]


class OpenObserverSessionRequest(BaseModel):
    model_config = _STRICT

    protocol: Literal[3]
    role: Literal["observer"]
    subscription: ObserverSubscriptionRequest


class OpenObserverSessionResponse(BaseModel):
    model_config = _STRICT

    capability: str = Field(min_length=1)
    idle_timeout_seconds: int = Field(ge=1)


class ObserverInterestRequest(BaseModel):
    model_config = _STRICT

    subscription: ObserverSubscriptionRequest
    visible_entity_ids: Optional[tuple[str, ...]] = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_visible_entity_ids(self) -> ObserverInterestRequest:
        ids = self.visible_entity_ids
        if ids is not None and (not ids or len(ids) != len(set(ids))):
            raise ValueError("visible entity interest must be non-empty and unique")
        return self


class ObserverIntentRequest(BaseModel):
    model_config = _STRICT

    kind: Literal["request_interaction"]
    actor_id: str = Field(min_length=1)
    interaction: Literal["greet", "rest"]


class ObserverIntentAcceptedResponse(BaseModel):
    model_config = _STRICT

    detail: Literal["observer intent accepted"]


class ObserverSubscriptionResponse(BaseModel):
    model_config = _STRICT

    kind: Literal["room", "elfie"]
    room_id: Optional[str]
    elfie_id: Optional[str]


class ObserverEntityResponse(BaseModel):
    model_config = _STRICT

    room_id: str
    zone_id: Optional[str]
    posture: str
    active: bool
    active_command_id: Optional[str]
    species_id: Optional[str]
    appearance: Dict[str, JsonValue]
    home_anchor_id: Optional[str]
    mock_motion: Optional[RuntimeMockMotion] = None


class ObserverEntityPatchResponse(BaseModel):
    model_config = _STRICT

    room_id: Optional[str] = None
    zone_id: Optional[str] = None
    posture: Optional[str] = None
    active: Optional[bool] = None
    active_command_id: Optional[str] = None
    species_id: Optional[str] = None
    appearance: Optional[Dict[str, JsonValue]] = None
    home_anchor_id: Optional[str] = None
    mock_motion: Optional[RuntimeMockMotion] = None

    @model_validator(mode="after")
    def require_changed_field(self) -> ObserverEntityPatchResponse:
        if not self.model_fields_set:
            raise ValueError("observer entity patch must not be empty")
        return self


class ObserverSnapshotResponse(BaseModel):
    model_config = _STRICT

    protocol: Literal[3] = 3
    kind: Literal["snapshot"] = "snapshot"
    generation: int = Field(ge=1)
    sequence: int = Field(ge=1)
    scope: ObserverSubscriptionResponse
    entities: Dict[str, ObserverEntityResponse]
    entity_revisions: Dict[str, int]


class ObserverDeltaResponse(BaseModel):
    model_config = _STRICT

    protocol: Literal[3] = 3
    kind: Literal["delta"] = "delta"
    generation: int = Field(ge=1)
    sequence: int = Field(ge=1)
    scope: ObserverSubscriptionResponse
    entity_id: str = Field(min_length=1)
    entity_revision: int = Field(ge=1)
    patch: ObserverEntityPatchResponse


ObserverFrameResponse = Annotated[
    Union[ObserverSnapshotResponse, ObserverDeltaResponse],
    Field(discriminator="kind"),
]


class ObserverErrorDetails(BaseModel):
    model_config = _STRICT


class ObserverErrorItem(BaseModel):
    model_config = _STRICT

    code: str
    message: str
    details: ObserverErrorDetails


class ObserverErrorResponse(BaseModel):
    model_config = _STRICT

    error: ObserverErrorItem


__all__ = (
    "ElfieSubscriptionRequest",
    "ObserverDeltaResponse",
    "ObserverEntityPatchResponse",
    "ObserverEntityResponse",
    "ObserverErrorDetails",
    "ObserverErrorItem",
    "ObserverErrorResponse",
    "ObserverFrameResponse",
    "ObserverInterestRequest",
    "ObserverIntentAcceptedResponse",
    "ObserverIntentRequest",
    "ObserverSnapshotResponse",
    "ObserverSubscriptionRequest",
    "ObserverSubscriptionResponse",
    "OpenObserverSessionRequest",
    "OpenObserverSessionResponse",
    "RoomSubscriptionRequest",
)
