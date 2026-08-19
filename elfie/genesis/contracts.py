"""Typed, one-time creation contracts for an Elfie life.

Genesis only validates the hand-off from creation to the long-lived owners. It
does not remain in the runtime and it does not own permissions, devices,
models, channels, or memories after the hand-off.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from elfie.brain.selfhood.contracts import BigFiveTraits, SelfhoodSpeechStyle
from elfie.profile import (
    WORLD_CANON_VERSION,
    AppearanceGenome,
    ElfieProfile,
    get_species_canon_for_technical_id,
)

GenesisStatus = Literal["draft", "validated", "committed"]
MemorySource = Literal["personal_memory", "witnessed", "program_brief"]
MemoryCertainty = Literal["high", "medium", "low"]


class GenesisValidationError(ValueError):
    """Raised when a creation bundle would violate its ownership limits."""


@dataclass(frozen=True)
class ProfileDraft:
    """The immutable Profile candidate produced before the final hand-off."""

    profile: ElfieProfile


@dataclass(frozen=True)
class PersonalitySeed:
    """Initial Selfhood input; ordinary turns cannot rewrite it directly."""

    big_five: BigFiveTraits
    self_description: str
    speech_style: SelfhoodSpeechStyle = SelfhoodSpeechStyle()
    norms: tuple[str, ...] = ()
    behavior_anchors: tuple[str, ...] = ()
    sensory_biases: tuple[str, ...] = ()


@dataclass(frozen=True)
class MemorySeed:
    """One bounded pre-arrival event that Memory may commit."""

    seed_id: str
    content: str
    source: MemorySource
    certainty: MemoryCertainty = "high"
    emotional_tone: str = "calm"
    intensity: float = 0.5


@dataclass(frozen=True)
class RelationshipSeed:
    """A relationship skeleton, not a complete social graph."""

    person_id: str
    display_name: str
    role: str
    initial_trust: float
    shared_facts: tuple[str, ...] = ()
    unknown_facts: tuple[str, ...] = ()


@dataclass(frozen=True)
class SelfModelSeed:
    """Initial self-understanding and explicit knowledge boundaries."""

    identity_summary: str
    known_facts: tuple[str, ...]
    unknown_facts: tuple[str, ...]
    knowledge_scope: tuple[str, ...] = ()
    species_knowledge: tuple[str, ...] = ()


@dataclass(frozen=True)
class BiographyEnrichmentPlan:
    """Temporary, bounded follow-up work for early Night Work only."""

    allowed_memory_seed_ids: tuple[str, ...] = ()
    max_additional_memories: int = 0
    expires_after_events: int = 0


@dataclass(frozen=True)
class InitializationManifest:
    """Creation provenance and validation status retained after hand-off."""

    manifest_id: str
    canon_version: str
    species_version: str
    reference_version: str
    status: GenesisStatus = "draft"
    validation_errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class GenesisBundle:
    """The complete, temporary creation package for one Elfie."""

    profile_draft: ProfileDraft
    personality_seed: PersonalitySeed
    memory_seeds: tuple[MemorySeed, ...]
    relationship_seeds: tuple[RelationshipSeed, ...]
    self_model_seed: SelfModelSeed
    biography_plan: BiographyEnrichmentPlan
    manifest: InitializationManifest

    def validate(self) -> None:
        """Reject an incomplete or over-powered creation package."""
        profile = self.profile_draft.profile
        try:
            profile.validate()
            species = get_species_canon_for_technical_id(profile.identity.species_id)
        except (ValueError, TypeError) as error:
            raise GenesisValidationError(str(error)) from error

        if not self.personality_seed.self_description.strip():
            raise GenesisValidationError("personality_seed.self_description 不能为空")
        if len(self.memory_seeds) > 5:
            raise GenesisValidationError("Genesis 最多只能提供 5 个 MemorySeed")
        _require_unique(
            (seed.seed_id for seed in self.memory_seeds),
            "memory seed_id",
        )
        _require_unique(
            (seed.person_id for seed in self.relationship_seeds),
            "relationship person_id",
        )
        for seed in self.memory_seeds:
            if not seed.seed_id.strip() or not seed.content.strip():
                raise GenesisValidationError("MemorySeed 的 ID 和内容不能为空")
            if not 0.0 <= seed.intensity <= 1.0:
                raise GenesisValidationError("MemorySeed.intensity 必须在 [0, 1] 内")
        for relationship in self.relationship_seeds:
            if (
                not relationship.person_id.strip()
                or not relationship.display_name.strip()
            ):
                raise GenesisValidationError("RelationshipSeed 的身份不能为空")
            if not 0.0 <= relationship.initial_trust <= 1.0:
                raise GenesisValidationError(
                    "RelationshipSeed.initial_trust 必须在 [0, 1] 内"
                )
        if not self.self_model_seed.identity_summary.strip():
            raise GenesisValidationError("self_model_seed.identity_summary 不能为空")
        if not self.self_model_seed.known_facts:
            raise GenesisValidationError("SelfModelSeed 至少需要一个已知事实")
        memory_ids = {seed.seed_id for seed in self.memory_seeds}
        if not set(self.biography_plan.allowed_memory_seed_ids) <= memory_ids:
            raise GenesisValidationError(
                "BiographyEnrichmentPlan 只能引用本次 Genesis 的 MemorySeed"
            )
        if not 0 <= self.biography_plan.max_additional_memories <= 12:
            raise GenesisValidationError(
                "BiographyEnrichmentPlan.max_additional_memories 必须在 [0, 12] 内"
            )
        if self.biography_plan.expires_after_events < 0:
            raise GenesisValidationError(
                "BiographyEnrichmentPlan.expires_after_events 不能为负数"
            )
        if self.manifest.species_version != species.canon_version:
            raise GenesisValidationError(
                "manifest.species_version 与 Profile 物种版本不一致"
            )
        if self.manifest.canon_version != WORLD_CANON_VERSION:
            raise GenesisValidationError(
                "manifest.canon_version 与世界 Canon 版本不一致"
            )
        if (
            not self.manifest.manifest_id.strip()
            or not self.manifest.reference_version.strip()
        ):
            raise GenesisValidationError("InitializationManifest 的身份字段不能为空")
        if (
            self.manifest.status in ("validated", "committed")
            and self.manifest.validation_errors
        ):
            raise GenesisValidationError(
                "已校验或已提交的 InitializationManifest 不能保留 validation_errors"
            )


def validate_genesis_bundle(bundle: GenesisBundle) -> GenesisBundle:
    """Validate and return the same immutable bundle for fluent hand-off code."""
    bundle.validate()
    return bundle


def _require_unique(values: Iterable[str], label: str) -> None:
    items = tuple(values)
    if len(set(items)) != len(items):
        raise GenesisValidationError(f"{label} 必须唯一")


# Candidate-generation contracts are kept beside the one-time hand-off
# contracts because both stages share the same immutable Genesis boundary.
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
    """A candidate batch cannot satisfy the Genesis generation contract."""


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
    visual_key: tuple[str, ...] = ()


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
    "BiographyEnrichmentPlan",
    "BIG_FIVE_TRAITS",
    "CANDIDATE_ROLES",
    "CandidateReveal",
    "CandidateSignature",
    "GenesisBundle",
    "GenesisAppearanceIntent",
    "GenesisBatch",
    "GenesisCandidate",
    "GenesisStatus",
    "GenesisError",
    "GenesisPersonality",
    "GenesisValidationError",
    "BigFiveProfile",
    "STAGE_PLASTICITY",
    "InitializationManifest",
    "MemoryCertainty",
    "MemorySeed",
    "MemorySource",
    "PersonalitySeed",
    "ProfileDraft",
    "RelationshipSeed",
    "SelfModelSeed",
    "validate_genesis_bundle",
)
