"""Commands, queries and results owned by Adoption."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

from elfie.genesis import CandidateReveal, GenesisCandidate

SpeciesId = str
LifeStage = Literal["youth", "young_adult", "mature", "elder", "any"]
CandidateGender = Literal["male", "female", "any"]
ElfieGender = Literal["male", "female"]
CandidateReplyStatus = Literal["accepted", "unsure"]
AdoptionAvailability = Literal[
    "available", "nest_full", "member_quota_full", "model_unavailable"
]


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
class AdoptionNestCapacity:
    used: int
    maximum: int
    remaining: int


@dataclass(frozen=True)
class AdoptionSpecies:
    """Stable metadata projected from the immutable species registry."""

    species_id: SpeciesId
    canon_id: str
    display_name: str
    display_name_zh: str
    earth_shape_label: str
    scene_id: str
    sort_order: int


@dataclass(frozen=True)
class AdoptionOptionsResult:
    personality_styles: tuple[str, ...]
    species: tuple[AdoptionSpecies, ...]
    heights: tuple[str, ...]
    builds: tuple[str, ...]
    life_stages: tuple[LifeStage, ...]
    quota: AdoptionQuota
    nest_capacity: AdoptionNestCapacity
    availability: AdoptionAvailability


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
    batch_number: int = 1
    adoption_session_id: Optional[str] = None


@dataclass(frozen=True)
class CandidateResult:
    candidate_id: str
    species_id: SpeciesId
    life_stage: ExposedLifeStage
    age_months: int
    gender: ElfieGender
    full_body_image_url: str
    headshot_image_url: str
    appearance_tags: tuple[str, ...]
    personality_tags: tuple[str, ...]
    runtime_appearance: dict[str, object] = field(default_factory=dict)


ExposedLifeStage = Literal["youth", "young_adult", "mature", "elder"]


@dataclass(frozen=True)
class CandidateSetResult:
    candidate_set_id: str
    adoption_session_id: str
    batch_number: int
    candidates: tuple[CandidateResult, ...]


@dataclass(frozen=True)
class ReplyToCandidatesCommand:
    candidate_set_id: str
    candidate_ids: tuple[str, ...]
    invitation_message: str = ""


@dataclass(frozen=True)
class CandidateReplyResult:
    candidate: CandidateResult
    status: CandidateReplyStatus
    message: str
    reveal: Optional[CandidateReveal] = None


@dataclass(frozen=True)
class CandidateRepliesResult:
    candidate_set_id: str
    replies: tuple[CandidateReplyResult, ...]


@dataclass(frozen=True)
class ReserveAcceptedAdoptionCommand:
    candidate_set_id: str
    candidate_id: str
    name: str
    full_body_image_url: str = ""
    headshot_image_url: str = ""


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
    original_name: str = ""
    genesis_candidate: Optional[GenesisCandidate] = None
    personal_story: str = ""
    age_months: int = 0
    life_stage: str = ""
    full_body_image_url: str = ""
    headshot_image_url: str = ""


__all__ = (
    "AcceptedAdoptionReservation",
    "AdoptionSpecies",
    "AdoptionOptionsResult",
    "AdoptionAvailability",
    "AdoptionNestCapacity",
    "AdoptionQuota",
    "CandidateAppearance",
    "CandidateGender",
    "CandidateRepliesResult",
    "CandidateReplyResult",
    "CandidateReplyStatus",
    "CandidateReveal",
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
