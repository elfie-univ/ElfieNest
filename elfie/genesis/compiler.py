"""Deterministic semantic compilation for one Genesis transaction.

This module is deliberately independent from App and Infrastructure.  It
turns one accepted candidate and the published creation-source package into
the temporary LifeContext/Plan objects consumed by the existing typed
GenesisBundle hand-off.  No object produced here is a runtime source of truth.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import unicodedata
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from typing import Callable, Iterable, Literal, Mapping

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
    PlaceRelationSeed,
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
    KnowledgeCondition,
    RelationshipArchetype,
    VisitOpportunityRule,
    WorldKnowledgeFact,
    WorldPlace,
)


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
    visit_counts: tuple[tuple[str, int], ...] = ()
    visit_purposes: tuple[tuple[str, str], ...] = ()
    visit_stay_days: tuple[tuple[str, int], ...] = ()
    visit_age_years: tuple[tuple[str, tuple[int, ...]], ...] = ()
    observed_place_ids: tuple[str, ...] = ()
    opportunity_records: tuple[tuple[str, tuple[str, ...], int, str, int], ...] = ()
    opportunity_route_ids: tuple[tuple[str, tuple[str, ...]], ...] = ()
    opportunity_travel_days: tuple[tuple[str, int], ...] = ()
    unmade_opportunity_records: tuple[tuple[str, int, str], ...] = ()
    # Internal legal-path evidence.  Cells and costs remain transient Genesis
    # data; only the reviewed route IDs are carried into Memory Episodes.
    travel_paths: tuple[tuple[str, tuple[str, ...], int], ...] = ()


@dataclass(frozen=True)
class LifeContextEarthTransition:
    preparation_duration_local_days: int
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
    acquired_age_years: int | None = None


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
        relationships = self._relationships(request, context)
        context = self._personal_mobility(request, candidate, context, relationships)
        profile = self._profile(request, candidate, context)
        episodes = (
            *self._episodes(request, context, relationships),
            *self._family_episodes(request, context, relationships),
            *self._visit_episodes(context),
        )
        episodes = self._order_life_episodes(episodes)
        knowledge_entries, traces = self._knowledge(
            context,
            request.species_id,
            episodes,
            seed=request.appearance_seed,
        )
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
            or request.age_years_at_adoption
            < self._source.generation_policy.candidate_minimum_age_years
        ):
            raise GenesisError(
                "age_years_at_adoption 必须为至少 "
                f"{self._source.generation_policy.candidate_minimum_age_years} 岁的整数"
            )
        if not request.invitation_accepted:
            raise GenesisError("只有已接受的领养决定可以进入 Genesis")
        if not self._source.earth_arrival_rules.allows(
            request.species_id, request.life_stage
        ):
            raise GenesisError("该物种或生命阶段不符合赴地资格")
        species = self._species(request.species_id)
        if species.genesis is None:
            raise GenesisError("领养物种缺少 Genesis 年龄配置")
        maximum_age = (
            species.genesis.terminal_age_years
            - self._source.generation_policy.candidate_age_reserve_years
        )
        if request.age_years_at_adoption > maximum_age:
            raise GenesisError(
                "age_years_at_adoption 必须保留物种生命终点前的 Genesis 策略年限"
            )
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
        batch: GenesisBatch = GenesisEngine(
            catalog=self._catalog,
            generation_policy=self._source.generation_policy,
        ).generate_batch(
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
        region_rng = random.Random(
            self._domain_seed(request.appearance_seed, "birth-region")
        )
        cells = tuple(
            sorted(
                source.spatial_population.eligible_cells(request.species_id),
                key=lambda item: item.cell_id,
            )
        )
        if not cells:
            raise GenesisError(f"资料包没有物种 {request.species_id} 的出生地点")
        eligible_regions = tuple(sorted({cell.region_id for cell in cells}))
        if not eligible_regions:
            raise GenesisError(f"资料包没有物种 {request.species_id} 的可出生区域")
        region_id = eligible_regions[region_rng.randrange(len(eligible_regions))]
        regional_cells = tuple(cell for cell in cells if cell.region_id == region_id)
        cell_rng = random.Random(
            self._domain_seed(request.appearance_seed, f"birth-cell:{region_id}")
        )
        cell = regional_cells[cell_rng.randrange(len(regional_cells))]
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
        square = _first_place_id(source.places, kind="settlement_shared_space")
        waystation = _first_place_id(source.places, kind="departure_facility")
        # Birth and residence establish familiarity, not a travel episode.
        # A learning or work location is not a visit until a corresponding
        # completed activity exists.  The departure station is the one
        # mandatory trip in the pre-arrival route.
        mandatory_visited = _unique((waystation,) if waystation else ())
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
            birth_region_id=cell.region_id,
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
        station_path = self._land_path_to_place(cell.cell_id, waystation)
        station_route_ids = self._registered_routes_on_path(station_path)
        square_station_route = _route_between(source, square, waystation)
        # The station is mandatory, but the named square-to-station route is
        # familiar only when the resident's actual home-to-station path
        # traverses that registered segment.
        mobility = LifeContextMobility(
            visited_place_ids=mandatory_visited,
            familiar_route_ids=station_route_ids,
            visit_counts=tuple((place_id, 1) for place_id in mandatory_visited),
            travel_paths=self._travel_paths(
                context_origin_cell=cell.cell_id,
                visited_place_ids=mandatory_visited,
                station_place_id=waystation,
            ),
        )
        preparation_days = source.earth_arrival_rules.preparation_duration_local_days
        if preparation_days != 3:
            raise GenesisError("赴地前准备固定为一次 3 个本地日的简单培训")
        transition = LifeContextEarthTransition(
            preparation_duration_local_days=preparation_days,
            departure_place_id=waystation or public_home,
            route_id=(
                square_station_route
                if square_station_route in station_route_ids
                else ""
            ),
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

    def _land_path_to_place(
        self, context_origin_cell: str, place_id: str
    ) -> tuple[str, ...]:
        network = self._source.geography_network
        start = _cell_label_from_population_id(context_origin_cell)
        destination = network.cell_for_place(place_id)
        path = network.shortest_land_path(start, destination or "")
        if path is None:
            raise GenesisError(f"出生地到必需地点不存在合法陆路: {start} -> {place_id}")
        return path

    def _registered_routes_on_path(self, path: tuple[str, ...]) -> tuple[str, ...]:
        """Return named route aliases whose complete reviewed path was traversed."""

        network = self._source.geography_network
        result: list[str] = []
        for route in sorted(self._source.routes, key=lambda item: item.route_id):
            start = network.cell_for_place(route.from_place_id)
            destination = network.cell_for_place(route.to_place_id)
            segment = network.shortest_land_path(start or "", destination or "")
            if segment is None or len(segment) < 2 or len(segment) > len(path):
                continue
            reverse_segment = tuple(reversed(segment))
            if any(
                path[index : index + len(segment)] in {segment, reverse_segment}
                for index in range(len(path) - len(segment) + 1)
            ):
                result.append(route.route_id)
        return tuple(result)

    def _personal_mobility(
        self,
        request: GenesisCompileInput,
        candidate: GenesisCandidate,
        context: LifeContext,
        relationships: tuple[RelationshipSeed, ...],
    ) -> LifeContext:
        """Schedule sampled visits against care, route and local-calendar limits."""

        origin = context.origin
        sampled = self._sample_visit_opportunities(
            request,
            candidate,
            region_id=origin.birth_region_id,
            birth_cell_id=origin.birth_cell_id,
            relationships=relationships,
        )
        days_per_year = self._source.geography_network.days_per_local_year
        eligible_life_ages = self._visit_activity_ages(
            request, relationships, minimum_age_years=2
        )
        remaining_days = dict.fromkeys(eligible_life_ages, days_per_year)
        cross_region_days = math.floor(
            days_per_year
            * len(eligible_life_ages)
            * self._source.generation_policy.visit_cross_region_lifetime_fraction
        )
        attempts: list[tuple[int, str, int, tuple[str, ...], VisitOpportunityRule]] = []
        unmade: dict[tuple[str, str], int] = {}
        trip_metrics: dict[str, tuple[int, int, tuple[str, ...]] | None] = {}
        for opportunity, place_ids, count, eligible_ages in sampled:
            metrics = self._opportunity_trip_metrics(
                origin.birth_cell_id, place_ids, opportunity.stay_days
            )
            trip_metrics[opportunity.opportunity_id] = metrics
            if metrics is None:
                unmade[(opportunity.opportunity_id, "不存在完整合法路程")] = count
                continue
            ages = self._schedule_visit_ages(
                request, opportunity, count, eligible_ages=eligible_ages
            )
            for index, age in enumerate(ages):
                priority = self._domain_seed(
                    request.appearance_seed,
                    f"visit-schedule:{opportunity.opportunity_id}:{index}",
                )
                attempts.append(
                    (priority, opportunity.opportunity_id, age, place_ids, opportunity)
                )

        attempts.sort(key=lambda item: (item[0], item[1], item[2]))
        actual_ages: dict[str, list[int]] = {}
        actual_rules: dict[str, tuple[VisitOpportunityRule, tuple[str, ...]]] = {}
        for _, opportunity_id, age, place_ids, opportunity in attempts:
            metrics = trip_metrics.get(opportunity_id)
            if metrics is None:
                reason = "不存在完整合法路程"
            elif remaining_days.get(age, 0) < metrics[1]:
                reason = "超过该年龄年度历法上限"
            else:
                is_cross_region = self._visit_crosses_macro_region(
                    origin.birth_cell_id, place_ids
                )
                if is_cross_region and cross_region_days < metrics[1]:
                    reason = "超过终生跨区旅行时长上限"
                else:
                    remaining_days[age] -= metrics[1]
                    if is_cross_region:
                        cross_region_days -= metrics[1]
                    actual_ages.setdefault(opportunity_id, []).append(age)
                    actual_rules[opportunity_id] = (opportunity, place_ids)
                    continue
            key = (opportunity_id, reason)
            unmade[key] = unmade.get(key, 0) + 1

        base = context.mobility
        visit_counts = dict(base.visit_counts)
        purposes: dict[str, set[str]] = {}
        stay_by_place: dict[str, int] = {}
        observed: list[str] = []
        opportunity_records: list[tuple[str, tuple[str, ...], int, str, int]] = []
        opportunity_route_ids: dict[str, tuple[str, ...]] = {}
        opportunity_travel_days: dict[str, int] = {}
        visited: list[str] = list(base.visited_place_ids)
        for opportunity_id, ages in sorted(actual_ages.items()):
            if not ages:
                continue
            opportunity, place_ids = actual_rules[opportunity_id]
            count = len(ages)
            opportunity_records.append(
                (
                    opportunity_id,
                    place_ids,
                    count,
                    opportunity.purpose,
                    opportunity.stay_days,
                )
            )
            metrics = trip_metrics[opportunity_id]
            assert metrics is not None
            opportunity_travel_days[opportunity_id] = metrics[0]
            opportunity_route_ids[opportunity_id] = metrics[2]
            for index, place_id in enumerate(place_ids):
                if self._place_access(place_id) == "observation_only":
                    observed.append(place_id)
                    continue
                visited.append(place_id)
                # The first place is the opportunity's main destination and
                # receives its sampled repeat count. Conditional in-group
                # sights are sampled once for that opportunity, so don't
                # inflate their personal familiarity with the group's repeats.
                place_visit_count = count if index == 0 else 1
                visit_counts[place_id] = (
                    visit_counts.get(place_id, 0) + place_visit_count
                )
                purposes.setdefault(place_id, set()).add(opportunity.purpose)
                stay_by_place[place_id] = max(
                    stay_by_place.get(place_id, 0), opportunity.stay_days
                )
        visited_ids = _unique(visited)
        familiar_routes = _unique(
            (
                *base.familiar_route_ids,
                *(
                    route_id
                    for route_ids in opportunity_route_ids.values()
                    for route_id in route_ids
                ),
            )
        )
        mobility = replace(
            base,
            visited_place_ids=visited_ids,
            familiar_route_ids=familiar_routes,
            visit_counts=tuple(sorted(visit_counts.items())),
            visit_purposes=tuple(
                (place_id, ",".join(sorted(values)))
                for place_id, values in sorted(purposes.items())
            ),
            visit_stay_days=tuple(sorted(stay_by_place.items())),
            visit_age_years=tuple(
                (opportunity_id, tuple(sorted(ages)))
                for opportunity_id, ages in sorted(actual_ages.items())
                if ages
            ),
            observed_place_ids=_unique((*base.observed_place_ids, *observed)),
            opportunity_records=tuple(opportunity_records),
            opportunity_route_ids=tuple(sorted(opportunity_route_ids.items())),
            opportunity_travel_days=tuple(sorted(opportunity_travel_days.items())),
            unmade_opportunity_records=tuple(
                (opportunity_id, count, reason)
                for (opportunity_id, reason), count in sorted(unmade.items())
            ),
            travel_paths=self._travel_paths(
                context_origin_cell=origin.birth_cell_id,
                visited_place_ids=visited_ids,
                station_place_id=context.earth_transition.departure_place_id,
            ),
        )
        provisional = replace(context, mobility=mobility, content_hash="")
        return replace(provisional, content_hash=_content_hash(provisional))

    def _visit_activity_ages(
        self,
        request: GenesisCompileInput,
        relationships: tuple[RelationshipSeed, ...],
        *,
        minimum_age_years: int,
    ) -> tuple[int, ...]:
        ages = []
        for age in range(max(2, minimum_age_years), request.age_years_at_adoption + 1):
            if stage_for_age(request.species_id, age, self._catalog) == "youth":
                if not any(
                    relation.role in {"parent", "caregiver"}
                    and "self" in relation.care_recipient_person_ids
                    and (
                        relation.life_status == "alive"
                        or (
                            relation.death_event_age_years is not None
                            and age < relation.death_event_age_years
                        )
                    )
                    for relation in relationships
                ):
                    continue
            ages.append(age)
        return tuple(ages)

    def _opportunity_trip_days(
        self,
        birth_cell_id: str,
        place_ids: tuple[str, ...],
        stay_days: int,
    ) -> int | None:
        metrics = self._opportunity_trip_metrics(birth_cell_id, place_ids, stay_days)
        return metrics[1] if metrics is not None else None

    def _opportunity_trip_metrics(
        self,
        birth_cell_id: str,
        place_ids: tuple[str, ...],
        stay_days: int,
    ) -> tuple[int, int, tuple[str, ...]] | None:
        """Plan an ordered, legal round trip and retain only routes it traverses."""

        origin = _cell_label_from_population_id(birth_cell_id)
        current = origin
        stops = tuple(
            place_id
            for place_id in place_ids
            if self._place_access(place_id) != "observation_only"
        )
        if not stops:
            return None

        travel_days = 0
        route_ids: list[str] = []
        for place_id in stops:
            anchors = self._travel_cells_for_place(place_id)
            legs = tuple((cell, self._travel_leg(current, cell)) for cell in anchors)
            reachable = tuple((cell, leg) for cell, leg in legs if leg is not None)
            if not reachable:
                return None
            destination, leg = min(
                reachable,
                key=lambda item: (item[1][1], item[0]),
            )
            path, days = leg
            travel_days += days
            route_ids.extend(self._registered_routes_on_path(path))
            current = destination

        return_leg = self._travel_leg(current, origin)
        if return_leg is None:
            return None
        return_path, return_days = return_leg
        travel_days += return_days
        route_ids.extend(self._registered_routes_on_path(return_path))
        # Named in-town links may share a sampling cell, so the cell path alone
        # cannot prove them. Endpoints selected in this same trip are evidence.
        route_ids.extend(_routes_for_places(self._source, stops))
        return travel_days, travel_days + stay_days, _unique(route_ids)

    def _travel_cells_for_place(self, place_id: str) -> tuple[str, ...]:
        network = self._source.geography_network
        direct = network.cell_for_place(place_id)
        if direct:
            return (direct,)
        cells: set[str] = set()
        pending = [place_id]
        seen: set[str] = set()
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            for child in self._source.places:
                if child.parent_id != current:
                    continue
                cell = network.cell_for_place(child.place_id)
                if cell:
                    cells.add(cell)
                else:
                    pending.append(child.place_id)
        return tuple(sorted(cells))

    def _travel_leg(
        self, start: str, destination: str
    ) -> tuple[tuple[str, ...], int] | None:
        network = self._source.geography_network
        land = network.shortest_land_path(start, destination)
        if land is not None:
            return land, (len(land) - 1) * network.land_days_per_grid_hop

        island_by_cell = {
            island_cell: (ferry_cell, water_hops)
            for _, island_cell, ferry_cell, water_hops in network.island_destinations
        }
        if destination in island_by_cell:
            ferry_cell, water_hops = island_by_cell[destination]
            land_path = network.shortest_land_path(start, ferry_cell)
            if land_path is not None:
                return (
                    (*land_path, destination),
                    (len(land_path) - 1) * network.land_days_per_grid_hop
                    + water_hops * network.water_days_per_grid_hop,
                )
        if start in island_by_cell:
            ferry_cell, water_hops = island_by_cell[start]
            land_path = network.shortest_land_path(ferry_cell, destination)
            if land_path is not None:
                return (
                    (start, *land_path),
                    water_hops * network.water_days_per_grid_hop
                    + (len(land_path) - 1) * network.land_days_per_grid_hop,
                )
        return None

    def _visit_crosses_macro_region(
        self, birth_cell_id: str, place_ids: tuple[str, ...]
    ) -> bool:
        home_region = self._region_for_cell(
            _cell_label_from_population_id(birth_cell_id)
        )
        home_place = self._place(home_region)
        home_macro = dict(home_place.metadata).get("macro_region", home_region)
        for place_id in place_ids:
            regions: set[str] = set()
            pending = [place_id]
            seen: set[str] = set()
            while pending:
                current = pending.pop()
                if current in seen:
                    continue
                seen.add(current)
                place = self._place(current)
                if place is None:
                    continue
                regions.update(place.aliases)
                cell = self._source.geography_network.cell_for_place(current)
                if cell:
                    regions.add(self._region_for_cell(cell))
                pending.extend(
                    item.place_id
                    for item in self._source.places
                    if item.parent_id == current
                )
            for region_id in regions:
                region_place = self._place(region_id)
                macro = (
                    dict(region_place.metadata).get("macro_region", region_id)
                    if region_place is not None
                    else region_id
                )
                if macro != home_macro:
                    return True
        return False

    def _region_for_cell(self, cell_id: str) -> str:
        if not (cell_id.startswith("R") and "C" in cell_id):
            raise GenesisError(f"地理网格坐标格式无效: {cell_id}")
        row_text, column_text = cell_id[1:].split("C", 1)
        if not row_text.isdigit() or not column_text.isdigit():
            raise GenesisError(f"地理网格坐标格式无效: {cell_id}")
        matrix = self._source.geography_network.region_matrix
        row, column = int(row_text), int(column_text)
        try:
            return matrix[row][column]
        except IndexError as error:
            raise GenesisError(f"地理网格坐标超出范围: {cell_id}") from error

    def _travel_paths(
        self,
        *,
        context_origin_cell: str,
        visited_place_ids: tuple[str, ...],
        station_place_id: str,
    ) -> tuple[tuple[str, tuple[str, ...], int], ...]:
        """Resolve deterministic legal land paths for the lived projection."""

        network = self._source.geography_network
        start = _cell_label_from_population_id(context_origin_cell)
        station = network.cell_for_place(station_place_id)
        if station is None:
            raise GenesisError("赴地基站缺少已登记的网格位置")
        paths: list[tuple[str, tuple[str, ...], int]] = []
        mandatory = network.shortest_land_path(start, station)
        if mandatory is None:
            raise GenesisError(f"出生地到赴地基站不存在合法陆路: {start} -> {station}")
        paths.append(
            (
                "birth_to_earthbound_station",
                mandatory,
                (len(mandatory) - 1) * network.land_days_per_grid_hop,
            )
        )
        place_cells = network.place_cells
        for place_id in sorted(visited_place_ids):
            destination = dict(place_cells).get(place_id)
            if destination is None or destination == start:
                continue
            path = network.shortest_land_path(start, destination)
            if path is not None:
                paths.append(
                    (
                        f"birth_to:{place_id}",
                        path,
                        (len(path) - 1) * network.land_days_per_grid_hop,
                    )
                )
                continue
            island = next(
                (
                    (island_cell, ferry_cell, water_hops)
                    for island_place_id, island_cell, ferry_cell, water_hops in network.island_destinations
                    if island_place_id == place_id and island_cell == destination
                ),
                None,
            )
            if island is None:
                raise GenesisError(
                    f"出生地到已访问地点不存在合法路径: {start} -> {place_id}"
                )
            island_cell, ferry_cell, water_hops = island
            land_path = network.shortest_land_path(start, ferry_cell)
            if land_path is None:
                raise GenesisError(
                    f"出生地到湖泊渡点不存在合法陆路: {start} -> {place_id}"
                )
            combined_path = (*land_path, island_cell)
            paths.append(
                (
                    f"birth_to:{place_id}",
                    combined_path,
                    (len(land_path) - 1) * network.land_days_per_grid_hop
                    + water_hops * network.water_days_per_grid_hop,
                )
            )
        return tuple(paths)

    def _sample_visit_opportunities(
        self,
        request: GenesisCompileInput,
        candidate: GenesisCandidate,
        *,
        region_id: str,
        birth_cell_id: str,
        relationships: tuple[RelationshipSeed, ...],
    ) -> tuple[tuple[VisitOpportunityRule, tuple[str, ...], int, tuple[int, ...]], ...]:
        """Sample bounded visit groups without implying town or restricted access."""

        latent = candidate.personality.candidate.latent
        openness = min(1.0, max(0.0, (latent[0] + 2.0) / 4.0))
        neuroticism = min(1.0, max(0.0, (latent[1] + 2.0) / 4.0))
        extraversion = min(1.0, max(0.0, (latent[2] + 2.0) / 4.0))
        opportunities: list[
            tuple[VisitOpportunityRule, tuple[str, ...], int, tuple[int, ...]]
        ] = []
        selected: set[str] = set()
        place_ids = {place.place_id for place in self._source.places}
        for opportunity in self._source.generation_policy.visit_opportunities:
            if opportunity.home_regions and region_id not in opportunity.home_regions:
                continue
            if opportunity.requires_opportunity_id and (
                opportunity.requires_opportunity_id not in selected
            ):
                continue
            if request.age_years_at_adoption < opportunity.minimum_age_years:
                continue
            base_visit_probability = opportunity.base_visit_probability_for(region_id)
            if base_visit_probability <= 0.0:
                continue
            eligible_ages = self._visit_activity_ages(
                request,
                relationships,
                minimum_age_years=opportunity.minimum_age_years,
            )
            if not eligible_ages:
                continue
            social_multiplier = (
                self._source.generation_policy.visit_social_multiplier_base
                + self._source.generation_policy.visit_social_multiplier_slope
                * extraversion
            )
            curiosity_multiplier = (
                self._source.generation_policy.visit_curiosity_multiplier_base
                + self._source.generation_policy.visit_curiosity_multiplier_slope
                * openness
            )
            risk_multiplier = (
                self._source.generation_policy.visit_risk_multiplier_base
                + self._source.generation_policy.visit_risk_openness_slope * openness
                + self._source.generation_policy.visit_risk_neuroticism_slope
                * neuroticism
            )
            purpose = _weighted_text(
                opportunity.purpose_options(),
                random.Random(
                    self._domain_seed(
                        request.appearance_seed,
                        f"visit-purpose:{opportunity.opportunity_id}",
                    )
                ),
            )
            personality_factor = opportunity.personality_factor_for(purpose)
            personality_multiplier = {
                "social": social_multiplier,
                "curiosity": curiosity_multiplier,
                "risk": risk_multiplier,
            }[personality_factor]
            species_values = tuple(
                value for _, value in opportunity.species_multipliers
            )
            species_scale = max((1.0, *species_values))
            species_factor = (
                opportunity.species_multiplier_for(_species_label(request.species_id))
                / species_scale
            )
            region_values = tuple(value for _, value in opportunity.region_multipliers)
            region_scale = max((1.0, *region_values))
            region_factor = opportunity.region_multiplier_for(region_id) / region_scale
            distance_days = self._opportunity_distance_days(
                birth_cell_id, opportunity.place_ids
            )
            if distance_days is None:
                continue
            distance_multiplier = math.exp(
                -distance_days / opportunity.distance_decay_days
            )
            personality_ceiling = {
                "social": (
                    self._source.generation_policy.visit_social_multiplier_base
                    + self._source.generation_policy.visit_social_multiplier_slope
                ),
                "curiosity": (
                    self._source.generation_policy.visit_curiosity_multiplier_base
                    + self._source.generation_policy.visit_curiosity_multiplier_slope
                ),
                "risk": (
                    self._source.generation_policy.visit_risk_multiplier_base
                    + self._source.generation_policy.visit_risk_openness_slope
                    + max(
                        0.0,
                        self._source.generation_policy.visit_risk_neuroticism_slope,
                    )
                ),
            }[personality_factor]
            personality_factor_probability = min(
                1.0,
                max(
                    0.0,
                    personality_multiplier / max(personality_ceiling, 1e-9),
                ),
            )
            age_factor = min(
                1.0,
                len(eligible_ages) / max(1, request.age_years_at_adoption),
            )
            visit_probability = (
                base_visit_probability
                * distance_multiplier
                * region_factor
                * species_factor
                * age_factor
                * personality_factor_probability
            )
            count = _sample_visit_count(
                visit_probability,
                opportunity.max_repeat_count,
                self._source.generation_policy.visit_repeat_count_power,
                visit_uniform=self._domain_uniform(
                    request.appearance_seed,
                    f"visit-presence:{opportunity.opportunity_id}",
                ),
                count_uniform=self._domain_uniform(
                    request.appearance_seed,
                    f"visit-repeat-count:{opportunity.opportunity_id}",
                ),
            )
            if count == 0:
                continue
            selected_places: list[str] = []
            for index, place_id in enumerate(opportunity.place_ids):
                if place_id not in place_ids:
                    raise GenesisError(
                        f"访问机会引用了未注册地点: {opportunity.opportunity_id}/{place_id}"
                    )
                # A typed geography rule can make a place unavailable for
                # ordinary travel.  Keep observation-only landmarks in the
                # opportunity so the episode can record ``witnessed``; a
                # restricted place without that explicit observation mode
                # must not silently become an entered visit.
                if self._place_access(place_id) == "restricted":
                    continue
                if index == 0:
                    selected_places.append(place_id)
                    continue
                member_probability = opportunity.member_probability_for(place_id)
                member_draw = random.Random(
                    self._domain_seed(
                        request.appearance_seed,
                        f"visit-member:{opportunity.opportunity_id}:{place_id}",
                    )
                ).random()
                if member_draw < member_probability:
                    selected_places.append(place_id)
            if not selected_places:
                continue
            selected.add(opportunity.opportunity_id)
            opportunities.append(
                (
                    replace(opportunity, purpose=purpose),
                    tuple(selected_places),
                    count,
                    eligible_ages,
                )
            )
        return tuple(opportunities)

    def _schedule_visit_ages(
        self,
        request: GenesisCompileInput,
        opportunity: VisitOpportunityRule,
        count: int,
        *,
        eligible_ages: tuple[int, ...],
    ) -> tuple[int, ...]:
        """Allocate opportunities by equal per-year contribution, with replacement."""

        if not eligible_ages:
            return ()
        ages: list[int] = []
        for index in range(count):
            draw = random.Random(
                self._domain_seed(
                    request.appearance_seed,
                    f"visit-age:{opportunity.opportunity_id}:{index}",
                )
            )
            ages.append(eligible_ages[draw.randrange(len(eligible_ages))])
        return tuple(sorted(ages))

    def _opportunity_distance_days(
        self, birth_cell_id: str, place_ids: tuple[str, ...]
    ) -> int | None:
        """Return the round-trip cost to the nearest place in an opportunity."""

        network = self._source.geography_network
        start = _cell_label_from_population_id(birth_cell_id)
        candidates: list[str] = []
        pending = list(place_ids)
        seen: set[str] = set()
        while pending:
            place_id = pending.pop()
            if place_id in seen:
                continue
            seen.add(place_id)
            cell = network.cell_for_place(place_id)
            if cell:
                candidates.append(cell)
            pending.extend(
                place.place_id
                for place in self._source.places
                if place.parent_id == place_id
            )
        costs: list[int] = []
        for destination in candidates:
            path = network.shortest_land_path(start, destination)
            if path is not None:
                costs.append(2 * (len(path) - 1) * network.land_days_per_grid_hop)
                continue
            island = next(
                (
                    (island_cell, ferry_cell, water_hops)
                    for _, island_cell, ferry_cell, water_hops in network.island_destinations
                    if island_cell == destination
                ),
                None,
            )
            if island is None:
                continue
            _, ferry_cell, water_hops = island
            land_path = network.shortest_land_path(start, ferry_cell)
            if land_path is not None:
                costs.append(
                    2
                    * (
                        (len(land_path) - 1) * network.land_days_per_grid_hop
                        + water_hops * network.water_days_per_grid_hop
                    )
                )
        return min(costs) if costs else None

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
        self,
        context: LifeContext,
        species_id: str,
        episodes: tuple[EpisodeSeed, ...],
        *,
        seed: int,
    ) -> tuple[tuple[PersonalKnowledgeEntry, ...], tuple[KnowledgeDecisionTrace, ...]]:
        required = set(self._source.earth_arrival_rules.required_knowledge_ids)
        post_arrival = set(self._source.earth_arrival_rules.post_arrival_knowledge_ids)
        selected: list[PersonalKnowledgeEntry] = []
        traces: list[KnowledgeDecisionTrace] = []
        facts = {fact.fact_id: fact for fact in self._source.knowledge}
        missing_required = sorted((required | post_arrival) - facts.keys())
        if missing_required:
            raise GenesisError(
                "赴地规则引用了未发布的必修知识: " + ", ".join(missing_required)
            )
        for fact in self._source.knowledge:
            access = _access_for(fact, species_id)
            if access == "denied":
                traces.append(
                    KnowledgeDecisionTrace(
                        fact.fact_id, access, "none", "none", "资格不符"
                    )
                )
                continue
            eligible = all(
                self._condition_satisfied(condition, context, episodes)
                for condition in fact.conditions
            )
            if fact.fact_id in post_arrival and not eligible:
                traces.append(
                    KnowledgeDecisionTrace(
                        fact.fact_id,
                        access,
                        "none",
                        "not_yet_eligible",
                        "抵达事件尚未完成",
                    )
                )
                continue
            mandatory = fact.fact_id in required or fact.fact_id in post_arrival
            if not mandatory and not eligible:
                traces.append(
                    KnowledgeDecisionTrace(
                        fact.fact_id, access, "none", "not_eligible", "来源条件未满足"
                    )
                )
                continue
            if fact.status == "unknown-boundary" or fact.level == "unknown":
                if mandatory:
                    raise GenesisError(f"赴地必修知识 {fact.fact_id} 不能是未知边界")
                mastery_level: Literal["full", "partial", "reference_only", "none"] = (
                    "reference_only"
                )
                epistemic_kind = "unknown_boundary"
                acquired_via = "public_boundary"
                decision = "boundary"
            else:
                if fact.mastery_difficulty == "medium" and not mandatory:
                    probability = (
                        self._source.generation_policy.medium_knowledge_probability
                    )
                    draw = random.Random(
                        self._domain_seed(seed, f"knowledge:{fact.fact_id}")
                    ).random()
                    if draw >= probability:
                        traces.append(
                            KnowledgeDecisionTrace(
                                fact.fact_id,
                                access,
                                "eligible",
                                "not_mastered",
                                "中等掌握难度的稳定抽样未通过",
                            )
                        )
                        continue
                mastery_level = "full"
                epistemic_kind = fact.epistemic_kind
                acquired_via = (
                    "earth_program"
                    if fact.fact_id in required
                    else "source_eligibility"
                )
                decision = (
                    "mandatory"
                    if mandatory
                    else (
                        "medium_mastery"
                        if fact.mastery_difficulty == "medium"
                        else "eligible_certain"
                    )
                )
            statement = fact.statement
            importance = max(fact.importance, 0.82) if mandatory else fact.importance
            entry = PersonalKnowledgeEntry(
                knowledge_id=fact.fact_id,
                mastery_level=mastery_level,
                epistemic_kind=epistemic_kind,
                statement_variant_id="full",
                topic_ids=(fact.topic,),
                aliases=fact.aliases,
                compiled_search_terms=fact.retrieval_terms,
                recall_eligible=True,
                acquired_via=acquired_via,
                acquired_stage=context.identity.life_stage,
                acquisition_ref=f"knowledge:{fact.fact_id}",
                consultable_target_ids=(),
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
                acquired_age_years=self._knowledge_acquisition_age(
                    fact, context, episodes
                ),
            )
            selected.append(entry)
            traces.append(
                KnowledgeDecisionTrace(
                    fact.fact_id, access, "eligible", decision, "来源条件全部满足"
                )
            )
        selected = _close_prerequisites(
            selected,
            facts,
            species_id,
            context,
            episodes,
            acquisition_age=self._knowledge_acquisition_age,
        )
        selected_by_id = {entry.knowledge_id: entry for entry in selected}
        missing_after_closure = sorted(required - selected_by_id.keys())
        if missing_after_closure:
            raise GenesisError(
                "赴地必修知识未能形成个人知识: " + ", ".join(missing_after_closure)
            )
        insufficient = sorted(
            fact_id
            for fact_id in required | post_arrival
            if fact_id in selected_by_id
            and selected_by_id[fact_id].mastery_level != "full"
        )
        if insufficient:
            raise GenesisError("必修知识必须达到 full 掌握: " + ", ".join(insufficient))
        return tuple(selected), tuple(traces)

    def _knowledge_acquisition_age(
        self,
        fact: WorldKnowledgeFact,
        context: LifeContext,
        episodes: tuple[EpisodeSeed, ...],
    ) -> int:
        """Return the earliest age at which all declared conditions hold.

        Genesis records the earliest evidence age for each condition and then
        waits for the slowest conjunctive condition.  A fact without
        conditions is baseline knowledge available from early life; it is
        intentionally not backdated to a precise birthday.
        """

        condition_ages: list[int] = []
        for condition in fact.conditions:
            candidate_ages: list[int] = []
            if condition.kind == "place":
                target_id = condition.value("id")
                contact = condition.value("contact")
                if contact == "residence":
                    candidate_ages.append(1)
                else:
                    for episode in episodes:
                        matched = (
                            target_id in episode.place_ids
                            or target_id in episode.observed_place_ids
                            if contact in {"entered", "exterior_view"}
                            else any(
                                self._is_place_within(place_id, target_id)
                                for place_id in (
                                    *episode.place_ids,
                                    *episode.observed_place_ids,
                                )
                            )
                        )
                        if not matched:
                            continue
                        candidate_ages.extend(
                            episode.visit_age_years
                            or (
                                (episode.age_years_at_event,)
                                if episode.age_years_at_event is not None
                                else ()
                            )
                        )
            elif condition.kind == "route":
                route_id = condition.value("id")
                for episode in episodes:
                    if route_id not in episode.route_ids:
                        continue
                    candidate_ages.extend(
                        episode.visit_age_years
                        or (
                            (episode.age_years_at_event,)
                            if episode.age_years_at_event is not None
                            else ()
                        )
                    )
            elif condition.kind == "experience":
                if condition.value("id") == "earth_arrival":
                    candidate_ages.extend(
                        episode.age_years_at_event
                        for episode in episodes
                        if episode.theme_id == "arrival-nest"
                        and episode.age_years_at_event is not None
                    )
            elif condition.kind == "vocation":
                if condition.value("id") == context.vocation.vocation_id:
                    candidate_ages.append(
                        max(1, context.identity.age_years_at_adoption)
                    )
            if not candidate_ages:
                # The caller already checked eligibility.  Keeping the age at
                # the current anchor is safer than fabricating an earlier
                # prerequisite event when a source condition has no episode
                # projection yet.
                candidate_ages.append(context.identity.age_years_at_adoption)
            # A repeated visit does not postpone acquisition: the first
            # evidence satisfying this condition is enough.  Multiple
            # conditions are conjunctive, so the fact becomes available once
            # the slowest condition has its earliest evidence.
            condition_ages.append(min(candidate_ages))
        return min(
            context.identity.age_years_at_adoption,
            max(condition_ages, default=1),
        )

    def _condition_satisfied(
        self,
        condition: KnowledgeCondition,
        context: LifeContext,
        episodes: tuple[EpisodeSeed, ...],
    ) -> bool:
        if condition.kind == "place":
            target_id = condition.value("id")
            contact = condition.value("contact")
            target = self._place(target_id)
            if target is None:
                return False
            if contact == "residence":
                return context.origin.birth_region_id == target_id or (
                    context.origin.birth_region_id in target.aliases
                )
            if contact == "public_area_visit":
                return any(
                    self._is_place_within(place_id, target_id)
                    for place_id in context.mobility.visited_place_ids
                )
            if contact in {"exterior_view", "entered"}:
                return target_id in (
                    context.mobility.visited_place_ids
                    if contact == "entered"
                    else (
                        *context.mobility.visited_place_ids,
                        *context.mobility.observed_place_ids,
                    )
                )
            # Merely living near a landmark does not prove participation in its tradition.
            return False
        if condition.kind == "route":
            return (
                condition.value("id") in context.mobility.familiar_route_ids
                and condition.value("extent") == "full"
                and condition.value("status") == "traversed"
            )
        if condition.kind == "experience":
            return (
                condition.value("id") == "earth_arrival"
                and condition.value("status") == "completed"
                and condition.value("outcome") == "arrived_on_earth"
                and any(episode.theme_id == "arrival-nest" for episode in episodes)
            )
        if condition.kind == "vocation":
            values = {
                "id": context.vocation.vocation_id,
                "proficiency": context.vocation.proficiency_band,
                "workplace": context.vocation.workplace_place_id,
            }
            return all(
                values.get(key, "") == value for key, value in condition.attributes
            )
        return False

    def _is_place_within(self, place_id: str, target_id: str) -> bool:
        current_id = place_id
        seen: set[str] = set()
        while current_id and current_id not in seen:
            if current_id == target_id:
                return True
            seen.add(current_id)
            place = self._place(current_id)
            if place is None:
                return False
            current_id = place.parent_id
        return False

    def _eligible_episode_themes(
        self, context: LifeContext
    ) -> tuple[EpisodeTheme, ...]:
        # The package's apprenticeship_refs name available rules, not a
        # resident's lived apprenticeship. A teacher-backed theme therefore
        # needs an actual vocation in this person's life context.
        themes = tuple(
            sorted(
                (
                    theme
                    for theme in self._source.episode_themes
                    if context.identity.life_stage in theme.life_stages
                    and context.identity.age_years_at_adoption >= theme.min_age_years
                    and (
                        "teacher" not in theme.required_roles
                        or context.vocation.vocation_id
                    )
                ),
                key=lambda item: (item.order, item.theme_id),
            )
        )
        if not themes:
            raise GenesisError("资料包没有匹配当前年龄和生命阶段的经历主题")
        return themes

    def _selected_episode_themes(
        self,
        request: GenesisCompileInput,
        context: LifeContext,
    ) -> tuple[EpisodeTheme, ...]:
        eligible = self._eligible_episode_themes(context)
        selected = sorted(
            (theme for theme in eligible if theme.required),
            key=lambda item: (item.order, item.theme_id),
        )
        if context.identity.life_stage == "youth":
            if not selected:
                raise GenesisError("幼体没有可由实际生活支持的经历，不能补造经历")
        else:
            target = max(
                self._source.generation_policy.normal_episode_minimum,
                len(selected),
            )
            if len(eligible) < target:
                raise GenesisError(
                    f"当前生命阶段只有 {len(eligible)} 段有来源的可行经历，无法满足通常至少 {target} 段；不补造经历"
                )
            remaining = [theme for theme in eligible if theme not in selected]
            while len(selected) < target:
                index = len(selected)
                chosen = _weighted_choice(
                    tuple(remaining),
                    random.Random(
                        self._domain_seed(
                            request.appearance_seed, f"episode-theme:{index}"
                        )
                    ),
                )
                selected.append(chosen)
                remaining.remove(chosen)
        return tuple(sorted(selected, key=lambda item: (item.order, item.theme_id)))

    def _relationships(
        self,
        request: GenesisCompileInput,
        context: LifeContext,
    ) -> tuple[RelationshipSeed, ...]:
        themes = self._selected_episode_themes(request, context)
        rules = tuple(
            sorted(
                self._source.relationship_archetypes, key=lambda item: item.archetype_id
            )
        )
        if not rules:
            raise GenesisError("资料包没有 RelationshipArchetypeRules")

        theme_ids_by_role: dict[str, set[str]] = {}
        for theme in themes:
            for role in theme.required_roles:
                theme_ids_by_role.setdefault(role, set()).add(theme.theme_id)
        required_roles = tuple(
            role
            for role in sorted(theme_ids_by_role)
            if role not in {"family", "friend"}
        )

        def compatible_rules(role: str) -> tuple[RelationshipArchetype, ...]:
            compatible = tuple(
                rule
                for rule in rules
                if rule.role == role
                and (
                    not rule.life_stages
                    or context.identity.life_stage in rule.life_stages
                )
                and (
                    not rule.episode_theme_ids
                    or theme_ids_by_role.get(role, set()) <= set(rule.episode_theme_ids)
                )
            )
            if role == "family":
                same_species = tuple(
                    rule
                    for rule in compatible
                    if _species_label(request.species_id) in rule.person_species_ids
                )
                compatible = same_species or compatible
            if not compatible:
                raise GenesisError(f"资料包没有满足经历角色的关系原型: {role}")
            return compatible

        family_rule = _weighted_choice(
            compatible_rules("family"),
            random.Random(self._domain_seed(request.appearance_seed, "family-rule")),
        )
        friend_rules = compatible_rules("friend")
        selected_rules: list[RelationshipArchetype] = []
        for role in required_roles:
            selected_rules.append(
                _weighted_choice(
                    compatible_rules(role),
                    random.Random(
                        self._domain_seed(
                            request.appearance_seed, f"relationship-role:{role}"
                        )
                    ),
                )
            )
        names_by_species: dict[str, tuple[str, ...]] = {}
        name_counters: dict[str, int] = {}
        result: list[RelationshipSeed] = []
        used_person_ids: set[str] = set()

        def generated_name(person_species_id: str) -> str:
            if person_species_id not in names_by_species:
                names_by_species[person_species_id] = self._generated_names_for_species(
                    request,
                    person_species_id,
                    max(16, len(selected_rules) + 8),
                )
            index = name_counters.get(person_species_id, 0)
            pool = names_by_species[person_species_id]
            name_counters[person_species_id] = index + 1
            return pool[index % len(pool)]

        def add_family_member(
            *,
            person_id: str,
            role: str,
            person_gender: str,
            age_years: int,
            minimum_survival_age: int = 0,
            importance: float,
            shared_fact: str,
            birth_order: int | None = None,
            relationship_start_age: int | None = None,
            rule: RelationshipArchetype = family_rule,
            caregiver_person_ids: tuple[str, ...] = (),
            care_recipient_person_ids: tuple[str, ...] = (),
        ) -> None:
            if person_id in used_person_ids:
                raise GenesisError(f"家庭图生成了重复人物: {person_id}")
            used_person_ids.add(person_id)
            terminal = self._species(request.species_id).genesis.terminal_age_years
            death_age = _sample_conditioned_death_age(
                terminal_age=terminal,
                minimum_survival_age=minimum_survival_age,
                cdf_power=policy.family_lifespan_cdf_power,
                uniform=self._domain_uniform(
                    request.appearance_seed, f"lifespan:{person_id}"
                ),
            )
            life_status = "deceased" if age_years >= death_age else "alive"
            recorded_death_age = death_age if life_status == "deceased" else None
            birth_event_age = main_age - age_years
            if not 1 <= birth_event_age <= main_age:
                birth_event_age = None
            death_event_age = (
                main_age - (age_years - death_age)
                if recorded_death_age is not None
                else None
            )
            if death_event_age is not None and not 1 <= death_event_age <= main_age:
                death_event_age = None
            person_species_id = (
                _species_label(request.species_id)
                if role not in {"friend", "teacher", "neighbor"}
                else rule.person_species_ids[0]
            )
            display_name = generated_name(person_species_id)
            result.append(
                RelationshipSeed(
                    person_id=person_id,
                    display_name=display_name,
                    role=role,
                    initial_trust=rule.initial_trust,
                    shared_facts=(shared_fact,),
                    unknown_facts=("对方没有在共同经历中告诉我的完整生活。",),
                    relationship_id=f"rel:{person_id}",
                    subject_id=f"elfie:{request.elfie_id}",
                    object_id=person_id,
                    object_kind="elfie",
                    direction="elfie_to_elfie",
                    familiarity=rule.familiarity,
                    importance=importance,
                    aliases=(display_name, role),
                    retrieval_terms=(role, person_id, person_species_id),
                    episode_ids=(),
                    source="genesis_family_graph"
                    if role
                    in {
                        "parent",
                        "sibling",
                        "partner",
                        "child",
                        "grandparent",
                        "aunt_uncle",
                    }
                    else "genesis_relationship_plan",
                    source_ref=f"relationship:{person_id}",
                    source_version="genesis-relationship.v0.4",
                    certainty="high",
                    version=1,
                    related_species_id=person_species_id,
                    age_band_at_genesis=context.identity.life_stage,
                    home_place_id=context.origin.predeparture_home_place_id,
                    vocation_id=rule.vocation_id,
                    person_species_id=person_species_id,
                    age_years_at_genesis=(
                        max(0, age_years) if life_status == "alive" else None
                    ),
                    birth_order=birth_order,
                    relationship_start_age=relationship_start_age,
                    person_gender=person_gender,
                    life_status=life_status,
                    death_age_years_at_genesis=recorded_death_age,
                    birth_event_age_years=birth_event_age,
                    death_event_age_years=death_event_age,
                    competency_ids=rule.competency_ids,
                    eligible_episode_theme_ids=rule.episode_theme_ids,
                    caregiver_person_ids=caregiver_person_ids,
                    care_recipient_person_ids=care_recipient_person_ids,
                )
            )

        main_age = context.identity.age_years_at_adoption
        parent_gap = self._source.generation_policy.family_parent_min_age_gap_years
        max_children = self._source.generation_policy.family_max_children
        policy = self._source.generation_policy
        family_importance = policy.relationship_importance(
            "parent", family_rule.importance
        )
        sibling_importance = policy.relationship_importance(
            "sibling", family_rule.importance
        )
        relationship_decay = math.exp(-policy.relationship_layer_decay_lambda)

        def draw_child_target(stable_id: str) -> int:
            return _weighted_integer(
                self._source.generation_policy.family_child_count_distribution,
                random.Random(
                    self._domain_seed(
                        request.appearance_seed,
                        f"family-child-count:{stable_id}",
                    )
                ),
            )

        def choose_child_ages(
            *,
            anchor_age: int,
            target: int,
            parent_current_ages: tuple[int, int],
            union_id: str,
        ) -> tuple[int, ...]:
            """Uniformly choose a bounded legal child-year subset containing anchor."""

            terminal = self._species(request.species_id).genesis.terminal_age_years
            max_child_age = min(parent_current_ages) - parent_gap
            legal_years = tuple(
                age
                for age in range(max_child_age + 1)
                if all(
                    parent_age - age >= parent_gap
                    and parent_age - age < terminal
                    and stage_for_age(
                        request.species_id,
                        parent_age - age,
                        self._catalog,
                    )
                    != "elder"
                    for parent_age in parent_current_ages
                )
            )
            if anchor_age not in legal_years:
                raise GenesisError("家庭锚定子女年份不满足父母生育年龄")
            count = min(max_children, max(1, target), len(legal_years))
            other_years = _uniform_hash_subset(
                tuple(age for age in legal_years if age != anchor_age),
                count - 1,
                lambda age: self._domain_seed(
                    request.appearance_seed,
                    f"family-child-year:{union_id}:{age}",
                ),
            )
            return tuple(sorted((anchor_age, *other_years), reverse=True))

        def sample_legal_years(
            legal_years: tuple[int, ...], count: int, union_id: str
        ) -> tuple[int, ...]:
            """Choose a uniform, stable subset from a union's legal birth years."""

            return _uniform_hash_subset(
                legal_years,
                count,
                lambda age: self._domain_seed(
                    request.appearance_seed,
                    f"family-child-year:{union_id}:{age}",
                ),
            )

        parent_ids = ["family-parent-1", "family-parent-2"]
        parent_child_target = draw_child_target("parents")
        # The protagonist is anchored into one shared parent-child set.  The
        # target distribution is drawn once per union; each additional child
        # occupies a distinct legal birth year and gets its rank from that
        # year.  This keeps both parents and all siblings on the same graph
        # instead of independently re-drawing the same family from each node.
        parent_current_ages = (
            main_age + parent_gap + 1,
            main_age + parent_gap + 2,
        )
        child_ages = choose_child_ages(
            anchor_age=main_age,
            target=parent_child_target,
            parent_current_ages=parent_current_ages,
            union_id="parents",
        )
        add_family_member(
            person_id=parent_ids[0],
            role="parent",
            person_gender="female",
            age_years=main_age + parent_gap + 1,
            minimum_survival_age=max(
                main_age + parent_gap + 1 - min(child_ages),
                parent_gap + 1 + min(2, main_age),
            ),
            importance=family_importance,
            shared_fact="她是我的父母之一，曾参与我的早期照护。",
            care_recipient_person_ids=("self",),
        )
        add_family_member(
            person_id=parent_ids[1],
            role="parent",
            person_gender="male",
            age_years=main_age + parent_gap + 2,
            minimum_survival_age=max(
                main_age + parent_gap + 2 - min(child_ages),
                parent_gap + 2 + min(2, main_age),
            ),
            importance=family_importance,
            shared_fact="他是我的父母之一，曾参与我的早期照护。",
            care_recipient_person_ids=("self",),
        )

        sibling_ids: list[str] = []
        sibling_order_by_id: dict[str, int] = {}
        for order, sibling_age in enumerate(child_ages, start=1):
            if sibling_age == main_age:
                continue
            sibling_index = len(sibling_ids) + 1
            person_id = f"family-sibling-{sibling_index}"
            sibling_ids.append(person_id)
            sibling_order_by_id[person_id] = order
            add_family_member(
                person_id=person_id,
                role="sibling",
                person_gender="male" if sibling_index % 2 else "female",
                age_years=sibling_age,
                importance=sibling_importance,
                shared_fact="我们是同一对父母的子女，曾共享家庭生活。",
                birth_order=order,
            )

        # Expand only upward from the two direct parents.  Each parent has a
        # separate grandparent union; that union reuses the already-created
        # parent as one child and may add a bounded aunt/uncle set.  We do not
        # recursively expand those new people, which is the width/depth limit
        # from the Genesis design.
        expansion_related: dict[str, set[str]] = {}
        parent_child_orders = tuple(
            sorted(
                (
                    ("self", child_ages.index(main_age) + 1),
                    *sibling_order_by_id.items(),
                ),
                key=lambda item: item[1],
            )
        )
        child_orders_by_parent: dict[str, tuple[tuple[str, int], ...]] = dict.fromkeys(
            parent_ids, parent_child_orders
        )

        def set_birth_order(person_id: str, order: int) -> None:
            for index, relationship in enumerate(result):
                if relationship.person_id == person_id:
                    result[index] = replace(relationship, birth_order=order)
                    return
            raise GenesisError(f"家庭图找不到待设置排行的人物: {person_id}")

        terminal_age = self._species(request.species_id).genesis.terminal_age_years
        for parent_index, parent_id in enumerate(parent_ids, start=1):
            parent_age = main_age + parent_gap + parent_index
            # A parent near the terminal age does not force an implausible
            # grandparent branch merely to make the tree look complete.
            if (
                parent_age + parent_gap + 1 >= terminal_age
                or stage_for_age(request.species_id, parent_age, self._catalog)
                == "elder"
            ):
                continue
            grandparent_ids = [
                f"family-grandparent-{parent_index}-1",
                f"family-grandparent-{parent_index}-2",
            ]
            grandparent_target = _weighted_integer(
                self._source.generation_policy.family_child_count_distribution,
                random.Random(
                    self._domain_seed(
                        request.appearance_seed,
                        f"family-child-count:{parent_id}",
                    )
                ),
            )
            grandparent_ages = (
                parent_age + parent_gap + 1,
                parent_age + parent_gap + 2,
            )
            grandparent_children = choose_child_ages(
                anchor_age=parent_age,
                target=grandparent_target,
                parent_current_ages=grandparent_ages,
                union_id=parent_id,
            )
            parent_order = grandparent_children.index(parent_age) + 1
            set_birth_order(parent_id, parent_order)
            for index, grandparent_id in enumerate(grandparent_ids):
                add_family_member(
                    person_id=grandparent_id,
                    role="grandparent",
                    person_gender="female" if index == 0 else "male",
                    age_years=grandparent_ages[index],
                    minimum_survival_age=(
                        grandparent_ages[index] - min(grandparent_children)
                    ),
                    importance=family_importance * relationship_decay,
                    shared_fact=(
                        "她是我父母一方的父母，我通过家庭关系知道她。"
                        if index == 0
                        else "他是我父母一方的父母，我通过家庭关系知道他。"
                    ),
                )
            aunt_ids: list[str] = []
            aunt_order_by_id: dict[str, int] = {}
            for order, aunt_age in enumerate(grandparent_children, start=1):
                if aunt_age == parent_age:
                    continue
                aunt_id = f"family-aunt-uncle-{parent_index}-{len(aunt_ids) + 1}"
                aunt_ids.append(aunt_id)
                aunt_order_by_id[aunt_id] = order
                add_family_member(
                    person_id=aunt_id,
                    role="aunt_uncle",
                    person_gender="female" if len(aunt_ids) % 2 == 0 else "male",
                    age_years=aunt_age,
                    importance=sibling_importance * relationship_decay,
                    shared_fact="这是我父母一方的兄弟姐妹，属于已知的旁系亲属。",
                    birth_order=order,
                )
            grandparent_child_orders = tuple(
                sorted(
                    ((parent_id, parent_order), *aunt_order_by_id.items()),
                    key=lambda item: item[1],
                )
            )
            for grandparent_id in grandparent_ids:
                child_orders_by_parent[grandparent_id] = grandparent_child_orders
            union_children = {parent_id, *aunt_ids}
            for grandparent_id in grandparent_ids:
                expansion_related.setdefault(grandparent_id, set()).update(
                    {
                        "self",
                        *[item for item in grandparent_ids if item != grandparent_id],
                        *union_children,
                    }
                )
            expansion_related.setdefault(parent_id, set()).update(
                {*grandparent_ids, *aunt_ids}
            )
            for aunt_id in aunt_ids:
                expansion_related.setdefault(aunt_id, set()).update(
                    {
                        *grandparent_ids,
                        parent_id,
                        "self",
                        *[item for item in aunt_ids if item != aunt_id],
                    }
                )

        partner_id: str | None = None
        partner_start_age: int | None = None
        partner_age = 0
        first_birth_age = 0
        partner_child_count = 0
        partner_child_birth_ages: tuple[int, ...] = ()
        if main_age >= policy.family_partner_min_age_years:
            years = main_age - policy.family_partner_min_age_years + 1
            chance = 1.0 - (1.0 - policy.family_partner_annual_probability) ** years
            partner_draw = random.Random(
                self._domain_seed(request.appearance_seed, "family-partner")
            ).random()
            if partner_draw < chance:
                partner_id = "family-partner"
                for elapsed_years in range(years):
                    annualized = 1.0 - (
                        1.0 - policy.family_partner_annual_probability
                    ) ** (elapsed_years + 1)
                    if partner_draw < annualized:
                        partner_start_age = (
                            policy.family_partner_min_age_years + elapsed_years
                        )
                        break
                if partner_start_age is None:
                    raise GenesisError("伴侣抽样缺少合法的首次形成年龄")
                partner_age = max(
                    policy.family_partner_min_age_years,
                    main_age - partner_start_age + policy.family_partner_min_age_years,
                )
                first_birth_age = partner_start_age + 1
                terminal = self._species(request.species_id).genesis.terminal_age_years
                legal_birth_ages = tuple(
                    birth_age
                    for birth_age in range(first_birth_age, main_age + 1)
                    if stage_for_age(request.species_id, birth_age, self._catalog)
                    != "elder"
                    and parent_gap <= partner_age - (main_age - birth_age) < terminal
                    and stage_for_age(
                        request.species_id,
                        partner_age - (main_age - birth_age),
                        self._catalog,
                    )
                    != "elder"
                )
                partner_child_target = draw_child_target("partner")
                partner_child_count = min(
                    partner_child_target,
                    policy.family_max_children,
                    len(legal_birth_ages),
                )
                partner_child_birth_ages = sample_legal_years(
                    legal_birth_ages, partner_child_count, "partner"
                )
                minimum_survival_age = max(
                    partner_age - (main_age - partner_start_age),
                    partner_age - (main_age - max(partner_child_birth_ages))
                    if partner_child_count
                    else 0,
                )
                partner_gender = "female" if request.gender == "male" else "male"
                add_family_member(
                    person_id=partner_id,
                    role="partner",
                    person_gender=partner_gender,
                    age_years=partner_age,
                    minimum_survival_age=minimum_survival_age,
                    importance=family_importance,
                    shared_fact="这是我的伴侣，我们共同承担生活。",
                )
                result[-1] = replace(
                    result[-1], relationship_start_age=partner_start_age
                )

        child_ids: list[str] = []
        if partner_id is not None:
            # The first child can only be born after one complete year of the
            # partnership.  Each later child occupies a different year on the
            # same deterministic timeline.
            if partner_start_age is None:
                raise GenesisError("已有伴侣但缺少关系形成年龄")
            for index, birth_age in enumerate(partner_child_birth_ages):
                person_id = f"family-child-{index + 1}"
                child_ids.append(person_id)
                add_family_member(
                    person_id=person_id,
                    role="child",
                    person_gender="female" if index % 2 else "male",
                    age_years=max(0, main_age - birth_age),
                    importance=family_importance,
                    shared_fact="这是我的子女，我们之间有家庭照护关系。",
                    birth_order=index + 1,
                    caregiver_person_ids=("self",),
                )

        # Friends are selected from actual contact opportunities represented by
        # the published relationship archetypes.  The draw is per candidate,
        # so adding another archetype cannot re-roll or duplicate an existing
        # person.  Keep at most two important friends and force one only when
        # a selected episode has a real friend participant requirement.
        openness = min(
            1.0, max(0.0, (context.identity.personality_anchor[0] + 2.0) / 4.0)
        )
        extraversion = min(
            1.0, max(0.0, (context.identity.personality_anchor[2] + 2.0) / 4.0)
        )
        theme_min_age = {
            theme.theme_id: theme.min_age_years for theme in self._source.episode_themes
        }
        required_friend = any("friend" in theme.required_roles for theme in themes)
        friend_candidates: list[tuple[RelationshipArchetype, float]] = []
        for rule in friend_rules:
            relevant_ages = [
                theme_min_age[theme_id]
                for theme_id in rule.episode_theme_ids
                if theme_id in theme_min_age
            ]
            minimum_age = min(relevant_ages, default=1)
            contact_years = max(1, main_age - minimum_age + 1)
            frequency = 0.5 + 0.5 * min(1.0, contact_years / 4.0)
            purpose_match = 0.5 + 0.5 * openness
            contact_strength = (
                policy.friend_contact_beta
                * contact_years
                * frequency
                * purpose_match
                * (0.8 + 0.4 * extraversion)
                * rule.weight
            )
            probability = 1.0 - math.exp(-contact_strength)
            draw = random.Random(
                self._domain_seed(
                    request.appearance_seed, f"friend-contact:{rule.archetype_id}"
                )
            ).random()
            if draw < probability:
                friend_candidates.append((rule, contact_strength))
        if required_friend and not friend_candidates:
            eligible_rules = tuple(
                rule
                for rule in friend_rules
                if any(theme_id in theme_min_age for theme_id in rule.episode_theme_ids)
            )
            if not eligible_rules:
                raise GenesisError("协作经历没有可用的好友关系原型")
            fallback = max(
                eligible_rules,
                key=lambda rule: (
                    rule.weight,
                    rule.importance,
                    rule.archetype_id,
                ),
            )
            friend_candidates.append((fallback, 0.0))
        selected_friend_rules = sorted(
            friend_candidates,
            key=lambda item: (-item[1], item[0].archetype_id),
        )[: policy.friend_max_count]
        for index, (rule, contact_strength) in enumerate(selected_friend_rules):
            person_id = f"friend-{index + 1}"
            friend_baseline = policy.relationship_importance("friend", rule.importance)
            friend_importance = min(
                1.0,
                friend_baseline
                + (1.0 - friend_baseline)
                * (
                    1.0 - math.exp(-policy.friend_layer_decay_lambda * contact_strength)
                ),
            )
            friend_age = max(1, main_age - (index % 2))
            friend_contact_age = min(
                (
                    theme_min_age[theme_id]
                    for theme_id in rule.episode_theme_ids
                    if theme_id in theme_min_age
                ),
                default=1,
            )
            friend_contact_age += random.Random(
                self._domain_seed(request.appearance_seed, f"friend-age:{person_id}")
            ).randrange(max(1, main_age - friend_contact_age + 1))
            add_family_member(
                person_id=person_id,
                role="friend",
                person_gender="female" if index % 2 else "male",
                age_years=friend_age,
                minimum_survival_age=max(
                    0, friend_age - (main_age - friend_contact_age)
                ),
                importance=friend_importance,
                shared_fact="我们曾在共同生活或共同活动中相识。",
                relationship_start_age=friend_contact_age,
                rule=rule,
            )

        for index, rule in enumerate(selected_rules):
            person_id = rule.archetype_id
            if person_id in used_person_ids:
                person_id = f"{person_id}-{index + 1:02d}"
            used_person_ids.add(person_id)
            species_rng = random.Random(
                self._domain_seed(request.appearance_seed, f"person-species:{index}")
            )
            person_species_id = rule.person_species_ids[
                species_rng.randrange(len(rule.person_species_ids))
            ]
            if person_species_id not in names_by_species:
                names_by_species[person_species_id] = self._generated_names_for_species(
                    request, person_species_id, max(4, len(selected_rules))
                )
            name_index = name_counters.get(person_species_id, 0)
            pool = names_by_species[person_species_id]
            display_name = pool[name_index % len(pool)]
            name_counters[person_species_id] = name_index + 1
            object_kind = "elfie"
            terminal_age = self._species(request.species_id).genesis.terminal_age_years
            person_age = min(terminal_age - 1, max(1, main_age + index))
            contact_age = min(
                (
                    theme_min_age[theme_id]
                    for theme_id in rule.episode_theme_ids
                    if theme_id in theme_min_age
                ),
                default=1,
            )
            contact_age += random.Random(
                self._domain_seed(
                    request.appearance_seed, f"relationship-age:{person_id}"
                )
            ).randrange(max(1, main_age - contact_age + 1))
            minimum_survival_age = max(0, person_age - (main_age - contact_age))
            death_age = _sample_conditioned_death_age(
                terminal_age=self._species(
                    request.species_id
                ).genesis.terminal_age_years,
                minimum_survival_age=minimum_survival_age,
                cdf_power=policy.family_lifespan_cdf_power,
                uniform=self._domain_uniform(
                    request.appearance_seed, f"lifespan:{person_id}"
                ),
            )
            life_status = "deceased" if person_age >= death_age else "alive"
            recorded_death_age = death_age if life_status == "deceased" else None
            birth_event_age = main_age - person_age
            if not 1 <= birth_event_age <= main_age:
                birth_event_age = None
            death_event_age = (
                main_age - (person_age - death_age)
                if recorded_death_age is not None
                else None
            )
            if death_event_age is not None and not 1 <= death_event_age <= main_age:
                death_event_age = None
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
                    object_kind=object_kind,
                    direction=f"elfie_to_{object_kind}",
                    familiarity=rule.familiarity,
                    importance=policy.relationship_importance(
                        rule.role, rule.importance
                    ),
                    aliases=(display_name, rule.role),
                    retrieval_terms=(rule.role, person_id, person_species_id),
                    episode_ids=(),
                    source="genesis_relationship_plan",
                    source_ref=f"relationship:{person_id}",
                    source_version="genesis-relationship.v0.4",
                    certainty="high",
                    version=1,
                    related_species_id=person_species_id,
                    age_band_at_genesis=context.identity.life_stage,
                    home_place_id=context.origin.predeparture_home_place_id,
                    vocation_id=rule.vocation_id,
                    person_species_id=person_species_id,
                    age_years_at_genesis=(
                        person_age if life_status == "alive" else None
                    ),
                    life_status=life_status,
                    death_age_years_at_genesis=recorded_death_age,
                    birth_event_age_years=birth_event_age,
                    death_event_age_years=death_event_age,
                    relationship_start_age=contact_age,
                    competency_ids=rule.competency_ids,
                    eligible_episode_theme_ids=rule.episode_theme_ids,
                )
            )

        related: dict[str, set[str]] = {
            relationship.person_id: set() for relationship in result
        }
        for person_id, linked_ids in expansion_related.items():
            related.setdefault(person_id, set()).update(linked_ids)
        parent_child_ids = {"self", *sibling_ids}
        for person_id in parent_ids:
            related[person_id].update(
                {
                    "self",
                    *[item for item in parent_ids if item != person_id],
                    *sibling_ids,
                }
            )
            related[person_id].update(parent_child_ids)
        for person_id in sibling_ids:
            related[person_id].update(
                {
                    "self",
                    *parent_ids,
                    *[item for item in sibling_ids if item != person_id],
                }
            )
        for child_id in child_ids:
            related[child_id].update({"self", *parent_ids})
        if partner_id is not None:
            related[partner_id].add("self")
            related[partner_id].update(child_ids)
            for child_id in child_ids:
                related[child_id].update({"self", partner_id})
        result = [
            replace(
                relationship,
                related_person_ids=tuple(
                    sorted(related.get(relationship.person_id, ()))
                ),
                child_birth_orders=child_orders_by_parent.get(
                    relationship.person_id, relationship.child_birth_orders
                ),
                caregiver_person_ids=(
                    tuple(
                        sorted(
                            {
                                *relationship.caregiver_person_ids,
                                *(
                                    (partner_id,)
                                    if relationship.role == "child"
                                    and partner_id is not None
                                    else ()
                                ),
                            }
                        )
                    )
                    if relationship.role == "child"
                    else relationship.caregiver_person_ids
                ),
                care_recipient_person_ids=(
                    tuple(
                        sorted(
                            {
                                *relationship.care_recipient_person_ids,
                                *(
                                    {"self", *sibling_ids, *child_ids}
                                    if relationship.role == "parent"
                                    else {"self", *child_ids}
                                    if relationship.role == "partner"
                                    else set()
                                ),
                            }
                        )
                    )
                    if relationship.role in {"parent", "partner"}
                    else relationship.care_recipient_person_ids
                ),
            )
            for relationship in result
        ]

        result.append(
            RelationshipSeed(
                person_id=f"owner-person-{request.owner_reference}",
                display_name="主人",
                role="owner",
                initial_trust=0.65,
                shared_facts=(
                    "主人是负责照料我的地球人。",
                    "我们会通过真实相处逐步建立信任。",
                ),
                unknown_facts=("主人的完整生活、过去和每天的想法。",),
                relationship_id=f"rel:owner-person-{request.owner_reference}",
                subject_id=f"elfie:{request.elfie_id}",
                object_id=f"owner-person-{request.owner_reference}",
                object_kind="person",
                direction="elfie_to_person",
                familiarity="acquainted",
                importance=0.95,
                aliases=("主人", request.owner_reference),
                retrieval_terms=("主人", "照料"),
                episode_ids=(),
                source="adoption_decision",
                source_ref="adoption:accepted",
                source_version="adoption-decision.v1",
                certainty="high",
                version=1,
                age_band_at_genesis=context.identity.life_stage,
                life_status="alive",
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
                object_kind="group",
                direction="elfie_to_group",
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
                life_status="alive",
            )
        )
        return tuple(result)

    def _visit_episodes(
        self,
        context: LifeContext,
    ) -> tuple[EpisodeSeed, ...]:
        """Materialize each sampled opportunity as an auditable Episode."""

        result: list[EpisodeSeed] = []
        for (
            opportunity_id,
            place_ids,
            visit_count,
            purpose,
            stay_days,
        ) in context.mobility.opportunity_records:
            if not place_ids:
                continue
            seed_id = f"visit:{opportunity_id}"
            visited_place_ids = tuple(
                place_id
                for place_id in place_ids
                if self._place_access(place_id) != "observation_only"
            )
            observed_place_ids = tuple(
                place_id
                for place_id in place_ids
                if self._place_access(place_id) == "observation_only"
            )
            main_place_ids = visited_place_ids[:1]
            incidental_place_ids = visited_place_ids[1:]
            route_ids = dict(context.mobility.opportunity_route_ids).get(
                opportunity_id, ()
            )
            travel_days = dict(context.mobility.opportunity_travel_days).get(
                opportunity_id, 0
            )
            visit_age_years = dict(context.mobility.visit_age_years).get(
                opportunity_id, ()
            )
            age_label = (
                "、".join(f"{age}岁" for age in visit_age_years)
                if visit_age_years
                else "未知年龄"
            )
            result.append(
                EpisodeSeed(
                    seed_id=seed_id,
                    content=(
                        (
                            f"我因为{purpose}去过{'、'.join(self._label(place_id) for place_id in main_place_ids)}，累计访问{visit_count}次。"
                            if main_place_ids
                            else ""
                        )
                        + (
                            f"{'其中一次' if visit_count > 1 else '同一次'}行程还顺道到过{'、'.join(self._label(place_id) for place_id in incidental_place_ids)}。"
                            if incidental_place_ids
                            else ""
                        )
                        + (
                            f"{'其中一次' if visit_count > 1 else '同一次'}行程还从可到达的位置看见了{'、'.join(self._label(place_id) for place_id in observed_place_ids)}。"
                            if observed_place_ids
                            else ""
                        )
                        + f"完整组合行程往返约{travel_days}天、停留约{stay_days}天；主要地点的访问发生在{age_label}。"
                    ),
                    source="personal_memory",
                    source_ref=f"visit-opportunity:{opportunity_id}",
                    source_version=(
                        f"genesis-visit:{self._source.generation_policy.visit_sampler_version}"
                    ),
                    scope="elfie",
                    topic="biography.visits",
                    aliases=(opportunity_id, purpose),
                    retrieval_terms=("访问", purpose, *place_ids),
                    certainty="high",
                    temporal_label="抵达前",
                    life_stage=context.identity.life_stage,
                    place_ids=visited_place_ids,
                    observed_place_ids=observed_place_ids,
                    route_ids=route_ids,
                    result=f"完成了{purpose}相关的实际访问",
                    feeling="我记得这次出行的主要目的和到过的地方。",
                    impact="我对主要地点形成了与访问次数相称的熟悉程度，对顺道到访的地点只留下一次接触的熟悉度。",
                    related_ids=(),
                    emotional_tone="curiosity",
                    emotion_intensity=0.55,
                    importance=min(1.0, 0.55 + 0.08 * visit_count),
                    theme_id="visit-opportunity",
                    age_years_at_event=min(visit_age_years)
                    if visit_age_years
                    else None,
                    visit_count=visit_count,
                    travel_days=travel_days,
                    stay_days=stay_days,
                    visit_age_years=visit_age_years,
                    purposes=(purpose,),
                )
            )
        return tuple(result)

    def _place_access(self, place_id: str) -> str:
        for rule in self._source.access_rules:
            if rule.place_id != place_id:
                continue
            if rule.observation_only:
                return "observation_only"
            if not rule.ordinary_travel_allowed:
                return "restricted"
        place = self._place(place_id)
        if place is None:
            return ""
        return dict(place.metadata).get("access", "")

    def _family_episodes(
        self,
        request: GenesisCompileInput,
        context: LifeContext,
        relationships: tuple[RelationshipSeed, ...],
    ) -> tuple[EpisodeSeed, ...]:
        """Materialize only family events the protagonist could have lived."""

        main_age = context.identity.age_years_at_adoption
        policy = self._source.generation_policy
        candidates: list[tuple[int, RelationshipSeed, str, str]] = []
        for relationship in relationships:
            if (
                relationship.role == "child"
                and relationship.birth_event_age_years is not None
            ):
                event_age = relationship.birth_event_age_years
                if 1 <= event_age <= main_age:
                    candidates.append(
                        (
                            event_age,
                            relationship,
                            "child_birth",
                            f"{relationship.display_name}出生",
                        )
                    )
            elif (
                relationship.role == "sibling"
                and relationship.birth_event_age_years is not None
            ):
                event_age = relationship.birth_event_age_years
                if 1 <= event_age <= main_age:
                    candidates.append(
                        (
                            event_age,
                            relationship,
                            "sibling_birth",
                            f"{relationship.display_name}出生",
                        )
                    )
            elif relationship.role == "partner":
                event_age = relationship.relationship_start_age or min(
                    main_age, policy.family_partner_min_age_years
                )
                if event_age >= 1:
                    candidates.append(
                        (
                            event_age,
                            relationship,
                            "partnership",
                            f"和{relationship.display_name}建立伴侣关系",
                        )
                    )
            if (
                relationship.life_status == "deceased"
                and relationship.death_age_years_at_genesis is not None
                and relationship.death_event_age_years is not None
                and relationship.importance >= 0.65
                and relationship.familiarity != "heard"
            ):
                candidates.append(
                    (
                        relationship.death_event_age_years,
                        relationship,
                        "death",
                        f"得知{relationship.display_name}去世",
                    )
                )
        ordered = sorted(
            candidates,
            key=lambda item: (item[0], item[1].person_id, item[2]),
        )
        episodes: list[EpisodeSeed] = []
        for event_age, relationship, event_kind, label in ordered:
            stage = stage_for_age(request.species_id, event_age, self._catalog)
            if event_kind == "child_birth":
                content = f"我在{event_age}岁左右经历了{label}，这段家庭变化让我开始承担新的照护责任。"
                impact = "我记得家庭成员的出生会改变日常照护和相处方式。"
            elif event_kind == "sibling_birth":
                content = (
                    f"我在{event_age}岁左右经历了家中{label}，我们后来共享家庭生活。"
                )
                impact = "我记得家庭成员的变化需要通过共同生活逐步熟悉。"
            elif event_kind == "death":
                content = (
                    f"我在{event_age}岁左右得知{relationship.display_name}去世。"
                    "我记得这段送别，但不知道的死因和细节不会被补写。"
                )
                impact = "这次离别改变了我与家人的相处和记忆。"
            else:
                content = f"我在{event_age}岁左右{label}，开始和对方共同承担生活。"
                impact = "我记得重要关系需要在共同生活中逐步建立。"
            episodes.append(
                EpisodeSeed(
                    seed_id=f"family-event:{event_kind}:{relationship.person_id}",
                    content=content,
                    source="personal_memory",
                    source_ref=f"family-event:{event_kind}",
                    source_version="genesis-family-episode.v0.2",
                    scope="elfie",
                    topic="biography.family",
                    aliases=(event_kind, relationship.role),
                    retrieval_terms=("家庭", label, relationship.role),
                    certainty="high",
                    temporal_label="抵达前",
                    life_stage=stage,
                    place_ids=(
                        (context.origin.childhood_home_place_id,)
                        if event_kind != "death"
                        else ()
                    ),
                    person_ids=(relationship.person_id,),
                    result=label,
                    feeling="我记得这段关系变化，但不会把未知细节当成亲历。",
                    impact=impact,
                    emotional_tone="belonging",
                    emotion_intensity=min(1.0, relationship.importance),
                    importance=min(1.0, 0.65 + relationship.importance * 0.25),
                    theme_id=f"family-event:{event_kind}",
                    age_years_at_event=event_age,
                )
            )
        return tuple(episodes)

    def _episodes(
        self,
        request: GenesisCompileInput,
        context: LifeContext,
        relationships: tuple[RelationshipSeed, ...],
    ) -> tuple[EpisodeSeed, ...]:
        result: list[EpisodeSeed] = []
        caregivers = tuple(
            item
            for item in relationships
            if item.role in {"parent", "caregiver"}
            and "self" in item.care_recipient_person_ids
        )
        if caregivers:
            caregiver_ids = tuple(item.person_id for item in caregivers)
            caregiver_names = "、".join(item.display_name for item in caregivers)
            result.append(
                EpisodeSeed(
                    seed_id="early-home",
                    content=(
                        f"我幼年时由{caregiver_names}承担早期照护，我在家中长大。"
                    ),
                    source_ref="genesis:family-care",
                    source_version="genesis-family-episode.v0.3",
                    topic="biography.family",
                    aliases=("幼年", "家庭照护"),
                    retrieval_terms=("家庭", "照护", "家"),
                    temporal_label="幼年时期（具体年龄未知）",
                    life_stage=stage_for_age(request.species_id, 1, self._catalog),
                    place_ids=(context.origin.childhood_home_place_id,),
                    person_ids=caregiver_ids,
                    result=f"我的早期照护者是{caregiver_names}。",
                    feeling="我记得家庭照护是我早期生活的一部分。",
                    impact="这段照护关系构成了我早期的家庭生活。",
                    emotional_tone="belonging",
                    emotion_intensity=0.8,
                    importance=0.85,
                    theme_id="early-home",
                )
            )

        for relationship in relationships:
            if relationship.relationship_start_age is None:
                continue
            if relationship.role in {
                "parent",
                "sibling",
                "partner",
                "child",
                "grandparent",
                "aunt_uncle",
            }:
                continue
            event_age = relationship.relationship_start_age
            if event_age > context.identity.age_years_at_adoption:
                raise GenesisError("关系相识年龄不能晚于当前年龄")
            place_id = (
                relationship.home_place_id or context.origin.predeparture_home_place_id
            )
            role_label = {
                "friend": "朋友",
                "teacher": "师长",
                "neighbor": "邻居",
                "route_keeper": "路线同行者",
                "learning_keeper": "学习伙伴",
                "elder": "长者",
            }.get(relationship.role, relationship.role)
            shared_fact = (
                relationship.shared_facts[0]
                if relationship.shared_facts
                else f"我与{relationship.display_name}建立了{role_label}关系。"
            )
            result.append(
                EpisodeSeed(
                    seed_id=f"relationship-start:{relationship.person_id}",
                    content=(
                        f"我在{event_age}岁左右于{self._label(place_id)}附近"
                        f"与{relationship.display_name}相识。{shared_fact}"
                    ),
                    source_ref=relationship.source_ref,
                    source_version="genesis-relationship-episode.v0.3",
                    topic="biography.relationships",
                    aliases=(relationship.display_name, role_label),
                    retrieval_terms=("相识", role_label, relationship.display_name),
                    temporal_label=f"{event_age}岁时",
                    life_stage=stage_for_age(
                        request.species_id, event_age, self._catalog
                    ),
                    place_ids=(place_id,),
                    person_ids=(relationship.person_id,),
                    result=shared_fact,
                    feeling="我记得这段相识，不把对方未分享的经历当成已知。",
                    impact=f"我从这次相识开始认识{relationship.display_name}。",
                    emotional_tone="belonging",
                    importance=min(1.0, relationship.importance),
                    theme_id=(
                        "shared-space-choice"
                        if relationship.role == "friend"
                        else f"relationship-start:{relationship.role}"
                    ),
                    age_years_at_event=event_age,
                )
            )

        station_id = context.earth_transition.departure_place_id
        travel_paths = {
            path_id: (cells, days)
            for path_id, cells, days in context.mobility.travel_paths
        }
        station_path, travel_days = travel_paths.get(
            "birth_to_earthbound_station", ((), 0)
        )
        station_route_ids = self._registered_routes_on_path(station_path)
        preparation_days = context.earth_transition.preparation_duration_local_days
        result.append(
            EpisodeSeed(
                seed_id="predeparture-training",
                content=(
                    f"出发前，我在{self._label(station_id)}完成了"
                    f"{preparation_days}个本地日的赴地准备。"
                ),
                source_ref="earth-arrival:preparation-duration",
                source_version="genesis-transition-episode.v0.3",
                topic="biography.departure",
                aliases=("赴地准备", "出发培训"),
                retrieval_terms=("赴地", "准备", "培训"),
                temporal_label="离开故乡前（具体年龄未知）",
                life_stage="pre_arrival",
                place_ids=(station_id,),
                stay_days=preparation_days,
                purposes=("赴地准备",),
                result=f"完成了{preparation_days}个本地日的赴地准备。",
                feeling="我记得这是离开故乡前的一次正式准备。",
                impact="这次准备发生在离开故乡之前。",
                emotional_tone="resolve",
                importance=0.9,
                theme_id="predeparture-training",
            )
        )
        home_id = context.origin.predeparture_home_place_id
        result.append(
            EpisodeSeed(
                seed_id="departure-decision",
                content=(
                    f"完成赴地准备后，我从{self._label(home_id)}出发，"
                    f"沿实际路线到达{self._label(station_id)}，参加赴地计划。"
                ),
                source_ref="earth-arrival:mandatory-station-trip",
                source_version="genesis-transition-episode.v0.3",
                topic="biography.departure",
                aliases=("赴地", "离开故乡", "赴地基站"),
                retrieval_terms=("赴地", "基站", "路线", *station_route_ids),
                temporal_label="赴地准备与离开故乡（具体年龄未知）",
                life_stage="pre_arrival",
                place_ids=_unique((home_id, station_id)),
                route_ids=station_route_ids,
                travel_days=travel_days,
                purposes=("赴地",),
                result=f"我从故乡抵达{self._label(station_id)}并参加赴地计划。",
                feeling="我记得这是一段实际走过的赴地行程。",
                impact="这次行程把故乡生活与赴地计划连接起来。",
                predecessor_ids=("predeparture-training",),
                emotional_tone="resolve",
                importance=0.94,
                theme_id="departure-decision",
            )
        )
        arrival_age = context.identity.age_years_at_adoption
        owner_person_id = f"owner-person-{request.owner_reference}"
        owner_group_id = f"owner-{request.owner_reference}"
        result.append(
            EpisodeSeed(
                seed_id="arrival-nest",
                content=(
                    f"我在{arrival_age}岁时来到{self._source.earth_home_name}，"
                    "开始与领养家庭共同生活。"
                ),
                source_ref="adoption:accepted",
                source_version="genesis-transition-episode.v0.3",
                topic="biography.arrival",
                aliases=("抵达新家", "领养", "到家"),
                retrieval_terms=("领养家庭", "新家", self._source.earth_home_name),
                temporal_label="领养抵达时",
                life_stage=context.identity.life_stage,
                place_ids=(request.arrival_base_id,),
                person_ids=(owner_person_id, owner_group_id),
                result="抵达领养家庭并开始共同生活。",
                feeling="我记得这是新生活开始的时点。",
                impact="从此，我与领养家庭开始真实相处。",
                predecessor_ids=("departure-decision",),
                emotional_tone="wonder",
                importance=1.0,
                theme_id="arrival-nest",
                age_years_at_event=arrival_age,
            )
        )
        return tuple(result)

    @staticmethod
    def _order_life_episodes(
        episodes: tuple[EpisodeSeed, ...],
    ) -> tuple[EpisodeSeed, ...]:
        """Order factual life points; unknown transition ages stay unguessed."""

        def order(episode: EpisodeSeed) -> tuple[int, int, str]:
            if episode.theme_id == "early-home":
                return 0, 0, episode.seed_id
            if episode.theme_id == "predeparture-training":
                return 2, 0, episode.seed_id
            if episode.theme_id == "departure-decision":
                return 2, 1, episode.seed_id
            if episode.theme_id == "arrival-nest":
                return 3, 0, episode.seed_id
            return 1, episode.age_years_at_event or 0, episode.seed_id

        return tuple(sorted(episodes, key=order))

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
            place_relation_seeds=self._place_relation_seeds(),
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
        requested.add(request.arrival_base_id)
        requested.update(
            item
            for item in (
                _first_place_id(self._source.places, kind="earth_gateway_station"),
                _first_place_id(self._source.places, kind="earth_home"),
            )
            if item
        )
        place_by_id = {place.place_id: place for place in self._source.places}
        pending = list(requested)
        while pending:
            place = place_by_id.get(pending.pop())
            if place is None or place.parent_id in requested:
                continue
            if place.parent_id in place_by_id:
                requested.add(place.parent_id)
                pending.append(place.parent_id)
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
                importance=0.35,
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
                importance=0.65,
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
                importance=0.9,
            )
        )
        # The public geography graph is part of every Elfie's initial Memory.
        # Personal familiarity is represented by visit episodes and importance,
        # not by deleting public place nodes from the shared graph.
        requested.update(place.place_id for place in self._source.places)
        familiar = {
            place_id
            for place_id in (
                *context.mobility.visited_place_ids,
                context.origin.birth_settlement_id,
                context.earth_transition.departure_place_id,
                request.arrival_base_id,
                f"private:{request.elfie_id}:home",
            )
            if place_id
        }
        pending_familiar = list(familiar)
        while pending_familiar:
            current = pending_familiar.pop()
            parent = place_by_id.get(current)
            if parent is None or not parent.parent_id or parent.parent_id in familiar:
                continue
            if parent.parent_id in place_by_id:
                familiar.add(parent.parent_id)
                pending_familiar.append(parent.parent_id)
        visit_counts = dict(context.mobility.visit_counts)
        for place in sorted(self._source.places, key=lambda item: item.place_id):
            if place.place_id not in requested:
                continue
            importance = (
                0.9
                if place.place_id.startswith(f"private:{request.elfie_id}:")
                else min(1.0, 0.7 + 0.05 * visit_counts.get(place.place_id, 0))
                if place.place_id in context.mobility.visited_place_ids
                else 0.65
                if place.place_id in familiar
                else 0.35
            )
            append(
                PlaceSeed(
                    place_id=place.place_id,
                    label=place.label,
                    kind=place.kind,
                    parent_id=place.parent_id,
                    aliases=place.aliases,
                    description=place.description,
                    source_ref=f"place:{place.place_id}",
                    importance=importance,
                    metadata=place.metadata,
                )
            )
        if request.arrival_base_id not in place_by_id:
            append(
                PlaceSeed(
                    place_id=request.arrival_base_id,
                    label=self._source.earth_home_name,
                    kind="earth_home",
                    description=self._source.earth_home_role,
                    source_ref="genesis:accepted-arrival-base",
                    importance=0.9,
                )
            )
        return tuple(result)

    def _place_relation_seeds(self) -> tuple[PlaceRelationSeed, ...]:
        return tuple(
            PlaceRelationSeed(
                subject_id=relation.subject_id,
                relation=relation.relation,
                object_id=relation.object_id,
                source_ref=relation.source_ref,
            )
            for relation in self._source.place_relations
        )

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

    def _domain_uniform(self, seed: int, label: str) -> float:
        """Project one domain digest to a stable open-interval sample."""

        bits = (
            256
            if self._source.generation_policy.seed_algorithm == "sha256-domain-v1"
            else 64
        )
        return (self._domain_seed(seed, label) + 0.5) / (1 << bits)


