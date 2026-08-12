"""Commands, queries and results owned by Adoption."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SpeciesId = Literal["dog", "fox"]
LifeStage = Literal["youth", "young_adult", "mature", "elder", "any"]
CandidateGender = Literal["male", "female", "any"]
ElfieGender = Literal["male", "female"]
CandidateReplyStatus = Literal["accepted", "unsure"]


@dataclass(frozen=True)
class GetAdoptionOptionsQuery:
    pass


@dataclass(frozen=True)
class AdoptionQuota:
    used: int
    maximum: int
    remaining: int
    can_adopt: bool


@dataclass(frozen=True)
class AdoptionOptionsResult:
    personality_styles: tuple[str, ...]
    species_ids: tuple[SpeciesId, ...]
    heights: tuple[str, ...]
    builds: tuple[str, ...]
    life_stages: tuple[LifeStage, ...]
    quota: AdoptionQuota


@dataclass(frozen=True)
class CandidateAppearance:
    stature: str
    build: str
    face: str
    signature: str
    priority: str


@dataclass(frozen=True)
class CreateCandidateSetCommand:
    species_id: SpeciesId
    life_stage: LifeStage
    gender: CandidateGender
    appearance: CandidateAppearance
    answers: tuple[str, ...]


@dataclass(frozen=True)
class CandidateResult:
    candidate_id: str
    original_name: str
    suggested_name: str
    species_id: SpeciesId
    life_stage: ExposedLifeStage
    gender: ElfieGender
    image_url: str
    appearance_tags: tuple[str, ...]
    personality_tags: tuple[str, ...]
    introduction: str
    compatibility: str


ExposedLifeStage = Literal["youth", "young_adult", "mature", "elder"]


@dataclass(frozen=True)
class CandidateSetResult:
    candidate_set_id: str
    candidates: tuple[CandidateResult, ...]


@dataclass(frozen=True)
class ReplyToCandidatesCommand:
    candidate_set_id: str
    candidate_ids: tuple[str, ...]


@dataclass(frozen=True)
class CandidateReplyResult:
    candidate: CandidateResult
    status: CandidateReplyStatus
    message: str


@dataclass(frozen=True)
class CandidateRepliesResult:
    candidate_set_id: str
    replies: tuple[CandidateReplyResult, ...]


@dataclass(frozen=True)
class ReserveAcceptedAdoptionCommand:
    candidate_set_id: str
    candidate_id: str
    name: str


@dataclass(frozen=True)
class AcceptedAdoptionReservation:
    elfie_id: str
    owner_user_id: int
    name: str
    species_id: SpeciesId
    personality_style: str
    height: str
    build: str
    appearance_seed: int
    face: str
    signature: str
    gender: ElfieGender
    birth_date: str


__all__ = (
    "AcceptedAdoptionReservation",
    "AdoptionOptionsResult",
    "AdoptionQuota",
    "CandidateAppearance",
    "CandidateGender",
    "CandidateRepliesResult",
    "CandidateReplyResult",
    "CandidateReplyStatus",
    "CandidateResult",
    "CandidateSetResult",
    "CreateCandidateSetCommand",
    "ElfieGender",
    "ExposedLifeStage",
    "GetAdoptionOptionsQuery",
    "LifeStage",
    "ReplyToCandidatesCommand",
    "ReserveAcceptedAdoptionCommand",
    "SpeciesId",
)
