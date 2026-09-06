"""Typed, one-time creation contracts for an Elfie life.

Genesis only validates the hand-off from creation to the long-lived owners. It
does not remain in the runtime and it does not own permissions, devices,
models, channels, or memories after the hand-off.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

from elfie.brain.selfhood.contracts import SelfhoodState
from elfie.profile import (
    AppearanceGenome,
    ElfieProfile,
)

GenesisStatus = Literal["draft", "validated", "committed"]
MemoryCertainty = Literal["high", "medium", "low"]
KnowledgeMastery = Literal["known", "partial", "heard", "unknown"]
KnowledgeLevel = Literal["common", "regional", "specialist", "unknown"]
KnowledgeStatus = Literal["active", "unknown-boundary"]


class GenesisValidationError(ValueError):
    """Raised when a creation bundle would violate its ownership limits."""


@dataclass(frozen=True)
class ProfileDraft:
    """The immutable Profile candidate produced before the final hand-off."""

    profile: ElfieProfile


@dataclass(frozen=True)
class KnowledgeSeed:
    """One published resident-facing fact selected for this Elfie's Memory."""

    seed_id: str
    content: str = ""
    source: str = "genesis_source"
    source_ref: str = "source-package"
    source_version: str = "genesis-source.v1"
    scope: str = "world"
    topic: str = "world"
    aliases: tuple[str, ...] = ()
    retrieval_terms: tuple[str, ...] = ()
    certainty: MemoryCertainty = "high"
    level: KnowledgeLevel = "common"
    mastery: KnowledgeMastery = "known"
    status: KnowledgeStatus = "active"
    eligibility: tuple[str, ...] = ()
    related_ids: tuple[str, ...] = ()
    version: int = 1
    importance: float = 0.5
    # These fields are creation-time decisions.  Memory uses them to build
    # indexes and resolve its own retention policy; they are not replay
    # instructions and must not be copied into the Profile.
    epistemic_kind: str = "documented"
    prerequisite_ids: tuple[str, ...] = ()
    acquired_via: str = "public_exposure"
    acquired_stage: str = ""
    consultable_target_ids: tuple[str, ...] = ()
    confidence_class: str = "high"
    initial_confidence: float = 1.0
    recall_eligible: bool = True


@dataclass(frozen=True)
class EpisodeSeed:
    """One ordered, source-grounded pre-arrival personal experience."""

    seed_id: str
    content: str = ""
    source: str = "personal_memory"
    source_ref: str = "approved-seed:elfaria"
    source_version: str = "genesis-source.v1"
    scope: str = "elfie"
    topic: str = "biography"
    aliases: tuple[str, ...] = ()
    retrieval_terms: tuple[str, ...] = ()
    certainty: MemoryCertainty = "high"
    temporal_label: str = "before_arrival"
    life_stage: str = "youth"
    occurred_from: str | None = None
    occurred_to: str | None = None
    place_ids: tuple[str, ...] = ()
    person_ids: tuple[str, ...] = ()
    result: str = ""
    feeling: str = ""
    impact: str = ""
    predecessor_ids: tuple[str, ...] = ()
    causal_links: tuple[str, ...] = ()
    related_ids: tuple[str, ...] = ()
    emotional_tone: str = "calm"
    emotion_intensity: float = 0.5
    importance: float = 0.5
    version: int = 1
    theme_id: str = ""
    age_years_at_event: int | None = None


