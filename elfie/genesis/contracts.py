"""Typed, one-time creation contracts for an Elfie life.

Genesis only validates the hand-off from creation to the long-lived owners. It
does not remain in the runtime and it does not own permissions, devices,
models, channels, or memories after the hand-off.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
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
class KnowledgeSeed:
    """One public-canon fact selected for this Elfie's personal knowledge.

    ``content`` is the storage-facing spelling.  ``statement`` is accepted as
    a narrative alias so a canon author can use the same vocabulary as the
    bundled World Canon.  Both are normalized to the same immutable value.
    """

    seed_id: str
    content: str = ""
    source: str = "canon"
    source_ref: str = "canon:elfaria"
    source_version: str = WORLD_CANON_VERSION
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
    statement: str = ""
    version: int = 1
    importance: float = 0.5

    def __post_init__(self) -> None:
        content = self.content.strip()
        statement = self.statement.strip()
        if content and statement and content != statement:
            raise ValueError("KnowledgeSeed.content 与 statement 不能冲突")
        text = content or statement
        if not text:
            return
        object.__setattr__(self, "content", text)
        object.__setattr__(self, "statement", text)


@dataclass(frozen=True)
class EpisodeSeed:
    """One ordered, source-grounded pre-arrival personal experience."""

    seed_id: str
    content: str = ""
    source: str = "personal_memory"
    source_ref: str = "approved-seed:elfaria"
    source_version: str = WORLD_CANON_VERSION
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
    statement: str = ""
    version: int = 1

    def __post_init__(self) -> None:
        content = self.content.strip()
        statement = self.statement.strip()
        if content and statement and content != statement:
            raise ValueError("EpisodeSeed.content 与 statement 不能冲突")
        text = content or statement
        if text:
            object.__setattr__(self, "content", text)
            object.__setattr__(self, "statement", text)


@dataclass(frozen=True)
class RelationshipSeed:
    """A relationship skeleton, not a complete social graph."""

    person_id: str
    display_name: str
    role: str
    initial_trust: float
    shared_facts: tuple[str, ...] = ()
    unknown_facts: tuple[str, ...] = ()
    relationship_id: str | None = None
    relation_id: str | None = None
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
    source_version: str = WORLD_CANON_VERSION
    certainty: MemoryCertainty = "high"
    version: int = 1

    @property
    def stable_relationship_id(self) -> str:
        return self.relationship_id or self.relation_id or self.person_id


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
    namespace: str = ""
    generator_version: str = "genesis.v1"
    schema_version: int = 1
    master_seed: int | None = None
    input_ids: tuple[str, ...] = ()
    output_ids: tuple[str, ...] = ()
    content_hash: str = ""
    idempotency_key: str = ""
    committed_at: str | None = None


@dataclass(frozen=True)
class GenesisBundle:
    """The complete, temporary creation package for one Elfie."""

    profile_draft: ProfileDraft
    personality_seed: PersonalitySeed
    memory_seeds: tuple[MemorySeed, ...] = ()
    relationship_seeds: tuple[RelationshipSeed, ...] = ()
    self_model_seed: SelfModelSeed = field(
        default_factory=lambda: SelfModelSeed(
            identity_summary="",
            known_facts=(),
            unknown_facts=(),
        )
    )
    biography_plan: BiographyEnrichmentPlan = field(
        default_factory=BiographyEnrichmentPlan
    )
    manifest: InitializationManifest = field(
        default_factory=lambda: InitializationManifest(
            manifest_id="",
            canon_version=WORLD_CANON_VERSION,
            species_version="",
            reference_version="",
        )
    )
    knowledge_seeds: tuple[KnowledgeSeed, ...] = ()
    episode_seeds: tuple[EpisodeSeed, ...] = ()

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
        typed_seed_package = bool(self.knowledge_seeds or self.episode_seeds)
        if not typed_seed_package:
            _require_unique(
                (seed.person_id for seed in self.relationship_seeds),
                "relationship person_id",
            )
        for seed in self.memory_seeds:
            if not seed.seed_id.strip() or not seed.content.strip():
                raise GenesisValidationError("MemorySeed 的 ID 和内容不能为空")
            if not 0.0 <= seed.intensity <= 1.0:
                raise GenesisValidationError("MemorySeed.intensity 必须在 [0, 1] 内")
        # ``relationship_seeds`` alone is retained for the pre-source-first
        # compatibility bundle used by older callers.  The typed path starts
        # when either of the new knowledge/episode collections is present and
        # then requires the complete three-collection package.
        if typed_seed_package and not (
            self.knowledge_seeds and self.episode_seeds and self.relationship_seeds
        ):
            raise GenesisValidationError(
                "结构化 Genesis 必须同时提供 KnowledgeSeed、EpisodeSeed 和 RelationshipSeed"
            )
        if self.episode_seeds and not 3 <= len(self.episode_seeds) <= 5:
            raise GenesisValidationError("EpisodeSeed 必须有 3 到 5 段连续经历")
        _require_unique(
            (seed.seed_id for seed in self.knowledge_seeds),
            "knowledge seed_id",
        )
        _require_unique(
            (seed.seed_id for seed in self.episode_seeds),
            "episode seed_id",
        )
        _require_unique(
            (seed.stable_relationship_id for seed in self.relationship_seeds),
            "relationship_id",
        )
        all_seed_ids = (
            [seed.seed_id for seed in self.memory_seeds]
            + [seed.seed_id for seed in self.knowledge_seeds]
            + [seed.seed_id for seed in self.episode_seeds]
        )
        _require_unique(all_seed_ids, "Genesis seed_id")
        for knowledge_seed in self.knowledge_seeds:
            _validate_knowledge_seed(knowledge_seed, typed=typed_seed_package)
        for index, episode_seed in enumerate(self.episode_seeds):
            _validate_episode_seed(episode_seed, typed=typed_seed_package)
            if set(episode_seed.predecessor_ids) - {
                prior.seed_id for prior in self.episode_seeds[:index]
            }:
                raise GenesisValidationError(
                    "EpisodeSeed 的 predecessor_ids 必须只引用更早的 Episode"
                )
        if self.episode_seeds:
            if not 10 <= len(self.relationship_seeds) <= 20:
                raise GenesisValidationError(
                    "带结构化 Episode 的 Genesis 必须初始化 10 到 20 个关系对象"
                )
            if not any(seed.place_ids for seed in self.episode_seeds):
                raise GenesisValidationError("EpisodeSeed 至少需要一个生活地点引用")
            if not any(seed.person_ids for seed in self.episode_seeds):
                raise GenesisValidationError("EpisodeSeed 至少需要一个人物引用")
            if not any(seed.impact.strip() for seed in self.episode_seeds):
                raise GenesisValidationError("EpisodeSeed 至少需要一条长期影响")
            if not any(seed.predecessor_ids for seed in self.episode_seeds):
                raise GenesisValidationError("EpisodeSeed 至少需要一条前后因果链")
            if not any(
                any(
                    marker in (seed.topic + seed.content + seed.temporal_label)
                    for marker in ("赴地", "抵达", "地球", "arrival", "earth")
                )
                for seed in self.episode_seeds
            ):
                raise GenesisValidationError("EpisodeSeed 必须包含赴地或抵达地球经历")
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
            if not 0.0 <= relationship.importance <= 1.0:
                raise GenesisValidationError(
                    "RelationshipSeed.importance 必须在 [0, 1] 内"
                )
            if not relationship.stable_relationship_id.strip():
                raise GenesisValidationError("RelationshipSeed 的关系 ID 不能为空")
            if (
                isinstance(relationship.version, bool)
                or not isinstance(relationship.version, int)
                or relationship.version < 1
            ):
                raise GenesisValidationError("RelationshipSeed.version 必须为正整数")
            if relationship.object_kind not in ("person", "place", "group"):
                raise GenesisValidationError("RelationshipSeed.object_kind 无效")
            if relationship.familiarity not in (
                "intimate",
                "known",
                "acquainted",
                "heard",
            ):
                raise GenesisValidationError("RelationshipSeed.familiarity 无效")
            if relationship.subject_id and not relationship.subject_id.strip():
                raise GenesisValidationError("RelationshipSeed.subject_id 不能为空")
            if relationship.object_id and not relationship.object_id.strip():
                raise GenesisValidationError("RelationshipSeed.object_id 不能为空")
            if typed_seed_package and (
                not relationship.subject_id.strip()
                or not relationship.object_id.strip()
            ):
                raise GenesisValidationError(
                    "结构化 RelationshipSeed 必须带 subject_id/object_id"
                )
            if (
                not relationship.source.strip()
                or not relationship.source_ref.strip()
                or not relationship.source_version.strip()
            ):
                raise GenesisValidationError(
                    "RelationshipSeed 必须带 source/source_ref/source_version"
                )
            if not relationship.scope.strip() or not relationship.topic.strip():
                raise GenesisValidationError("RelationshipSeed 必须带 scope/topic")
            _validate_text_collection(relationship.aliases, "RelationshipSeed.aliases")
            _validate_text_collection(
                relationship.retrieval_terms,
                "RelationshipSeed.retrieval_terms",
            )
            if typed_seed_package and not (
                relationship.aliases or relationship.retrieval_terms
            ):
                raise GenesisValidationError(
                    "结构化 RelationshipSeed 至少需要一个别名或检索词"
                )
            if relationship.episode_ids and set(relationship.episode_ids) - {
                seed.seed_id for seed in self.episode_seeds
            }:
                raise GenesisValidationError(
                    "RelationshipSeed 只能引用本次 Genesis 的 Episode"
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
        if self.episode_seeds and self.relationship_seeds:
            episode_ids = {seed.seed_id for seed in self.episode_seeds}
            referenced_people = {
                person_id
                for seed in self.episode_seeds
                for person_id in seed.person_ids
            }
            relationship_people = {
                relationship.person_id for relationship in self.relationship_seeds
            }
            if not referenced_people <= relationship_people:
                raise GenesisValidationError(
                    "EpisodeSeed 引用的人物必须存在于 RelationshipSeed"
                )
            if not any(
                set(relationship.episode_ids) & episode_ids
                for relationship in self.relationship_seeds
            ):
                raise GenesisValidationError("至少一段关系必须关联 Episode")
            person_occurrences: dict[str, int] = {}
            for episode_seed in self.episode_seeds:
                for person_id in episode_seed.person_ids:
                    person_occurrences[person_id] = (
                        person_occurrences.get(person_id, 0) + 1
                    )
            if not any(count >= 2 for count in person_occurrences.values()):
                raise GenesisValidationError(
                    "至少一个重要人物必须在多个 Episode 中重复出现"
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
        if (
            isinstance(self.manifest.schema_version, bool)
            or not isinstance(self.manifest.schema_version, int)
            or self.manifest.schema_version < 1
        ):
            raise GenesisValidationError(
                "InitializationManifest.schema_version 必须为正数"
            )
        if self.manifest.namespace == "":
            # Empty is allowed for legacy bundles; typed bundles are rejected
            # below because their per-Elfie namespace is part of the contract.
            pass
        elif not self.manifest.namespace.strip():
            raise GenesisValidationError("InitializationManifest.namespace 不能为空")
        if self.episode_seeds and not self.manifest.namespace.strip():
            raise GenesisValidationError(
                "带结构化 Episode 的 Genesis 必须声明 Elfie namespace"
            )
        if typed_seed_package:
            expected_namespace = f"elfie:{profile.identity.elfie_id}"
            if self.manifest.namespace != expected_namespace:
                raise GenesisValidationError(
                    "InitializationManifest.namespace 必须与 Elfie identity 一致"
                )
            if not self.manifest.idempotency_key.strip():
                raise GenesisValidationError("结构化 Genesis 必须声明 idempotency_key")
            _validate_manifest_ids(self.manifest.input_ids, "input_ids")
            _validate_manifest_ids(self.manifest.output_ids, "output_ids")
            expected_input_ids = (
                {seed.seed_id for seed in self.knowledge_seeds}
                | {seed.seed_id for seed in self.episode_seeds}
                | {seed.stable_relationship_id for seed in self.relationship_seeds}
            )
            if not expected_input_ids <= set(self.manifest.input_ids):
                raise GenesisValidationError(
                    "InitializationManifest.input_ids 必须覆盖全部 Genesis Seed"
                )
            if not self.manifest.output_ids:
                raise GenesisValidationError("结构化 Genesis 必须记录 output_ids")
            if not self.manifest.generator_version.strip():
                raise GenesisValidationError(
                    "结构化 Genesis 必须声明 generator_version"
                )
            if not self.manifest.content_hash:
                raise GenesisValidationError("结构化 Genesis 必须记录 content_hash")
            if len(self.manifest.content_hash) != 64 or any(
                character not in "0123456789abcdefABCDEF"
                for character in self.manifest.content_hash
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


def _validate_knowledge_seed(seed: KnowledgeSeed, *, typed: bool = False) -> None:
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
    if typed and not (seed.aliases or seed.retrieval_terms):
        raise GenesisValidationError("结构化 KnowledgeSeed 至少需要一个别名或检索词")
    if seed.status == "active" and seed.level == "unknown":
        raise GenesisValidationError("active KnowledgeSeed 不能使用 unknown level")
    if seed.status == "unknown-boundary" and seed.mastery == "known":
        raise GenesisValidationError("unknown-boundary 知识不能标记为 known")


def _validate_episode_seed(seed: EpisodeSeed, *, typed: bool = False) -> None:
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
    if typed and not (seed.aliases or seed.retrieval_terms):
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
    if typed and (not seed.result.strip() or not seed.feeling.strip()):
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
    "EpisodeSeed",
    "KnowledgeLevel",
    "KnowledgeMastery",
    "KnowledgeSeed",
    "KnowledgeStatus",
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
