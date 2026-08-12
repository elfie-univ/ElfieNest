"""Strict HTTP DTOs for the current member's Adoption resource."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.features.adoption import (
    AdoptionOptionsResult,
    CandidateRepliesResult,
    CandidateReplyResult,
    CandidateResult,
    CandidateSetResult,
)
from app.orchestration.resident_admission import ResidentAdmissionResult


class CandidateAppearanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stature: Literal["small", "standard", "tall", "any"]
    build: Literal["slim", "standard", "round", "any"]
    face: Literal["soft", "balanced", "defined", "any"]
    signature: Literal["warm", "marked", "ears", "any"]
    priority: Literal["stature", "build", "face", "signature"]


class CandidateSetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    species_id: Literal["dog", "fox"]
    life_stage: Literal["youth", "young_adult", "mature", "elder", "any"]
    gender: Literal["male", "female", "any"]
    appearance: CandidateAppearanceRequest
    answers: tuple[str, ...] = Field(min_length=5, max_length=5)

    @field_validator("answers")
    @classmethod
    def answers_are_not_empty(cls, answers: tuple[str, ...]) -> tuple[str, ...]:
        if any(not answer for answer in answers):
            raise ValueError("answers must not contain empty values")
        return answers


class CandidateRepliesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_ids: tuple[str, ...] = Field(min_length=1, max_length=3)

    @field_validator("candidate_ids")
    @classmethod
    def candidate_ids_are_unique(
        cls,
        candidate_ids: tuple[str, ...],
    ) -> tuple[str, ...]:
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("candidate_ids must be unique")
        return candidate_ids


class AdoptionCommitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_set_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=20)


class AdoptionQuotaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    used: int
    max: int
    remaining: int
    can_adopt: bool


class AdoptionOptionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    personality_styles: tuple[str, ...]
    species_ids: tuple[Literal["dog", "fox"], ...]
    heights: tuple[str, ...]
    builds: tuple[str, ...]
    life_stages: tuple[str, ...]
    quota: AdoptionQuotaResponse

    @classmethod
    def from_result(cls, result: AdoptionOptionsResult) -> AdoptionOptionsResponse:
        return cls(
            personality_styles=result.personality_styles,
            species_ids=result.species_ids,
            heights=result.heights,
            builds=result.builds,
            life_stages=result.life_stages,
            quota=AdoptionQuotaResponse(
                used=result.quota.used,
                max=result.quota.maximum,
                remaining=result.quota.remaining,
                can_adopt=result.quota.can_adopt,
            ),
        )


class AdoptionCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    original_name: str
    suggested_name: str
    species_id: Literal["dog", "fox"]
    life_stage: Literal["youth", "young_adult", "mature", "elder"]
    gender: Literal["male", "female"]
    image_url: str
    appearance_tags: tuple[str, ...]
    personality_tags: tuple[str, ...]
    introduction: str
    compatibility: str

    @classmethod
    def from_result(cls, result: CandidateResult) -> AdoptionCandidateResponse:
        return cls(**result.__dict__)


class CandidateSetResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_set_id: str
    candidates: tuple[AdoptionCandidateResponse, ...]

    @classmethod
    def from_result(cls, result: CandidateSetResult) -> CandidateSetResponse:
        return cls(
            candidate_set_id=result.candidate_set_id,
            candidates=tuple(
                AdoptionCandidateResponse.from_result(candidate)
                for candidate in result.candidates
            ),
        )


class CandidateReplyResponse(AdoptionCandidateResponse):
    status: Literal["accepted", "unsure"]
    message: str

    @classmethod
    def from_reply(cls, result: CandidateReplyResult) -> CandidateReplyResponse:
        return cls(
            **result.candidate.__dict__,
            status=result.status,
            message=result.message,
        )


class CandidateRepliesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_set_id: str
    replies: tuple[CandidateReplyResponse, ...]

    @classmethod
    def from_result(cls, result: CandidateRepliesResult) -> CandidateRepliesResponse:
        return cls(
            candidate_set_id=result.candidate_set_id,
            replies=tuple(
                CandidateReplyResponse.from_reply(reply) for reply in result.replies
            ),
        )


class AdoptionResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    elfie_id: str = Field(pattern=r"^[0-9]{8}$")
    name: str
    species_id: Literal["dog", "fox"]

    @classmethod
    def from_result(cls, result: ResidentAdmissionResult) -> AdoptionResultResponse:
        return cls(
            elfie_id=result.elfie_id,
            name=result.name,
            species_id=result.species_id,
        )


class AdoptionErrorDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: Optional[int] = None


class AdoptionErrorItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: AdoptionErrorDetails


class AdoptionErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: AdoptionErrorItem


__all__ = (
    "AdoptionCandidateResponse",
    "AdoptionCommitRequest",
    "AdoptionErrorDetails",
    "AdoptionErrorItem",
    "AdoptionErrorResponse",
    "AdoptionOptionsResponse",
    "AdoptionResultResponse",
    "CandidateAppearanceRequest",
    "CandidateRepliesRequest",
    "CandidateRepliesResponse",
    "CandidateReplyResponse",
    "CandidateSetRequest",
    "CandidateSetResponse",
)