@dataclass(frozen=True)
class RelationshipSeed:
    """A relationship skeleton, not a complete social graph."""

    person_id: str
    display_name: str
    role: str
    initial_trust: float
    shared_facts: tuple[str, ...] = ()
    unknown_facts: tuple[str, ...] = ()
    relationship_id: str = ""
    subject_id: str = ""
    object_id: str = ""
    object_kind: Literal["person", "place", "group"] = "person"
    direction: str = "elfie_to_person"
    familiarity: Literal["intimate", "known", "acquainted", "heard"] = "known"
    importance: float = 0.5
    scope: str = "elfie"
    topic: str = "relationship"
    aliases: tuple[str, ...] = ()
    retrieval_terms: tuple[str, ...] = ()
    episode_ids: tuple[str, ...] = ()
    source: str = "approved_seed"
    source_ref: str = "approved-seed:relationship"
    source_version: str = "genesis-source.v1"
    certainty: MemoryCertainty = "high"
    version: int = 1
    related_species_id: str = ""
    age_band_at_genesis: str = ""
    home_place_id: str = ""
    vocation_id: str = ""
    person_species_id: str = ""
    age_years_at_genesis: int | None = None
    competency_ids: tuple[str, ...] = ()
    eligible_episode_theme_ids: tuple[str, ...] = ()

    @property
    def stable_relationship_id(self) -> str:
        return self.relationship_id


@dataclass(frozen=True)
class SelfModelSeed:
    """Initial self-understanding and explicit knowledge boundaries."""

    identity_summary: str
    known_facts: tuple[str, ...]
    unknown_facts: tuple[str, ...]
    knowledge_scope: tuple[str, ...] = ()
    species_knowledge: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    habits: tuple[str, ...] = ()
    preferences: tuple[str, ...] = ()
    emotional_triggers: tuple[str, ...] = ()
    current_goal: str = ""
    earth_adaptation: tuple[str, ...] = ()


@dataclass(frozen=True)
class InitializationManifest:
    """Minimal transient receipt for one creation hand-off.

    Source-package bindings, questionnaire values, generation seeds and input
    inventories remain in the unpublished transaction envelope.  They are not
    part of this object and must not be copied to a final owner.
    """

    manifest_id: str
    status: GenesisStatus = "draft"
    validation_errors: tuple[str, ...] = ()
    compiler_version: str = "genesis-compiler.v0.2"
    schema_version: int = 1
    output_ids: tuple[str, ...] = ()
    content_hash: str = ""
    idempotency_key: str = ""
    committed_at: str | None = None


@dataclass(frozen=True)
class PlaceSeed:
    """A resident-visible place projection selected by Genesis.

    Geometry, population weights and route costs never cross this boundary.
    Private places are namespaced by the owning Elfie and are only used by
    that Elfie's personal Memory.
    """

    place_id: str
    label: str
    kind: str
    parent_id: str = ""
    aliases: tuple[str, ...] = ()
    description: str = ""
    visibility: Literal["public", "private"] = "public"
    source_ref: str = ""