def _candidate_age_years(candidate: GenesisCandidate) -> int:
    value = candidate.age_years
    if isinstance(value, bool) or not isinstance(value, int) or value < 2:
        raise GenesisError("候选年龄必须至少为 2 岁")
    return value


def _domain_seed(
    seed: int,
    label: str,
    *,
    algorithm: str = "blake2b-labeled-v1",
    policy_version: str = "generation-policy.v1",
) -> int:
    if algorithm == "blake2b-labeled-v1":
        digest = hashlib.blake2b(
            f"{seed}:{label}:{policy_version}".encode(), digest_size=8
        ).digest()
        return int.from_bytes(digest, "big")
    if algorithm != "sha256-domain-v1":
        raise GenesisError(f"不支持的 Genesis seed 算法: {algorithm}")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**256:
        raise GenesisError("SHA-256 Genesis master_seed 必须是 32 字节非负整数")
    domain, stable_id = _seed_domain_and_id(label)
    canonical_input = {
        "algorithm_version": algorithm,
        "attempt_id": 0,
        "domain": unicodedata.normalize("NFC", domain),
        "domain_policy_version": unicodedata.normalize("NFC", policy_version),
        "draw_counter": 0,
        "master_seed": f"{seed:064x}",
        "stable_object_or_slot_id": unicodedata.normalize("NFC", stable_id),
    }
    encoded = json.dumps(
        canonical_input, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return int.from_bytes(hashlib.sha256(encoded).digest(), "big")


def _uniform_hash_subset(
    values: tuple[int, ...], count: int, rank: Callable[[int], int]
) -> tuple[int, ...]:
    """Return a deterministic, equal-rank-weight subset without replacement."""

    if count < 0 or count > len(values) or len(values) != len(set(values)):
        raise GenesisError("家庭年份抽样的候选集合或数量无效")
    return tuple(sorted(sorted(values, key=lambda value: (rank(value), value))[:count]))


def _sample_visit_count(
    probability: float,
    maximum: int,
    power: float,
    *,
    visit_uniform: float,
    count_uniform: float,
) -> int:
    """Sample zero or a bounded, zero-heavy repeat count from two draws."""

    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        raise GenesisError("访问概率必须在 [0, 1] 内")
    if maximum < 1 or not math.isfinite(power) or power <= 0.0:
        raise GenesisError("访问次数上限或幂指数无效")
    if not 0.0 <= visit_uniform < 1.0 or not 0.0 <= count_uniform < 1.0:
        raise GenesisError("访问抽样值必须位于 [0, 1)")
    if visit_uniform >= probability:
        return 0
    return min(maximum, max(1, math.ceil(maximum * count_uniform**power)))


def _sample_conditioned_death_age(
    *,
    terminal_age: int,
    minimum_survival_age: int,
    cdf_power: int,
    uniform: float,
) -> int:
    """Sample one integer-year death age conditioned on required survival."""

    if (
        terminal_age < 1
        or minimum_survival_age < 0
        or minimum_survival_age >= terminal_age
        or isinstance(cdf_power, bool)
        or not 1 <= cdf_power <= 64
    ):
        raise GenesisError("条件寿命抽样的生命边界无效")
    if not 0.0 < uniform < 1.0:
        raise GenesisError("条件寿命抽样值必须位于 (0, 1)")
    lower_cdf = (minimum_survival_age / terminal_age) ** cdf_power
    sampled_cdf = lower_cdf + uniform * (1.0 - lower_cdf)
    sampled_age = terminal_age * sampled_cdf ** (1.0 / cdf_power)
    # The source lifespan curve is continuous; Memory and the current life
    # timeline have local-year precision, so record the first completed age
    # boundary at or after the sample.
    return min(terminal_age, max(minimum_survival_age + 1, math.ceil(sampled_age)))


def _seed_domain_and_id(label: str) -> tuple[str, str]:
    domains = {
        "birth": "birth",
        "birth-cell": "birth",
        "birth-region": "birth",
        "life-archetype": "household",
        "episode-theme": "episodes",
        "relationship-role": "people",
        "family-rule": "people",
        "family-child-count": "people",
        "family-child-year": "people",
        "family-partner": "people",
        "lifespan": "people",
        "friend-count": "people",
        "friend-contact": "people",
        "friend-age": "people",
        "relationship-age": "people",
        "visit-opportunity": "journey",
        "visit-age": "journey",
        "visit-presence": "journey",
        "visit-repeat-count": "journey",
        "visit-member": "journey",
        "visit-purpose": "journey",
        "visit-schedule": "journey",
        "person-species": "people",
        "names": "naming",
        "knowledge": "knowledge",
    }
    prefix, separator, stable_id = label.partition(":")
    domain_key = prefix if separator else label
    try:
        domain = domains[domain_key]
    except KeyError as error:
        raise GenesisError(f"未登记的 Genesis 随机域: {domain_key}") from error
    if separator:
        if prefix == "birth-cell":
            stable_object_id = f"cell:{stable_id}"
        elif prefix in {"visit-presence", "visit-repeat-count"}:
            stable_object_id = f"{prefix}:{stable_id}"
        else:
            stable_object_id = stable_id
    else:
        stable_object_id = domain_key.removeprefix("birth-")
    return domain, stable_object_id


def _generated_names_for_seed(
    source: GenesisSourcePackage,
    *,
    seed: int,
    species_id: str,
    count: int,
) -> tuple[str, ...]:
    pool = source.name_rules.pool(species_id) or ("Nemi",)
    policy = source.generation_policy
    name_rng = random.Random(
        _domain_seed(
            seed,
            f"names:{species_id}",
            algorithm=policy.seed_algorithm,
            policy_version=policy.policy_version,
        )
    )
    offset = name_rng.randrange(len(pool))
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


def _weighted_integer(values: tuple[tuple[int, float], ...], rng: random.Random) -> int:
    """Choose one configured integer without introducing a second sampler."""

    total = sum(float(weight) for _, weight in values)
    if total <= 0:
        raise GenesisError("整数分布权重必须为正")
    target = rng.random() * total
    for value, weight in values:
        target -= float(weight)
        if target <= 0:
            return value
    return values[-1][0]


def _weighted_text(values: tuple[tuple[str, float], ...], rng: random.Random) -> str:
    """Choose one configured text value using the caller's deterministic RNG."""

    total = sum(float(weight) for _, weight in values)
    if total <= 0.0:
        raise GenesisError("文本分布权重必须为正")
    target = rng.random() * total
    for value, weight in values:
        target -= float(weight)
        if target <= 0.0:
            return value
    return values[-1][0]


def _species_label(species_id: str) -> str:
    return {
        "fox": "Saevi",
        "dog": "Tovren",
        "cat": "Myelle",
    }.get(species_id, species_id)


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


def _cell_label_from_population_id(cell_id: str) -> str:
    """Translate the internal sampling-cell ID to the reviewed map label."""

    if not cell_id.startswith("u-r") or "-c" not in cell_id:
        raise GenesisError(f"出生采样单元格式无效: {cell_id}")
    row, column = cell_id[3:].split("-c", 1)
    if not row.isdigit() or not column.isdigit():
        raise GenesisError(f"出生采样单元格式无效: {cell_id}")
    return f"R{int(row)}C{int(column)}"


def _routes_for_places(
    source: GenesisSourcePackage, place_ids: Iterable[str]
) -> tuple[str, ...]:
    """Return declared route aliases whose endpoints were both contacted."""

    contacted = {place_id for place_id in place_ids if place_id}
    if not contacted:
        return ()
    return tuple(
        route.route_id
        for route in sorted(source.routes, key=lambda item: item.route_id)
        if route.from_place_id != route.to_place_id
        and route.from_place_id in contacted
        and route.to_place_id in contacted
    )


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return tuple(result)


def _access_for(fact: WorldKnowledgeFact, species_id: str) -> str:
    if fact.conditions:
        return "available"
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
        acquired_age_years=entry.acquired_age_years,
    )


def _close_prerequisites(
    entries: list[PersonalKnowledgeEntry],
    facts: dict[str, WorldKnowledgeFact],
    species_id: str,
    context: LifeContext,
    episodes: tuple[EpisodeSeed, ...],
    *,
    acquisition_age,
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
            acquired_age_years=acquisition_age(fact, context, episodes),
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
