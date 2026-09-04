"""Deterministic semantic compilation for one Genesis transaction.

This module is deliberately independent from App and Infrastructure.  It
turns one accepted candidate and the published creation-source package into
the temporary LifeContext/Plan objects consumed by the existing typed
GenesisBundle hand-off.  No object produced here is a runtime source of truth.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from typing import Iterable, Literal, Mapping

from elfie.brain.selfhood.contracts import (
    AdaptiveSelf,
    BigFiveTraits,
    IdentityCore,
    SelfhoodState,
)
from elfie.brain.selfhood.personality_derivation import derive_personality
from elfie.profile import (
    AppearanceResolver,
    ElfieOrigin,
    ElfieProfile,
    SpeciesCatalog,
    create_visual_profile,
    current_species_catalog,
)

from .appearance import generate_appearance
from .contracts import (
    CandidateReveal,
    EpisodeSeed,
    GenesisAppearanceIntent,
    GenesisBatch,
    GenesisBundle,
    GenesisCandidate,
    GenesisError,
    InitializationManifest,
    KnowledgeMastery,
    KnowledgeSeed,
    PlaceSeed,
    ProfileDraft,
    RelationshipSeed,
    SelfModelSeed,
)
from .engine import GenesisEngine
from .serialization import (
    genesis_content_hash,
    output_ids_hash,
    planned_genesis_output_ids,
)
from .world import (
    EpisodeTheme,
    GenesisSourcePackage,
    RelationshipArchetype,
    WorldKnowledgeFact,
    WorldPlace,
)

_REQUIRED_EARTH_MODULE_ID = "earth_program"


@dataclass(frozen=True)
class GenesisCompileInput:
    """The small, already-normalized input crossing from Admission to Genesis."""

    elfie_id: str
    owner_reference: str
    display_name: str
    species_id: str
    gender: str
    life_stage: str
    age_years_at_adoption: int
    appearance_seed: int
    height: str
    build: str
    face: str
    signature: str
    candidate: GenesisCandidate | None = None
    personality_style: str = ""
    personality_description: str = ""
    big_five_overrides: Mapping[str, float] | None = None
    original_name: str = ""
    adoption_anchor_at: str = ""
    reservation_id: str = ""
    idempotency_key: str = ""
    arrival_base_id: str = "elfie_nest"
    invitation_accepted: bool = True
    full_body_image_url: str = ""
    headshot_image_url: str = ""


class GenesisCandidateReveal:
    """Build the temporary identity shown after a candidate accepts."""

    def __init__(self, source: GenesisSourcePackage) -> None:
        self._source = source

    def reveal(self, candidate: GenesisCandidate) -> CandidateReveal:
        names = _generated_names_for_seed(
            self._source,
            seed=candidate.seed,
            species_id=candidate.species_id,
            count=2,
        )
        labels = candidate.personality.candidate.labels[:2]
        traits = "、".join(labels) if labels else "有自己的节奏"
        return CandidateReveal(
            original_name=names[0],
            suggested_name=names[1] if len(names) > 1 else f"{names[0]}-2",
            personal_story=(
                f"你好，我是一个{traits}的精灵。我喜欢先观察周围，再和熟悉的人慢慢靠近。"
                "很高兴这次能和你见面。"
            ),
        )


@dataclass(frozen=True)
class LifeContextIdentity:
    species_id: str
    gender: str
    life_stage: str
    age_years_at_adoption: int
    adoption_anchor_at: str
    original_name: str
    display_name: str
    appearance_ref: str
    personality_anchor: tuple[float, ...]


@dataclass(frozen=True)
class LifeContextOrigin:
    birth_region_id: str
    birth_settlement_id: str
    birth_cell_id: str
    childhood_home_place_id: str
    predeparture_home_place_id: str


@dataclass(frozen=True)
class LifeContextHousehold:
    archetype_id: str
    member_roles: tuple[str, ...]
    care_and_trade_context: str


@dataclass(frozen=True)
class LifeContextLearning:
    path_id: str
    institution_ids: tuple[str, ...]
    apprenticeship_ids: tuple[str, ...]


@dataclass(frozen=True)
class LifeContextVocation:
    vocation_id: str
    proficiency_band: str
    workplace_place_id: str


@dataclass(frozen=True)
class LifeContextMobility:
    visited_place_ids: tuple[str, ...]
    familiar_route_ids: tuple[str, ...]


@dataclass(frozen=True)
class LifeContextEarthTransition:
    curriculum_version: str
    completed_module_ids: tuple[str, ...]
    departure_place_id: str
    route_id: str
    earth_household_ref: str
    invitation_accepted: bool


@dataclass(frozen=True)
class LifeContext:
    """The deterministic, transient life conditions for one accepted Elfie."""

    elfie_id: str
    identity: LifeContextIdentity
    origin: LifeContextOrigin
    household: LifeContextHousehold
    learning: LifeContextLearning
    vocation: LifeContextVocation
    mobility: LifeContextMobility
    earth_transition: LifeContextEarthTransition
    content_hash: str


@dataclass(frozen=True)
class PersonalKnowledgeEntry:
    """The two-axis knowledge decision before it becomes a Memory seed."""

    knowledge_id: str
    mastery_level: Literal["full", "partial", "reference_only", "none"]
    epistemic_kind: str
    statement_variant_id: str
    topic_ids: tuple[str, ...]
    aliases: tuple[str, ...]
    compiled_search_terms: tuple[str, ...]
    recall_eligible: bool
    acquired_via: str
    acquired_stage: str
    acquisition_ref: str
    consultable_target_ids: tuple[str, ...]
    confidence_class: str
    initial_confidence: float
    importance_class: str
    initial_importance: float
    memory_admission_kind: str
    bounded_salience_signals: tuple[str, ...]
    related_ids: tuple[str, ...]
    prerequisite_ids: tuple[str, ...]
    source_statement: str


@dataclass(frozen=True)
class KnowledgeDecisionTrace:
    """Creation-only explanation; never persisted with the final Elfie."""

    knowledge_id: str
    access: str
    exposure: str
    decision: str
    reason: str


@dataclass(frozen=True)
class PersonalGenesisPlan:
    """Transient final-owner plan assembled from a LifeContext."""

    life_context: LifeContext
    profile: ElfieProfile
    selfhood: SelfhoodState
    knowledge_entries: tuple[PersonalKnowledgeEntry, ...]
    relationship_seeds: tuple[RelationshipSeed, ...]
    episode_seeds: tuple[EpisodeSeed, ...]
    bundle: GenesisBundle
    decision_trace: tuple[KnowledgeDecisionTrace, ...] = ()


@dataclass(frozen=True)
class GenesisCompilation:
    """One compile result handed to App/Infrastructure for final publication."""

    plan: PersonalGenesisPlan
    energy_limits: dict[str, object] | None = None
    full_body_image_url: str = ""
    headshot_image_url: str = ""

    @property
    def life_context(self) -> LifeContext:
        return self.plan.life_context

    @property
    def bundle(self) -> GenesisBundle:
        return self.plan.bundle

    @property
    def profile(self) -> ElfieProfile:
        return self.plan.profile

    @property
    def output_ids_hash(self) -> str:
        """Digest of the typed output inventory used by publication recovery."""
        return output_ids_hash(self.bundle.manifest.output_ids)


class GenesisCompiler:
    """Own all deterministic life-semantic choices for a creation transaction."""

    compiler_version = "genesis-compiler.v0.2"

    def __init__(
        self,
        source_package: GenesisSourcePackage,
        *,
        catalog: SpeciesCatalog | None = None,
    ) -> None:
        if not source_package.is_published:
            raise GenesisError("只有已发布的 Genesis 资料包可以用于创建")
        self._source = source_package
        self._catalog = catalog

    def create_compile_envelope(self, request: GenesisCompileInput):
        """Bind one normalized request to the exact source package in use."""

        from .envelope import GenesisCompileEnvelope

        return GenesisCompileEnvelope(
            request,
            source_package_version=self._source.package_version,
            source_content_sha256=self._source.manifest.content_sha256,
            policy_version=self._source.generation_policy.policy_version,
            compiler_version=self.compiler_version,
        )

    def compile_envelope(self, envelope) -> GenesisCompilation:
        """Compile the private envelope only when its source binding still matches."""

        if envelope.source_package_version != self._source.package_version:
            raise GenesisError("GenesisCompileEnvelope 引用了不同的资料包版本")
        if envelope.source_content_sha256 != self._source.manifest.content_sha256:
            raise GenesisError("GenesisCompileEnvelope 引用了不同的资料包摘要")
        if envelope.policy_version != self._source.generation_policy.policy_version:
            raise GenesisError("GenesisCompileEnvelope 引用了不同的生成策略")
        if envelope.compiler_version != self.compiler_version:
            raise GenesisError("GenesisCompileEnvelope 引用了不同的编译器版本")
        return self.compile(envelope.request)

    def compile(self, request: GenesisCompileInput) -> GenesisCompilation:
        self._validate_input(request)
        supplied_candidate = request.candidate is not None
        candidate = request.candidate or self._default_candidate(request)
        if not supplied_candidate:
            # A direct technical caller supplies the master value used to make
            # a candidate, while the accepted candidate carries the actual
            # appearance seed.  Normalize to the latter before the remaining
            # stages so Profile, LifeContext and the bundle share one seed.
            request = replace(request, appearance_seed=candidate.seed)
        self._validate_candidate(request, candidate)
        species = self._species(request.species_id)
        context = self._life_context(request, candidate)
        profile = self._profile(request, candidate, context)
        knowledge_entries, traces = self._knowledge(context, request.species_id)
        relationships = self._relationships(request, context)
        episodes = self._episodes(request, context, relationships)
        relationships = self._attach_relationship_episodes(relationships, episodes)
        selfhood = self._selfhood(request, candidate, species)
        bundle = self._bundle(
            request,
            context,
            profile,
            selfhood,
            knowledge_entries,
            relationships,
            episodes,
            species,
        )
        # Do not hand an invalid semantic package to Admission or an
        # Infrastructure boundary.  Those boundaries validate again because
        # they accept typed results from the port, but Genesis is the first
        # owner that can prove all of its cross-stage references.
        bundle.validate()
        plan = PersonalGenesisPlan(
            life_context=context,
            profile=profile,
            selfhood=selfhood,
            knowledge_entries=knowledge_entries,
            relationship_seeds=relationships,
            episode_seeds=episodes,
            bundle=bundle,
            decision_trace=traces,
        )
        return GenesisCompilation(
            plan,
            energy_limits=_energy_limits(
                request.appearance_seed, request.height, request.build
            ),
            full_body_image_url=request.full_body_image_url,
            headshot_image_url=request.headshot_image_url,
        )

    def _validate_input(self, request: GenesisCompileInput) -> None:
        for name in (
            "elfie_id",
            "owner_reference",
            "display_name",
            "species_id",
            "gender",
            "life_stage",
        ):
            if not str(getattr(request, name)).strip():
                raise GenesisError(f"Genesis 输入 {name} 不能为空")
        if (
            isinstance(request.age_years_at_adoption, bool)
            or not isinstance(request.age_years_at_adoption, int)
            or request.age_years_at_adoption < 1
        ):
            raise GenesisError("age_years_at_adoption 必须为正整数")
        if not request.invitation_accepted:
            raise GenesisError("只有已接受的领养决定可以进入 Genesis")
        if not self._source.earth_arrival_rules.allows(
            request.species_id, request.life_stage
        ):
            raise GenesisError("该物种或生命阶段不符合赴地资格")
        expected_stage = stage_for_age(
            request.species_id,
            request.age_years_at_adoption,
            self._catalog,
        )
        if request.life_stage != expected_stage:
            raise GenesisError(
                "life_stage 必须与 age_years_at_adoption 的物种生命阶段一致"
            )

    def _validate_candidate(
        self, request: GenesisCompileInput, candidate: GenesisCandidate
    ) -> None:
        candidate_age = _candidate_age_years(candidate)
        if (
            candidate.species_id != request.species_id
            or candidate.gender != request.gender
            or candidate.life_stage != request.life_stage
            or candidate_age != request.age_years_at_adoption
        ):
            raise GenesisError("接受的候选核心与 Genesis 输入不一致")
        if candidate.seed != request.appearance_seed:
            raise GenesisError("接受的候选外貌与 Genesis 输入不一致")

    def _default_candidate(self, request: GenesisCompileInput) -> GenesisCandidate:
        """Normalize direct technical callers through the same candidate engine."""

        intent = GenesisAppearanceIntent(
            stature=request.height,
            build=request.build,
            face=request.face,
            signature=request.signature,
            priority="face",
        )
        stage = request.life_stage
        batch: GenesisBatch = GenesisEngine(catalog=self._catalog).generate_batch(
            master_seed=request.appearance_seed,
            batch_number=1,
            species_id=request.species_id,
            life_stage=stage,
            gender=request.gender,
            appearance=intent,
            answers=("observe", "research", "comfort", "adapt", "steady"),
        )
        candidate = batch.candidates[0]
        if _candidate_age_years(candidate) != request.age_years_at_adoption:
            # Direct callers without a candidate are normalized to the same
            # requested age; production Adoption always supplies the frozen
            # candidate core and therefore never enters this branch.
            candidate = replace(
                candidate,
                age_years=request.age_years_at_adoption,
                appearance=generate_appearance(
                    seed=candidate.seed,
                    species_id=request.species_id,
                    intent=intent,
                    role=candidate.role,
                    rng=random.Random(candidate.seed),
                    life_stage=candidate.life_stage,
                    age_years=request.age_years_at_adoption,
                    gender=candidate.gender,
                    variant_index=0,
                    catalog=self._catalog,
                ),
            )
        return candidate

    def _species(self, species_id: str):
        catalog = self._catalog or current_species_catalog()
        try:
            return catalog.definition(species_id, adoptable_only=True)
        except ValueError as error:
            raise GenesisError(f"不支持的 Genesis 物种: {species_id}") from error

    def _life_context(
        self, request: GenesisCompileInput, candidate: GenesisCandidate
    ) -> LifeContext:
        source = self._source
        rng = random.Random(self._domain_seed(request.appearance_seed, "origin"))
        cells = tuple(
            sorted(
                source.spatial_population.eligible_cells(request.species_id),
                key=lambda item: item.cell_id,
            )
        )
        if not cells:
            raise GenesisError(f"资料包没有物种 {request.species_id} 的出生地点")
        cell = _weighted_choice(cells, rng)
        public_home = cell.place_id
        life_rules = tuple(
            sorted(
                (
                    rule
                    for rule in source.life_archetypes
                    if request.species_id in rule.species_ids
                    and request.life_stage in rule.life_stages
                    and (not rule.place_ids or public_home in rule.place_ids)
                ),
                key=lambda item: item.archetype_id,
            )
        )
        if not life_rules:
            raise GenesisError(
                f"资料包没有匹配物种、年龄阶段和出生地的 LifeArchetypeRule: "
                f"{request.species_id}/{request.life_stage}/{public_home}"
            )
        life_rule = _weighted_choice(
            life_rules,
            random.Random(self._domain_seed(request.appearance_seed, "life-archetype")),
        )
        private_home = f"private:{request.elfie_id}:home"
        learning_place = (
            life_rule.institution_ids[0]
            if life_rule.institution_ids
            else _first_place_id(source.places, kind="learning_place")
        )
        square = _first_place_id(source.places, kind="settlement_shared_space")
        waystation = _first_place_id(source.places, kind="departure_facility")
        gateway = _first_place_id(source.places, kind="earth_gateway_station")
        visited = _unique(
            item
            for item in (
                private_home,
                public_home,
                learning_place,
                square,
                waystation,
                life_rule.workplace_place_id,
            )
            if item
        )
        routes = tuple(
            route.route_id
            for route in sorted(source.routes, key=lambda item: item.route_id)
            if route.from_place_id in visited or route.to_place_id in visited
        )
        # Admission supplies the real creation anchor.  The deterministic
        # fallback keeps direct compilation free of wall-clock nondeterminism.
        anchor = request.adoption_anchor_at or f"genesis-anchor:{request.elfie_id}"
        identity = LifeContextIdentity(
            species_id=request.species_id,
            gender=request.gender,
            life_stage=request.life_stage,
            age_years_at_adoption=request.age_years_at_adoption,
            adoption_anchor_at=anchor,
            original_name=request.original_name or self._generated_names(request, 0)[0],
            display_name=request.display_name,
            appearance_ref=f"appearance:{request.elfie_id}",
            personality_anchor=tuple(candidate.personality.candidate.latent),
        )
        origin = LifeContextOrigin(
            birth_region_id=source.known_region_id,
            birth_settlement_id=public_home,
            birth_cell_id=cell.cell_id if cell is not None else "settlement-default",
            childhood_home_place_id=private_home,
            predeparture_home_place_id=public_home,
        )
        household = LifeContextHousehold(
            archetype_id=life_rule.archetype_id,
            member_roles=life_rule.household_roles,
            care_and_trade_context=life_rule.care_and_trade_context,
        )
        learning = LifeContextLearning(
            path_id=life_rule.learning_path_id,
            institution_ids=tuple(life_rule.institution_ids),
            apprenticeship_ids=tuple(life_rule.apprenticeship_ids),
        )
        vocation = LifeContextVocation(
            vocation_id=life_rule.vocation_id,
            proficiency_band=life_rule.proficiency_band,
            workplace_place_id=life_rule.workplace_place_id,
        )
        mobility = LifeContextMobility(
            visited_place_ids=visited, familiar_route_ids=routes
        )
        module_ids = tuple(source.earth_arrival_rules.required_module_ids)
        if _REQUIRED_EARTH_MODULE_ID not in module_ids:
            raise GenesisError("所有抵达地球的 Elfie 都必须完成 earth_program 必修培训")
        if len(module_ids) != len(set(module_ids)):
            raise GenesisError("赴地必修培训模块 ID 必须唯一")
        transition = LifeContextEarthTransition(
            curriculum_version=source.package_version,
            completed_module_ids=tuple(module_ids),
            departure_place_id=waystation or public_home,
            route_id=_route_between(source, waystation, gateway),
            earth_household_ref=request.owner_reference,
            invitation_accepted=request.invitation_accepted,
        )
        provisional = LifeContext(
            elfie_id=request.elfie_id,
            identity=identity,
            origin=origin,
            household=household,
            learning=learning,
            vocation=vocation,
            mobility=mobility,
            earth_transition=transition,
            content_hash="",
        )
        return replace(provisional, content_hash=_content_hash(provisional))

    def _profile(
        self,
        request: GenesisCompileInput,
        candidate: GenesisCandidate,
        context: LifeContext,
    ) -> ElfieProfile:
        appearance = candidate.appearance
        profile = create_visual_profile(
            elfie_id=request.elfie_id,
            display_name=request.display_name,
            species_id=request.species_id,
            seed=request.appearance_seed,
            height_direction=request.height,
            build_direction=request.build,
            appearance=appearance,
            origin=ElfieOrigin(
                origin_place_id=context.origin.birth_settlement_id,
                origin_place_label=self._label(context.origin.birth_settlement_id),
                age_years=context.identity.age_years_at_adoption,
                age_anchor_at=context.identity.adoption_anchor_at,
            ),
            gender=request.gender,
            catalog=self._catalog,
        )
        # Resolve once here so invalid species/appearance combinations fail
        # before any persistence adapter sees the compilation.
        AppearanceResolver(self._catalog).resolve(profile)
        return profile

    def _place(self, place_id: str) -> WorldPlace | None:
        if place_id.startswith("private:"):
            return None
        try:
            return self._source.place(place_id)
        except KeyError:
            return None

    def _label(self, place_id: str) -> str:
        if place_id.startswith("private:"):
            return "我的住处"
        if place_id == self._source.world_id:
            return self._source.display_name
        if place_id == self._source.known_region_id:
            return self._source.known_region_name
        place = self._place(place_id)
        return place.label if place is not None else place_id

    def _knowledge(
        self, context: LifeContext, species_id: str
    ) -> tuple[tuple[PersonalKnowledgeEntry, ...], tuple[KnowledgeDecisionTrace, ...]]:
        required = set(self._source.earth_arrival_rules.required_knowledge_ids)
        selected: list[PersonalKnowledgeEntry] = []
        traces: list[KnowledgeDecisionTrace] = []
        facts = {fact.fact_id: fact for fact in self._source.knowledge}
        missing_required = sorted(required - facts.keys())
        if missing_required:
            raise GenesisError(
                "赴地规则引用了未发布的必修知识: " + ", ".join(missing_required)
            )
        for fact in self._source.knowledge:
            access = _access_for(fact, species_id)
            mandatory = fact.fact_id in required
            if access == "denied":
                traces.append(
                    KnowledgeDecisionTrace(
                        fact.fact_id, access, "none", "none", "资格不符"
                    )
                )
                continue
            mastery_level: Literal["full", "partial", "reference_only", "none"]
            if mandatory:
                if fact.status == "unknown-boundary" or fact.level == "unknown":
                    raise GenesisError(f"赴地必修知识 {fact.fact_id} 不能是未知边界")
                mastery_level = "full"
                decision = "mandatory"
                epistemic_kind = fact.epistemic_kind
                acquired_via = "earth_program"
                recall_eligible = True
            elif fact.status == "unknown-boundary":
                mastery_level = "reference_only"
                decision = "boundary"
                epistemic_kind = "unknown_boundary"
                acquired_via = "public_boundary"
                recall_eligible = True
            elif fact.level == "common":
                mastery_level = "full"
                decision = "common_exposure"
                epistemic_kind = fact.epistemic_kind
                acquired_via = "common_exposure"
                recall_eligible = True
            elif _is_exposed(fact, context):
                mastery_level = "partial"
                decision = "regional_exposure"
                epistemic_kind = fact.epistemic_kind
                acquired_via = "local_exposure"
                recall_eligible = True
            else:
                mastery_level = "none"
                decision = "not_exposed"
                traces.append(
                    KnowledgeDecisionTrace(
                        fact.fact_id, access, "none", decision, "没有足够接触机会"
                    )
                )
                continue
            statement_variant = "full"
            if mastery_level == "partial" and fact.variant("partial"):
                statement_variant = "partial"
            elif mastery_level == "partial":
                # A lower mastery level is safe only when the reviewed source
                # supplies its own resident-facing wording.  Never turn a
                # missing partial variant into accidental full knowledge.
                traces.append(
                    KnowledgeDecisionTrace(
                        fact.fact_id,
                        access,
                        "insufficient_variant",
                        "none",
                        "来源没有提供可安全下放的 partial 版本",
                    )
                )
                continue
            statement = fact.variant(statement_variant) or fact.statement
            if mastery_level == "reference_only":
                statement = _boundary_statement(statement)
            importance = max(fact.importance, 0.82) if mandatory else fact.importance
            entry = PersonalKnowledgeEntry(
                knowledge_id=fact.fact_id,
                mastery_level=mastery_level,
                epistemic_kind=epistemic_kind,
                statement_variant_id=statement_variant,
                topic_ids=(fact.topic,),
                aliases=fact.aliases,
                compiled_search_terms=fact.retrieval_terms,
                recall_eligible=recall_eligible,
                acquired_via=acquired_via,
                acquired_stage=context.identity.life_stage,
                acquisition_ref=f"knowledge:{fact.fact_id}",
                consultable_target_ids=(context.learning.institution_ids[0],)
                if mastery_level == "reference_only"
                and context.learning.institution_ids
                else (),
                confidence_class=fact.certainty,
                initial_confidence=_mastery_confidence(fact.certainty, mastery_level),
                importance_class=_importance_class(importance),
                initial_importance=importance,
                memory_admission_kind="genesis_knowledge",
                bounded_salience_signals=(fact.topic, fact.level),
                related_ids=fact.related_ids,
                prerequisite_ids=tuple(
                    item for item in fact.prerequisite_ids if item in facts
                ),
                source_statement=statement,
            )
            selected.append(entry)
            traces.append(
                KnowledgeDecisionTrace(
                    fact.fact_id, access, "available", decision, "来源和接触条件通过"
                )
            )
        selected = _close_prerequisites(selected, facts, species_id, context)
        selected_by_id = {entry.knowledge_id: entry for entry in selected}
        missing_after_closure = sorted(required - selected_by_id.keys())
        if missing_after_closure:
            raise GenesisError(
                "赴地必修知识未能形成可掌握的个人知识: "
                + ", ".join(missing_after_closure)
            )
        insufficient = sorted(
            knowledge_id
            for knowledge_id in required
            if selected_by_id[knowledge_id].mastery_level != "full"
        )
        if insufficient:
            raise GenesisError(
                "赴地必修知识必须达到 full 掌握: " + ", ".join(insufficient)
            )
        return tuple(selected), tuple(traces)

    def _eligible_episode_themes(
        self, context: LifeContext
    ) -> tuple[EpisodeTheme, ...]:
        themes = tuple(
            sorted(
                (
                    theme
                    for theme in self._source.episode_themes
                    if context.identity.life_stage in theme.life_stages
                    and context.identity.age_years_at_adoption >= theme.min_age_years
                ),
                key=lambda item: (item.order, item.theme_id),
            )
        )
        if not themes:
            raise GenesisError("资料包没有匹配当前年龄和生命阶段的经历主题")
        return themes

    def _relationships(
        self,
        request: GenesisCompileInput,
        context: LifeContext,
    ) -> tuple[RelationshipSeed, ...]:
        count = _bounded_count(
            self._source.generation_policy.relationship_count, preferred=13
        )
        themes = self._eligible_episode_themes(context)
        rules = tuple(
            sorted(
                self._source.relationship_archetypes, key=lambda item: item.archetype_id
            )
        )
        if not rules:
            raise GenesisError("资料包没有 RelationshipArchetypeRules")

        required_roles = _unique(
            role
            for theme in themes
            if theme.required or theme.required_roles
            for role in theme.required_roles
        )
        selected_rules: list[RelationshipArchetype] = []
        for role in required_roles:
            compatible = tuple(
                rule
                for rule in rules
                if rule.role == role
                and (
                    not rule.life_stages
                    or context.identity.life_stage in rule.life_stages
                )
            )
            if role == "family":
                same_species = tuple(
                    rule
                    for rule in compatible
                    if request.species_id in rule.person_species_ids
                )
                compatible = same_species or compatible
            if not compatible:
                raise GenesisError(f"资料包没有满足经历角色的关系原型: {role}")
            selected_rules.append(
                _weighted_choice(
                    compatible,
                    random.Random(
                        self._domain_seed(
                            request.appearance_seed, f"relationship-role:{role}"
                        )
                    ),
                )
            )
        while len(selected_rules) < max(0, count - 1):
            index = len(selected_rules)
            selected_rules.append(
                _weighted_choice(
                    rules,
                    random.Random(
                        self._domain_seed(
                            request.appearance_seed, f"relationship-slot:{index}"
                        )
                    ),
                )
            )

        names_by_species: dict[str, tuple[str, ...]] = {}
        name_counters: dict[str, int] = {}
        result: list[RelationshipSeed] = []
        used_person_ids: set[str] = set()
        for index, rule in enumerate(selected_rules):
            person_id = rule.archetype_id
            if person_id in used_person_ids:
                person_id = f"{person_id}-{index + 1:02d}"
            used_person_ids.add(person_id)
            person_species_id = rule.person_species_ids[
                self._domain_seed(request.appearance_seed, f"person-species:{index}")
                % len(rule.person_species_ids)
            ]
            if person_species_id not in names_by_species:
                names_by_species[person_species_id] = self._generated_names_for_species(
                    request, person_species_id, max(4, count)
                )
            name_index = name_counters.get(person_species_id, 0)
            pool = names_by_species[person_species_id]
            display_name = pool[name_index % len(pool)]
            name_counters[person_species_id] = name_index + 1
            result.append(
                RelationshipSeed(
                    person_id=person_id,
                    display_name=display_name,
                    role=rule.role,
                    initial_trust=rule.initial_trust,
                    shared_facts=(
                        f"我们在{context.origin.predeparture_home_place_id}附近的"
                        f"{rule.role}关系中相识。",
                    ),
                    unknown_facts=("对方没有在共同经历中告诉我的完整生活。",),
                    relationship_id=f"rel:{person_id}",
                    subject_id=f"elfie:{request.elfie_id}",
                    object_id=person_id,
                    direction="elfie_to_person",
                    familiarity=rule.familiarity,
                    importance=rule.importance,
                    aliases=(display_name, rule.role),
                    retrieval_terms=(rule.role, person_id, person_species_id),
                    episode_ids=(),
                    source="genesis_relationship_plan",
                    source_ref=f"relationship:{person_id}",
                    source_version="genesis-relationship.v0.2",
                    certainty="high",
                    version=1,
                    related_species_id=person_species_id,
                    age_band_at_genesis=context.identity.life_stage,
                    home_place_id=context.origin.predeparture_home_place_id,
                    vocation_id=rule.vocation_id,
                    person_species_id=person_species_id,
                    age_years_at_genesis=max(
                        1, context.identity.age_years_at_adoption + index
                    ),
                    competency_ids=rule.competency_ids,
                    eligible_episode_theme_ids=rule.episode_theme_ids,
                )
            )
        result.append(
            RelationshipSeed(
                person_id=f"owner-{request.owner_reference}",
                display_name="领养家庭",
                role="earth_household",
                initial_trust=0.25,
                shared_facts=(
                    "对方为我准备了新的生活空间。",
                    "我们会通过真实相处逐步建立信任。",
                ),
                unknown_facts=("对方完整的生活、过去和每天的想法。",),
                relationship_id=f"rel:owner-{request.owner_reference}",
                subject_id=f"elfie:{request.elfie_id}",
                object_id=f"owner-{request.owner_reference}",
                direction="elfie_to_person",
                familiarity="acquainted",
                importance=0.90,
                aliases=("领养家庭", "主人"),
                retrieval_terms=("领养", "家庭"),
                episode_ids=(),
                source="adoption_decision",
                source_ref="adoption:accepted",
                source_version="adoption-decision.v1",
                certainty="high",
                version=1,
                age_band_at_genesis=context.identity.life_stage,
            )
        )
        return tuple(result)

    def _episodes(
        self,
        request: GenesisCompileInput,
        context: LifeContext,
        relationships: tuple[RelationshipSeed, ...],
    ) -> tuple[EpisodeSeed, ...]:
        count = _bounded_count(
            self._source.generation_policy.episode_count, preferred=5
        )
        eligible = self._eligible_episode_themes(context)
        required = [theme for theme in eligible if theme.required]
        selected: list[EpisodeTheme] = sorted(
            required[:count], key=lambda item: (item.order, item.theme_id)
        )
        remaining = [theme for theme in eligible if theme not in selected]
        while len(selected) < min(count, len(eligible)):
            index = len(selected)
            chosen = _weighted_choice(
                tuple(remaining),
                random.Random(
                    self._domain_seed(request.appearance_seed, f"episode-theme:{index}")
                ),
            )
            selected.append(chosen)
            remaining.remove(chosen)
        selected = sorted(selected, key=lambda item: (item.order, item.theme_id))

        result: list[EpisodeSeed] = []
        for index, theme in enumerate(selected):
            person_ids = self._people_for_theme(theme, relationships, request)
            place_ids = self._places_for_theme(theme, context)
            event_age = max(
                theme.min_age_years,
                min(
                    context.identity.age_years_at_adoption,
                    (context.identity.age_years_at_adoption * (index + 1) + count)
                    // (count + 1),
                ),
            )
            event_stage = stage_for_age(request.species_id, event_age, self._catalog)
            labels = "、".join(self._label(place_id) for place_id in place_ids)
            content = (
                f"我在{labels}尝试{theme.goal}。起初{theme.obstacle}；"
                f"后来{theme.outcome}。这让我记住：{theme.impact}"
            )
            temporal_label = (
                "抵达地球时"
                if set(theme.place_kinds) & {"earth_gateway_station", "earth_home"}
                else "抵达前"
            )
            result.append(
                EpisodeSeed(
                    seed_id=theme.theme_id,
                    content=content,
                    source="personal_memory",
                    source_ref=f"episode:{theme.theme_id}",
                    source_version="genesis-episode.v0.2",
                    scope="elfie",
                    topic=f"biography.{theme.theme_id}",
                    aliases=(theme.label,),
                    retrieval_terms=(theme.label, "经历"),
                    certainty="high",
                    temporal_label=temporal_label,
                    life_stage=event_stage,
                    place_ids=place_ids,
                    person_ids=person_ids,
                    result=theme.outcome,
                    feeling=(
                        f"我对这段{theme.label}经历有清楚的感受，"
                        "但不会把感受当作额外事实。"
                    ),
                    impact=theme.impact,
                    predecessor_ids=(result[-1].seed_id,) if result else (),
                    causal_links=(f"{result[-1].seed_id} -> {theme.theme_id}",)
                    if result
                    else (),
                    related_ids=theme.required_knowledge_ids,
                    emotional_tone=theme.emotional_tone,
                    emotion_intensity=min(1.0, theme.weight),
                    importance=min(1.0, max(0.5, theme.weight)),
                    theme_id=theme.theme_id,
                    age_years_at_event=event_age,
                )
            )
        if len(result) < 3:
            raise GenesisError("资料包可用经历主题不足以满足 Genesis 数量边界")
        return tuple(result)

    def _people_for_theme(
        self,
        theme: EpisodeTheme,
        relationships: tuple[RelationshipSeed, ...],
        request: GenesisCompileInput,
    ) -> tuple[str, ...]:
        selected: list[str] = []
        for role in theme.required_roles:
            for relationship in relationships:
                if relationship.role != role:
                    continue
                if relationship.eligible_episode_theme_ids and (
                    theme.theme_id not in relationship.eligible_episode_theme_ids
                ):
                    continue
                selected.append(relationship.person_id)
                break
        if theme.theme_id == "arrival-nest":
            selected.append(f"owner-{request.owner_reference}")
        if not selected:
            for relationship in relationships:
                if relationship.role != "earth_household":
                    selected.append(relationship.person_id)
                    break
        return _unique(selected)

    def _places_for_theme(
        self, theme: EpisodeTheme, context: LifeContext
    ) -> tuple[str, ...]:
        if "private_home" in theme.place_kinds:
            return (context.origin.childhood_home_place_id,)
        if set(theme.place_kinds) & {"earth_gateway_station", "earth_home"}:
            # Arrival is an explicitly observed transition: the accepted
            # resident can remember the gateway and the Earth home even though
            # neither belongs to the pre-arrival mobility list.
            selected = [
                place.place_id
                for place in sorted(self._source.places, key=lambda item: item.place_id)
                if place.kind in theme.place_kinds
            ]
            if selected:
                return _unique(selected)
        visited = set(context.mobility.visited_place_ids)
        selected = [
            place.place_id
            for place in sorted(self._source.places, key=lambda item: item.place_id)
            if place.place_id in visited and place.kind in theme.place_kinds
        ]
        if not selected:
            # A resident may only remember places represented in its own
            # observed/visited projection.  The world package is not an
            # implicit personal map, so never promote an unvisited place just
            # because its kind matches the episode theme.
            selected = [context.origin.predeparture_home_place_id]
        return _unique(selected)

    @staticmethod
    def _attach_relationship_episodes(
        relationships: tuple[RelationshipSeed, ...], episodes: tuple[EpisodeSeed, ...]
    ) -> tuple[RelationshipSeed, ...]:
        episode_by_person: dict[str, list[str]] = {}
        for episode in episodes:
            for person_id in episode.person_ids:
                episode_by_person.setdefault(person_id, []).append(episode.seed_id)
        return tuple(
            replace(
                relationship,
                episode_ids=tuple(episode_by_person.get(relationship.person_id, ())),
            )
            for relationship in relationships
        )

    def _selfhood(
        self,
        request: GenesisCompileInput,
        candidate: GenesisCandidate,
        species,
    ) -> SelfhoodState:
        candidate_values = {
            key: round((value + 2.0) / 4.0, 4)
            for key, value in zip(
                (
                    "openness",
                    "conscientiousness",
                    "extraversion",
                    "agreeableness",
                    "neuroticism",
                ),
                candidate.personality.candidate.latent,
            )
        }
        # The candidate answers remain the deterministic baseline.  A
        # developer-tool description or explicit calibration may refine that
        # baseline through the existing bounded derivation algorithm; neither
        # path creates a second personality writer.
        personality_text = " ".join(
            value
            for value in (request.personality_style, request.personality_description)
            if value.strip()
        )
        derivation = derive_personality(
            request.elfie_id,
            personality_text,
            request.big_five_overrides,
            default_big_five=candidate_values,
        )
        big_five = BigFiveTraits(**dict(derivation.big_five))
        expression_ids = (
            (request.personality_style.strip(),)
            if request.personality_style.strip()
            else tuple(candidate.personality.candidate.labels or (derivation.preset,))
        )
        state = SelfhoodState(
            revision=1,
            committed_at=datetime.fromtimestamp(0, timezone.utc),
            identity_core=IdentityCore(
                elfie_id=request.elfie_id,
                display_name=request.display_name,
                species_id=request.species_id,
                species_name=species.display_name,
                resident_role="ElfieNest 居民",
            ),
            adaptive_self=AdaptiveSelf(
                big_five=big_five,
                interaction_tendency_ids=tuple(species.earth_first_contact_cues),
                coping_tendency_ids=tuple(species.common_sensory_biases),
                expression_tendency_ids=expression_ids,
                value_ids=(
                    "尊重自愿选择，不把猜测说成亲历。",
                    "不知道时说明不知道。",
                ),
                speech_marker_ids=("呢",),
                source_event_ids=(),
            ),
        )
        return state

    def _bundle(
        self,
        request: GenesisCompileInput,
        context: LifeContext,
        profile: ElfieProfile,
        selfhood: SelfhoodState,
        knowledge: tuple[PersonalKnowledgeEntry, ...],
        relationships: tuple[RelationshipSeed, ...],
        episodes: tuple[EpisodeSeed, ...],
        species,
    ) -> GenesisBundle:
        knowledge_seeds = tuple(
            _knowledge_seed(entry, self._source) for entry in knowledge
        )
        self_model = SelfModelSeed(
            identity_summary=f"我是 {request.display_name}，正式物种是 {species.display_name}。",
            known_facts=tuple(
                entry.source_statement
                for entry in knowledge
                if entry.mastery_level == "full"
            )[:8],
            unknown_facts=tuple(
                entry.source_statement
                for entry in knowledge
                if entry.mastery_level == "reference_only"
            )[:8],
            knowledge_scope=(
                "我把亲历、听闻和未确认的信息分开。",
                "不知道时说明不知道。",
            ),
            species_knowledge=tuple(species.common_knowledge),
            skills=("区分亲历、听闻和未确认信息", "在陌生事物前先观察和询问"),
            habits=("先确认边界，再靠近陌生事物",),
            preferences=("逐步熟悉的新环境",),
            emotional_triggers=("被要求把猜测说成事实",),
            current_goal="在 ElfieNest 里通过真实相处逐步学习地球生活。",
            earth_adaptation=("地球设备需要通过真实接触逐步学习。",),
        )
        manifest_id = (
            request.reservation_id.strip() or f"genesis:{request.elfie_id}:v0.2"
        )
        idempotency_key = (
            request.idempotency_key.strip()
            or f"genesis-submit:{request.elfie_id}:{manifest_id}"
        )
        bundle = GenesisBundle(
            profile_draft=ProfileDraft(profile),
            selfhood_state=selfhood,
            relationship_seeds=relationships,
            self_model_seed=self_model,
            manifest=InitializationManifest(
                manifest_id=manifest_id,
                status="validated",
                schema_version=1,
                content_hash="",
                idempotency_key=idempotency_key,
            ),
            knowledge_seeds=knowledge_seeds,
            episode_seeds=episodes,
            place_seeds=self._place_seeds(context, request),
        )
        content_hash = genesis_content_hash(bundle)
        output_ids = planned_genesis_output_ids(bundle)
        return replace(
            bundle,
            manifest=replace(
                bundle.manifest,
                content_hash=content_hash,
                output_ids=output_ids,
            ),
        )

    def _place_seeds(
        self, context: LifeContext, request: GenesisCompileInput
    ) -> tuple[PlaceSeed, ...]:
        requested = set(context.mobility.visited_place_ids)
        requested.add(context.earth_transition.departure_place_id)
        requested.update(
            item
            for item in (
                _first_place_id(self._source.places, kind="earth_gateway_station"),
                _first_place_id(self._source.places, kind="earth_home"),
            )
            if item
        )
        result: list[PlaceSeed] = []
        seen: set[str] = set()

        def append(place: PlaceSeed) -> None:
            if place.place_id in seen:
                return
            seen.add(place.place_id)
            result.append(place)

        append(
            PlaceSeed(
                place_id=self._source.world_id,
                label=self._source.display_name,
                kind="home_world",
                aliases=(self._source.display_name,),
                source_ref=f"place:{self._source.world_id}",
            )
        )
        append(
            PlaceSeed(
                place_id=self._source.known_region_id,
                label=self._source.known_region_name,
                kind="home_region",
                parent_id=self._source.world_id,
                aliases=(),
                source_ref=f"place:{self._source.known_region_id}",
            )
        )
        append(
            PlaceSeed(
                place_id=f"private:{request.elfie_id}:home",
                label="我的住处",
                kind="private_home",
                parent_id=context.origin.predeparture_home_place_id,
                visibility="private",
                source_ref="genesis:private-home",
            )
        )
        for place in sorted(self._source.places, key=lambda item: item.place_id):
            if place.place_id not in requested:
                continue
            append(
                PlaceSeed(
                    place_id=place.place_id,
                    label=place.label,
                    kind=place.kind,
                    parent_id=place.parent_id,
                    aliases=place.aliases,
                    description=place.description,
                    source_ref=f"place:{place.place_id}",
                )
            )
        return tuple(result)

    def _generated_names(
        self, request: GenesisCompileInput, count: int
    ) -> tuple[str, ...]:
        return self._generated_names_for_species(request, request.species_id, count)

    def _generated_names_for_species(
        self, request: GenesisCompileInput, species_id: str, count: int
    ) -> tuple[str, ...]:
        return _generated_names_for_seed(
            self._source,
            seed=request.appearance_seed,
            species_id=species_id,
            count=count,
        )

    def _domain_seed(self, seed: int, label: str) -> int:
        policy = self._source.generation_policy
        return _domain_seed(
            seed,
            label,
            algorithm=policy.seed_algorithm,
            policy_version=policy.policy_version,
        )


def _candidate_age_years(candidate: GenesisCandidate) -> int:
    value = candidate.age_years
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise GenesisError("候选年龄必须是正整数年")
    return value


def _domain_seed(
    seed: int,
    label: str,
    *,
    algorithm: str = "blake2b-labeled-v1",
    policy_version: str = "generation-policy.v1",
) -> int:
    if algorithm != "blake2b-labeled-v1":
        raise GenesisError(f"不支持的 Genesis seed 算法: {algorithm}")
    digest = hashlib.blake2b(
        f"{seed}:{label}:{policy_version}".encode(), digest_size=8
    ).digest()
    return int.from_bytes(digest, "big")


def _generated_names_for_seed(
    source: GenesisSourcePackage,
    *,
    seed: int,
    species_id: str,
    count: int,
) -> tuple[str, ...]:
    pool = source.name_rules.pool(species_id) or ("Nemi",)
    policy = source.generation_policy
    offset = _domain_seed(
        seed,
        f"names:{species_id}",
        algorithm=policy.seed_algorithm,
        policy_version=policy.policy_version,
    ) % len(pool)
    rotated = tuple(pool[offset:] + pool[:offset])
    result: list[str] = []
    for index in range(max(count, 1)):
        base = rotated[index % len(rotated)]
        value = base if index < len(pool) else f"{base}-{index + 1}"
        if value not in result:
            result.append(value)
    return tuple(result)


def _weighted_choice(values, rng: random.Random):
    total = sum(float(item.weight) for item in values)
    if total <= 0:
        raise GenesisError("出生地点权重必须为正")
    target = rng.random() * total
    for item in values:
        target -= float(item.weight)
        if target <= 0:
            return item
    return values[-1]


def _first_place_id(places: Iterable[WorldPlace], *, kind: str) -> str:
    for place in sorted(places, key=lambda item: item.place_id):
        if place.kind == kind:
            return place.place_id
    return ""


def _route_between(source: GenesisSourcePackage, start: str, end: str) -> str:
    for route in sorted(source.routes, key=lambda item: item.route_id):
        if {route.from_place_id, route.to_place_id} == {start, end}:
            return route.route_id
    return ""


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return tuple(result)


def _access_for(fact: WorldKnowledgeFact, species_id: str) -> str:
    eligible = set(fact.eligibility)
    return (
        "available"
        if not eligible or "all" in eligible or species_id in eligible
        else "denied"
    )


def _is_exposed(fact: WorldKnowledgeFact, context: LifeContext) -> bool:
    """Apply the exposure axis after species/qualification access passes.

    Common facts are public opportunities rather than guaranteed mastery.  A
    regional or place fact needs a matching lived region/place, and a future
    specialist fact needs a learning or work anchor.  The bundled v1 source
    deliberately contains no specialist facts, so this remains conservative
    without inventing a profession.
    """

    if fact.exposure_weight <= 0.0:
        return False
    if fact.level == "common":
        return True
    visited = set(context.mobility.visited_place_ids) | {
        context.origin.birth_region_id,
        context.origin.birth_settlement_id,
        context.origin.predeparture_home_place_id,
    }
    if fact.level == "regional":
        return fact.scope in {"region", "culture", "society"} or bool(
            set(fact.related_ids) & visited
        )
    if fact.level == "specialist":
        anchors = set(context.learning.institution_ids)
        if context.vocation.workplace_place_id:
            anchors.add(context.vocation.workplace_place_id)
        return bool(set(fact.related_ids) & anchors)
    return False


def _boundary_statement(statement: str) -> str:
    return f"我知道这里有边界，但我不知道完整答案：{statement}"


def _certainty_score(certainty: str) -> float:
    return {"high": 1.0, "medium": 0.75, "low": 0.5}.get(certainty, 0.5)


def _mastery_confidence(certainty: str, mastery: str) -> float:
    score = _certainty_score(certainty)
    if mastery == "partial":
        return min(score, 0.75)
    if mastery == "reference_only":
        return min(score, 0.5)
    return score


def _importance_class(value: float) -> str:
    return "core" if value >= 0.85 else "high" if value >= 0.65 else "ordinary"


def _knowledge_seed(
    entry: PersonalKnowledgeEntry, source: GenesisSourcePackage
) -> KnowledgeSeed:
    fact = source.fact(entry.knowledge_id)
    mastery_by_level: dict[
        Literal["full", "partial", "reference_only", "none"], KnowledgeMastery
    ] = {
        "full": "known",
        "partial": "partial",
        "reference_only": "heard",
        "none": "unknown",
    }
    mastery = mastery_by_level[entry.mastery_level]
    return KnowledgeSeed(
        seed_id=entry.knowledge_id,
        content=entry.source_statement,
        source="genesis_source",
        source_ref=f"resident-knowledge:{fact.fact_id}",
        source_version=f"resident-knowledge-v{fact.version}",
        scope=fact.scope,
        topic=fact.topic,
        aliases=entry.aliases,
        retrieval_terms=entry.compiled_search_terms,
        certainty=fact.certainty,
        level=fact.level,
        mastery=mastery,
        status=fact.status,
        eligibility=fact.eligibility,
        related_ids=entry.related_ids,
        version=fact.version,
        importance=entry.initial_importance,
        epistemic_kind=entry.epistemic_kind,
        prerequisite_ids=entry.prerequisite_ids,
        acquired_via=entry.acquired_via,
        acquired_stage=entry.acquired_stage,
        consultable_target_ids=entry.consultable_target_ids,
        confidence_class=entry.confidence_class,
        initial_confidence=entry.initial_confidence,
        recall_eligible=entry.recall_eligible,
    )


def _close_prerequisites(
    entries: list[PersonalKnowledgeEntry],
    facts: dict[str, WorldKnowledgeFact],
    species_id: str,
    context: LifeContext,
) -> list[PersonalKnowledgeEntry]:
    original = {entry.knowledge_id: entry for entry in entries}
    generated: dict[str, PersonalKnowledgeEntry] = {}
    visiting: set[str] = set()
    resolved: dict[str, tuple[bool, frozenset[str]]] = {}

    def close(fact_id: str) -> tuple[bool, frozenset[str]]:
        if fact_id in resolved:
            return resolved[fact_id]
        if fact_id in visiting:
            return False, frozenset()
        fact = facts.get(fact_id)
        if fact is None or _access_for(fact, species_id) == "denied":
            resolved[fact_id] = (False, frozenset())
            return resolved[fact_id]
        if (
            fact_id not in original
            and fact.status != "unknown-boundary"
            and not _is_exposed(fact, context)
        ):
            resolved[fact_id] = (False, frozenset())
            return resolved[fact_id]
        visiting.add(fact_id)
        closure_ids: set[str] = {fact_id}
        for prerequisite_id in fact.prerequisite_ids:
            available, prerequisite_closure = close(prerequisite_id)
            if not available:
                visiting.remove(fact_id)
                resolved[fact_id] = (False, frozenset())
                return resolved[fact_id]
            closure_ids.update(prerequisite_closure)
        visiting.remove(fact_id)
        if fact_id in original:
            resolved[fact_id] = (True, frozenset(closure_ids))
            return resolved[fact_id]

        mastery: Literal["full", "partial", "reference_only"] = (
            "reference_only"
            if fact.status == "unknown-boundary"
            else "full"
            if fact.level == "common"
            else "partial"
        )
        statement_variant = "full" if mastery == "full" else "partial"
        statement = fact.variant(statement_variant)
        if statement is None:
            # A prerequisite may only be added at a mastery level for which
            # the published source provides a safe resident-facing variant.
            resolved[fact_id] = (False, frozenset())
            return resolved[fact_id]
        if mastery == "reference_only":
            statement = _boundary_statement(statement)
        generated[fact_id] = PersonalKnowledgeEntry(
            knowledge_id=fact_id,
            mastery_level=mastery,
            epistemic_kind=(
                "unknown_boundary"
                if mastery == "reference_only"
                else fact.epistemic_kind
            ),
            statement_variant_id=statement_variant,
            topic_ids=(fact.topic,),
            aliases=fact.aliases,
            compiled_search_terms=fact.retrieval_terms,
            recall_eligible=True,
            acquired_via="prerequisite",
            acquired_stage=context.identity.life_stage,
            acquisition_ref=f"knowledge:{fact_id}",
            consultable_target_ids=(),
            confidence_class=fact.certainty,
            initial_confidence=_mastery_confidence(fact.certainty, mastery),
            importance_class=_importance_class(fact.importance),
            initial_importance=fact.importance,
            memory_admission_kind="genesis_knowledge",
            bounded_salience_signals=(fact.topic, fact.level),
            related_ids=fact.related_ids,
            prerequisite_ids=tuple(fact.prerequisite_ids),
            source_statement=statement,
        )
        resolved[fact_id] = (True, frozenset(closure_ids))
        return resolved[fact_id]

    retained_ids: set[str] = set()
    for entry in entries:
        available, closure_ids = close(entry.knowledge_id)
        if available:
            retained_ids.update(closure_ids)

    result: list[PersonalKnowledgeEntry] = []
    for fact_id in facts:
        if fact_id not in retained_ids:
            continue
        selected_entry = original.get(fact_id) or generated.get(fact_id)
        if selected_entry is None:
            # This is unreachable when the closure algorithm succeeds, but a
            # hard failure is safer than publishing a dependent without its
            # prerequisite record.
            raise GenesisError(f"知识前置闭包缺少条目: {fact_id}")
        result.append(selected_entry)
    return result


def _bounded_count(bounds: tuple[int, int], *, preferred: int) -> int:
    minimum, maximum = bounds
    if minimum < 1 or maximum < minimum:
        raise GenesisError("Genesis 生成数量范围无效")
    return min(maximum, max(minimum, preferred))


def stage_for_age(
    species_id: str, age_years: int, catalog: SpeciesCatalog | None
) -> str:
    selected_catalog = catalog or current_species_catalog()
    definition = selected_catalog.definition(species_id, adoptable_only=True)
    if definition.genesis is None:
        raise GenesisError(f"物种 {species_id!r} 缺少 Genesis 配置")
    for stage in ("youth", "young_adult", "mature", "elder"):
        minimum, maximum = definition.genesis.stage_ranges[stage]
        if minimum <= age_years <= maximum:
            return stage
    raise GenesisError(f"年龄 {age_years} 不在物种 {species_id!r} 的生命阶段范围内")


def _content_hash(value: LifeContext) -> str:
    payload = asdict(value)
    payload["content_hash"] = ""
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _energy_limits(seed: int, height: str, build: str) -> dict[str, object]:
    """Generate the Brain-owned initial energy policy for this creation.

    This is a bounded startup output, not a Profile attribute.  Keeping the
    calculation in Genesis makes the workspace adapter a persistence-only
    boundary while preserving the existing deterministic behavior.
    """

    rng = random.Random(seed + 47)
    depletion_rate = rng.uniform(0.003, 0.008)
    if height == "tall":
        depletion_rate *= 1.1
    elif height == "short":
        depletion_rate *= 0.9
    if build == "plump":
        depletion_rate *= 1.05
    elif build == "slim":
        depletion_rate *= 0.95
    return {
        "limits": {
            "energy": {
                "max_value": 100.0,
                "initial_value": 100.0,
                "depletion_rate_per_sec": round(depletion_rate, 4),
                "depletion_per_remote_chat": round(rng.uniform(2.0, 3.5), 2),
                "depletion_per_local_chat": round(rng.uniform(0.3, 0.8), 2),
                "recovery_rate_sleep_per_sec": round(rng.uniform(0.03, 0.08), 4),
            },
            "fatigue": {
                "initial_value": 0.0,
                "max_value": 100.0,
                "accumulation_rate_per_sec": round(rng.uniform(0.002, 0.005), 4),
                "decay_rate_sleep_per_sec": round(rng.uniform(0.03, 0.06), 4),
                "hibernation_threshold": 95.0,
                "wakeup_threshold": round(rng.uniform(10.0, 20.0), 1),
            },
            "runtime_usage": {
                "observe_only": True,
                "daily_token_budget": rng.randint(8000, 12000),
                "local_token_cost": 0,
                "remote_token_cost": 1,
            },
        }
    }


__all__ = (
    "GenesisCompilation",
    "GenesisCandidateReveal",
    "GenesisCompileInput",
    "GenesisCompiler",
    "KnowledgeDecisionTrace",
    "LifeContext",
    "LifeContextEarthTransition",
    "LifeContextHousehold",
    "LifeContextIdentity",
    "LifeContextLearning",
    "LifeContextMobility",
    "LifeContextOrigin",
    "LifeContextVocation",
    "PersonalGenesisPlan",
    "PersonalKnowledgeEntry",
)