@dataclass(frozen=True)
class GenesisBundle:
    """The complete, temporary creation package for one Elfie."""

    profile_draft: ProfileDraft
    # Canonical two-layer hand-off used by the long-lived Selfhood owner.
    selfhood_state: SelfhoodState | None = None
    relationship_seeds: tuple[RelationshipSeed, ...] = ()
    self_model_seed: SelfModelSeed = field(
        default_factory=lambda: SelfModelSeed(
            identity_summary="",
            known_facts=(),
            unknown_facts=(),
        )
    )
    manifest: InitializationManifest = field(
        default_factory=lambda: InitializationManifest(
            manifest_id="",
        )
    )
    knowledge_seeds: tuple[KnowledgeSeed, ...] = ()
    episode_seeds: tuple[EpisodeSeed, ...] = ()
    place_seeds: tuple[PlaceSeed, ...] = ()

    def validate(self) -> None:
        """Reject an incomplete or over-powered creation package.

        There is one accepted shape: a typed knowledge/relationship/episode
        package plus the resident-visible place projection.  The former
        legacy memory-only submission is intentionally not accepted.
        """
        profile = self.profile_draft.profile
        try:
            profile.validate()
        except (ValueError, TypeError) as error:
            raise GenesisValidationError(str(error)) from error

        selfhood = self.selfhood_state
        if selfhood is None or not selfhood.complete:
            raise GenesisValidationError("Genesis 必须提供完整 SelfhoodState")
        core = selfhood.identity_core
        if core.elfie_id != profile.identity.elfie_id:
            raise GenesisValidationError(
                "Genesis Selfhood 与 Profile 的 Elfie ID 不一致"
            )
        if core.display_name != profile.identity.display_name:
            raise GenesisValidationError("Genesis Selfhood 与 Profile 的名字不一致")
        if core.species_id != profile.identity.species_id:
            raise GenesisValidationError("Genesis Selfhood 与 Profile 的物种不一致")
        if not self.knowledge_seeds:
            raise GenesisValidationError("Genesis 必须提供个人 KnowledgeSeed")
        if not 3 <= len(self.episode_seeds) <= 5:
            raise GenesisValidationError("EpisodeSeed 必须有 3 到 5 段连续经历")
        if not 10 <= len(self.relationship_seeds) <= 20:
            raise GenesisValidationError("Genesis 必须初始化 10 到 20 个关系对象")
        if not self.place_seeds:
            raise GenesisValidationError("Genesis 必须提供个人可见地点投影")

        _require_unique(
            (seed.seed_id for seed in self.knowledge_seeds), "knowledge seed_id"
        )
        _require_unique(
            (seed.seed_id for seed in self.episode_seeds), "episode seed_id"
        )
        _require_unique(
            (seed.stable_relationship_id for seed in self.relationship_seeds),
            "relationship_id",
        )
        _require_unique(
            (seed.person_id for seed in self.relationship_seeds),
            "relationship person_id",
        )
        _require_unique(
            (seed.object_id for seed in self.relationship_seeds),
            "relationship object_id",
        )
        _require_unique((seed.place_id for seed in self.place_seeds), "place_id")
        _require_unique(
            [seed.seed_id for seed in self.knowledge_seeds]
            + [seed.seed_id for seed in self.episode_seeds],
            "Genesis seed_id",
        )

        for seed in self.knowledge_seeds:
            _validate_knowledge_seed(seed)
        episode_ids = {seed.seed_id for seed in self.episode_seeds}
        for index, episode in enumerate(self.episode_seeds):
            _validate_episode_seed(episode)
            if set(episode.predecessor_ids) - {
                prior.seed_id for prior in self.episode_seeds[:index]
            }:
                raise GenesisValidationError(
                    "EpisodeSeed 的 predecessor_ids 必须只引用更早的 Episode"
                )
        place_ids = {seed.place_id for seed in self.place_seeds}
        relationship_people = {seed.person_id for seed in self.relationship_seeds}
        for place in self.place_seeds:
            if (
                not place.place_id.strip()
                or not place.label.strip()
                or not place.kind.strip()
            ):
                raise GenesisValidationError("PlaceSeed 的 ID、名称和类型不能为空")
            if place.visibility not in ("public", "private"):
                raise GenesisValidationError("PlaceSeed.visibility 无效")
            if (
                place.parent_id
                and place.parent_id not in place_ids
                and place.parent_id != "earth"
            ):
                raise GenesisValidationError(
                    "PlaceSeed.parent_id 必须引用本次地点或 earth"
                )
            _validate_text_collection(place.aliases, "PlaceSeed.aliases")

        for relationship in self.relationship_seeds:
            _validate_relationship_seed(relationship)
            if relationship.subject_id != f"elfie:{profile.identity.elfie_id}":
                raise GenesisValidationError(
                    "RelationshipSeed.subject_id 必须指向当前 Elfie"
                )
            if relationship.object_kind != "person":
                raise GenesisValidationError("当前 Genesis 关系只允许人物对象")
            if relationship.object_id != relationship.person_id:
                raise GenesisValidationError(
                    "RelationshipSeed.object_id 必须与 person_id 一致"
                )
            if set(relationship.episode_ids) - episode_ids:
                raise GenesisValidationError(
                    "RelationshipSeed 只能引用本次 Genesis 的 Episode"
                )

        for episode in self.episode_seeds:
            if not set(episode.place_ids) <= place_ids:
                raise GenesisValidationError(
                    "EpisodeSeed 引用的地点必须存在于 PlaceSeed"
                )
            if not set(episode.person_ids) <= relationship_people:
                raise GenesisValidationError(
                    "EpisodeSeed 引用的人物必须存在于 RelationshipSeed"
                )
            if episode.age_years_at_event is not None and (
                isinstance(episode.age_years_at_event, bool)
                or episode.age_years_at_event < 1
                or episode.age_years_at_event
                > (profile.identity.origin.age_years or episode.age_years_at_event)
            ):
                raise GenesisValidationError(
                    "EpisodeSeed.age_years_at_event 超出当前年龄"
                )
        if not any(seed.place_ids for seed in self.episode_seeds):
            raise GenesisValidationError("EpisodeSeed 至少需要一个生活地点引用")
        if not any(seed.person_ids for seed in self.episode_seeds):
            raise GenesisValidationError("EpisodeSeed 至少需要一个人物引用")
        if not any(seed.impact.strip() for seed in self.episode_seeds):
            raise GenesisValidationError("EpisodeSeed 至少需要一条长期影响")
        if not any(seed.predecessor_ids for seed in self.episode_seeds):
            raise GenesisValidationError("EpisodeSeed 至少需要一条前后因果链")

        knowledge_ids = {seed.seed_id for seed in self.knowledge_seeds}
        for seed in self.knowledge_seeds:
            if not set(seed.prerequisite_ids) <= knowledge_ids:
                raise GenesisValidationError(
                    "KnowledgeSeed.prerequisite_ids 必须引用本次知识"
                )
        if not self.self_model_seed.identity_summary.strip():
            raise GenesisValidationError("self_model_seed.identity_summary 不能为空")
        if not self.self_model_seed.known_facts:
            raise GenesisValidationError("SelfModelSeed 至少需要一个已知事实")
        manifest = self.manifest
        if not (
            manifest.manifest_id.strip()
            and manifest.compiler_version.strip()
            and manifest.idempotency_key.strip()
        ):
            raise GenesisValidationError("InitializationManifest 的身份字段不能为空")
        if manifest.status in ("validated", "committed") and manifest.validation_errors:
            raise GenesisValidationError(
                "已校验或已提交的 Manifest 不能保留 validation_errors"
            )
        if (
            isinstance(manifest.schema_version, bool)
            or not isinstance(manifest.schema_version, int)
            or manifest.schema_version < 1
        ):
            raise GenesisValidationError(
                "InitializationManifest.schema_version 必须为正数"
            )
        _validate_manifest_ids(manifest.output_ids, "output_ids")
        if not manifest.output_ids:
            raise GenesisValidationError("Genesis 必须记录 output_ids")
        if len(manifest.content_hash) != 64 or any(
            character not in "0123456789abcdefABCDEF"
            for character in manifest.content_hash
        ):
            raise GenesisValidationError(
                "InitializationManifest.content_hash 必须是 64 位十六进制摘要"
            )


