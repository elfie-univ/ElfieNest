"""Strongly typed records shared by Genesis stages."""

from __future__ import annotations

from dataclasses import dataclass

from elfie.profile import AppearanceGenome

BIG_FIVE_TRAITS = (
    "openness",
    "conscientiousness",
    "extraversion",
    "agreeableness",
    "neuroticism",
)
CANDIDATE_ROLES = (
    "primary_match",
    "appearance_anchor",
    "inner_anchor",
    "balanced_variant",
    "discovery_variant",
)
STAGE_PLASTICITY = {
    "youth": 1.15,
    "young_adult": 1.05,
    "mature": 0.95,
    "elder": 0.85,
}


class GenesisError(ValueError):
    """A candidate batch cannot satisfy the Genesis contract."""


@dataclass(frozen=True)
class CandidateReveal:
    """Identity details disclosed only after a candidate accepts contact."""

    original_name: str
    suggested_name: str
    personal_story: str


@dataclass(frozen=True)
class GenesisAppearanceIntent:
    stature: str
    build: str
    face: str
    signature: str
    priority: str


@dataclass(frozen=True)
class BigFiveProfile:
    latent: tuple[float, ...]
    scores: tuple[int, ...]
    labels: tuple[str, ...]

    def as_mapping(self) -> dict[str, float]:
        return dict(zip(BIG_FIVE_TRAITS, self.latent))


@dataclass(frozen=True)
class GenesisPersonality:
    core: BigFiveProfile
    candidate: BigFiveProfile


@dataclass(frozen=True)
class CandidateSignature:
    personality: tuple[float, ...]
    appearance: tuple[float, ...]


@dataclass(frozen=True)
class GenesisCandidate:
    candidate_id: str
    role: str
    seed: int
    species_id: str
    life_stage: str
    age_months: int
    gender: str
    appearance: AppearanceGenome
    personality: GenesisPersonality
    signature: CandidateSignature


@dataclass(frozen=True)
class GenesisBatch:
    batch_number: int
    candidates: tuple[GenesisCandidate, ...]
    core_personality: BigFiveProfile


__all__ = (
    "BIG_FIVE_TRAITS",
    "CANDIDATE_ROLES",
    "CandidateReveal",
    "STAGE_PLASTICITY",
    "BigFiveProfile",
    "CandidateSignature",
    "GenesisAppearanceIntent",
    "GenesisBatch",
    "GenesisCandidate",
    "GenesisError",
    "GenesisPersonality",
)
