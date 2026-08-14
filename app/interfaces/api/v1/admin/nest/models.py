"""Strict HTTP DTOs for the administrator Nest resource."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.features.nest_management import (
    NestBed,
    NestBedAssignment,
    NestConfiguration,
    NestRoom,
)


class NestBedCountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bed_count: int = Field(strict=True)


class NestBedAssignmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    home_anchor_id: Optional[str] = Field(
        default=None,
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$",
    )


class NestBedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    anchor_id: str
    kind: str
    label: str
    order: int
    active: bool
    occupant_id: Optional[str]
    occupant_name: Optional[str]
    occupant_owner_user_id: Optional[int]
    occupant_species_id: Optional[str]
    occupant_owner_account_id: Optional[str]
    occupant_owner_display_name: Optional[str]

    @classmethod
    def from_result(cls, bed: NestBed) -> NestBedResponse:
        return cls(
            id=bed.anchor_id,
            anchor_id=bed.anchor_id,
            kind="bed",
            label=bed.label,
            order=bed.order,
            active=True,
            occupant_id=bed.occupant_id,
            occupant_name=bed.occupant_name,
            occupant_owner_user_id=bed.occupant_owner_user_id,
            occupant_species_id=bed.occupant_species_id,
            occupant_owner_account_id=bed.occupant_owner_account_id,
            occupant_owner_display_name=bed.occupant_owner_display_name,
        )


class NestRoomResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    desired_bed_count: int
    applied_world_revision: Optional[int]
    beds: tuple[NestBedResponse, ...]

    @classmethod
    def from_result(cls, room: NestRoom) -> NestRoomResponse:
        return cls(
            id=room.nest_id,
            name=room.name,
            desired_bed_count=room.desired_bed_count,
            applied_world_revision=room.applied_world_revision,
            beds=tuple(NestBedResponse.from_result(bed) for bed in room.beds),
        )


class NestRoomsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: tuple[NestRoomResponse, ...]


class NestConfigurationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    desired_bed_count: int
    applied_world_revision: Optional[int]

    @classmethod
    def from_result(
        cls,
        configuration: NestConfiguration,
    ) -> NestConfigurationResponse:
        return cls(
            desired_bed_count=configuration.desired_bed_count,
            applied_world_revision=configuration.applied_world_revision,
        )


class NestBedAssignmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: str
    elfie_id: str
    home_anchor_id: Optional[str]

    @classmethod
    def from_result(
        cls,
        assignment: NestBedAssignment,
    ) -> NestBedAssignmentResponse:
        return cls(
            detail="Home assigned",
            elfie_id=assignment.elfie_id,
            home_anchor_id=assignment.home_anchor_id,
        )


class NestErrorDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NestErrorItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: NestErrorDetails


class NestErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: NestErrorItem


__all__ = (
    "NestBedAssignmentRequest",
    "NestBedAssignmentResponse",
    "NestBedCountRequest",
    "NestBedResponse",
    "NestConfigurationResponse",
    "NestErrorDetails",
    "NestErrorItem",
    "NestErrorResponse",
    "NestRoomResponse",
    "NestRoomsResponse",
)