def validate_genesis_bundle(bundle: GenesisBundle) -> GenesisBundle:
    """Validate and return the same immutable bundle for fluent hand-off code."""
    bundle.validate()
    return bundle


def _require_unique(values: Iterable[str], label: str) -> None:
    items = tuple(values)
    if len(set(items)) != len(items):
        raise GenesisValidationError(f"{label} 必须唯一")


def _validate_text_collection(values: tuple[str, ...], label: str) -> None:
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise GenesisValidationError(f"{label} 必须是非空字符串数组")


def _validate_knowledge_seed(seed: KnowledgeSeed) -> None:
    if not seed.seed_id.strip() or not seed.content.strip():
        raise GenesisValidationError("KnowledgeSeed 的 ID 和陈述不能为空")
    if (
        isinstance(seed.version, bool)
        or not isinstance(seed.version, int)
        or seed.version < 1
    ):
        raise GenesisValidationError("KnowledgeSeed.version 必须为正整数")
    if (
        not seed.source.strip()
        or not seed.source_ref.strip()
        or not seed.source_version.strip()
    ):
        raise GenesisValidationError(
            "KnowledgeSeed 必须带 source/source_ref/source_version"
        )
    if not seed.scope.strip() or not seed.topic.strip():
        raise GenesisValidationError("KnowledgeSeed 必须带 scope/topic")
    if seed.certainty not in ("high", "medium", "low"):
        raise GenesisValidationError("KnowledgeSeed.certainty 无效")
    if seed.level not in ("common", "regional", "specialist", "unknown"):
        raise GenesisValidationError("KnowledgeSeed.level 无效")
    if seed.mastery not in ("known", "partial", "heard", "unknown"):
        raise GenesisValidationError("KnowledgeSeed.mastery 无效")
    if seed.status not in ("active", "unknown-boundary"):
        raise GenesisValidationError("KnowledgeSeed.status 无效")
    if not 0.0 <= seed.importance <= 1.0:
        raise GenesisValidationError("KnowledgeSeed.importance 必须在 [0, 1] 内")
    _validate_text_collection(seed.aliases, "KnowledgeSeed.aliases")
    _validate_text_collection(seed.retrieval_terms, "KnowledgeSeed.retrieval_terms")
    _validate_text_collection(seed.eligibility, "KnowledgeSeed.eligibility")
    _validate_text_collection(seed.related_ids, "KnowledgeSeed.related_ids")
    if not (seed.aliases or seed.retrieval_terms):
        raise GenesisValidationError("结构化 KnowledgeSeed 至少需要一个别名或检索词")
    if seed.status == "active" and seed.level == "unknown":
        raise GenesisValidationError("active KnowledgeSeed 不能使用 unknown level")
    if seed.status == "unknown-boundary" and seed.mastery == "known":
        raise GenesisValidationError("unknown-boundary 知识不能标记为 known")


def _validate_relationship_seed(seed: RelationshipSeed) -> None:
    if not seed.person_id.strip() or not seed.display_name.strip():
        raise GenesisValidationError("RelationshipSeed 的身份不能为空")
    if not 0.0 <= seed.initial_trust <= 1.0:
        raise GenesisValidationError("RelationshipSeed.initial_trust 必须在 [0, 1] 内")
    if not 0.0 <= seed.importance <= 1.0:
        raise GenesisValidationError("RelationshipSeed.importance 必须在 [0, 1] 内")
    if not seed.relationship_id.strip():
        raise GenesisValidationError("RelationshipSeed.relationship_id 不能为空")
    if (
        isinstance(seed.version, bool)
        or not isinstance(seed.version, int)
        or seed.version < 1
    ):
        raise GenesisValidationError("RelationshipSeed.version 必须为正整数")
    if seed.object_kind not in ("person", "place", "group"):
        raise GenesisValidationError("RelationshipSeed.object_kind 无效")
    if seed.familiarity not in ("intimate", "known", "acquainted", "heard"):
        raise GenesisValidationError("RelationshipSeed.familiarity 无效")
    if not seed.subject_id.strip() or not seed.object_id.strip():
        raise GenesisValidationError(
            "结构化 RelationshipSeed 必须带 subject_id/object_id"
        )
    if (
        not seed.source.strip()
        or not seed.source_ref.strip()
        or not seed.source_version.strip()
    ):
        raise GenesisValidationError(
            "RelationshipSeed 必须带 source/source_ref/source_version"
        )
    if not seed.scope.strip() or not seed.topic.strip():
        raise GenesisValidationError("RelationshipSeed 必须带 scope/topic")
    _validate_text_collection(seed.aliases, "RelationshipSeed.aliases")
    _validate_text_collection(seed.retrieval_terms, "RelationshipSeed.retrieval_terms")
    if not (seed.aliases or seed.retrieval_terms):
        raise GenesisValidationError("RelationshipSeed 至少需要一个别名或检索词")


def _validate_episode_seed(seed: EpisodeSeed) -> None:
    if not seed.seed_id.strip() or not seed.content.strip():
        raise GenesisValidationError("EpisodeSeed 的 ID 和内容不能为空")
    if (
        isinstance(seed.version, bool)
        or not isinstance(seed.version, int)
        or seed.version < 1
    ):
        raise GenesisValidationError("EpisodeSeed.version 必须为正整数")
    if (
        not seed.source.strip()
        or not seed.source_ref.strip()
        or not seed.source_version.strip()
    ):
        raise GenesisValidationError(
            "EpisodeSeed 必须带 source/source_ref/source_version"
        )
    if (
        not seed.scope.strip()
        or not seed.topic.strip()
        or not seed.temporal_label.strip()
    ):
        raise GenesisValidationError("EpisodeSeed 必须带 scope/topic/temporal_label")
    if not seed.life_stage.strip():
        raise GenesisValidationError("EpisodeSeed.life_stage 不能为空")
    if seed.certainty not in ("high", "medium", "low"):
        raise GenesisValidationError("EpisodeSeed.certainty 无效")
    _validate_text_collection(seed.aliases, "EpisodeSeed.aliases")
    _validate_text_collection(seed.retrieval_terms, "EpisodeSeed.retrieval_terms")
    _validate_text_collection(seed.place_ids, "EpisodeSeed.place_ids")
    _validate_text_collection(seed.person_ids, "EpisodeSeed.person_ids")
    _validate_text_collection(seed.predecessor_ids, "EpisodeSeed.predecessor_ids")
    _validate_text_collection(seed.causal_links, "EpisodeSeed.causal_links")
    _validate_text_collection(seed.related_ids, "EpisodeSeed.related_ids")
    if not (seed.aliases or seed.retrieval_terms):
        raise GenesisValidationError("结构化 EpisodeSeed 至少需要一个别名或检索词")
    if len(set(seed.place_ids)) != len(seed.place_ids):
        raise GenesisValidationError("EpisodeSeed.place_ids 必须唯一")
    if len(set(seed.person_ids)) != len(seed.person_ids):
        raise GenesisValidationError("EpisodeSeed.person_ids 必须唯一")
    if not 0.0 <= seed.emotion_intensity <= 1.0:
        raise GenesisValidationError("EpisodeSeed.emotion_intensity 必须在 [0, 1] 内")
    if not 0.0 <= seed.importance <= 1.0:
        raise GenesisValidationError("EpisodeSeed.importance 必须在 [0, 1] 内")
    if seed.occurred_from is not None and not seed.occurred_from.strip():
        raise GenesisValidationError("EpisodeSeed.occurred_from 不能为空")
    if seed.occurred_to is not None and not seed.occurred_to.strip():
        raise GenesisValidationError("EpisodeSeed.occurred_to 不能为空")
    if not seed.result.strip() or not seed.feeling.strip():
        raise GenesisValidationError("结构化 EpisodeSeed 必须带 result 和 feeling")


def _validate_manifest_ids(values: tuple[str, ...], label: str) -> None:
    _validate_text_collection(values, f"InitializationManifest.{label}")
    if len(set(values)) != len(values):
        raise GenesisValidationError(f"InitializationManifest.{label} 必须唯一")


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
    """Temporary identity details disclosed after a candidate accepts contact."""

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
    """One deterministic candidate using the Earth-year age contract."""

    candidate_id: str
    role: str
    seed: int
    species_id: str
    life_stage: str
    age_years: int
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
    "EpisodeSeed",
    "KnowledgeLevel",
    "KnowledgeMastery",
    "KnowledgeSeed",
    "KnowledgeStatus",
    "STAGE_PLASTICITY",
    "InitializationManifest",
    "MemoryCertainty",
    "PlaceSeed",
    "ProfileDraft",
    "RelationshipSeed",
    "SelfModelSeed",
    "validate_genesis_bundle",
)
