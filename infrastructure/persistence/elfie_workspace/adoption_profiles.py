"""Final Elfie profile-workspace Adapter used by Resident Admission."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import random
import shutil
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from app.features.adoption import AcceptedAdoptionReservation
from app.orchestration.resident_admission import ResidentAdmissionPortError
from elfie.brain.selfhood import PERSONALITY_PRESETS
from elfie.brain.selfhood.contracts import (
    BigFiveTraits,
    SelfhoodSpeechStyle,
    SelfhoodState,
    normalize_selfhood_mapping,
)
from elfie.genesis import (
    BiographyEnrichmentPlan,
    EpisodeSeed,
    GenesisBundle,
    GenesisMemoryCommitter,
    InitializationManifest,
    KnowledgeMastery,
    KnowledgeSeed,
    PersonalitySeed,
    ProfileDraft,
    RelationshipSeed,
    SelfModelSeed,
    planned_genesis_output_ids,
)
from elfie.profile import (
    AppearanceResolver,
    ElfieOrigin,
    SpeciesCanon,
    SpeciesCatalog,
    create_visual_profile,
    get_species_canon_for_technical_id,
    get_species_definition,
)
from infrastructure.persistence.configuration.world import (
    WorldCanonError,
    load_world_canon,
)
from infrastructure.persistence.elfie_workspace.brain_state import (
    YamlEnergyLimitsAdapter,
    YamlSelfhoodSeedAdapter,
)
from infrastructure.persistence.layout.data_home import data_home_from_db_path
from infrastructure.persistence.layout.data_layout import (
    ensure_final_elfie_layout,
    final_root_layout,
)
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter

_VERBAL_TICKS = ("哒", "喵", "呢", "啦", "呀")
_MUTTER_TEMPLATES: dict[str, tuple[str, ...]] = {
    "bored": (
        "({name}有点无聊，想和你说说话...)",
        "({name}想找点事情聊聊...)",
        "({name}轻轻叹了口气...)",
        "({name}等你说话呢...)",
    ),
    "tired": (
        "({name}有点累，想慢一点说...)",
        "({name}需要安静一会儿...)",
        "(轻轻叹气) {name}想休息一下...",
    ),
    "jealous": (
        "哼，{name}也想和主人说说话...",
        "({name}有点在意主人呢...)",
        "({name}小声嘀咕着什么...)",
    ),
}
_DESCRIPTIONS = {
    "活泼好动": "一只活泼好动、精力旺盛的小精灵",
    "安静温顺": "一只安静温顺、乖巧懂事的小精灵",
    "好奇探索": "一只充满好奇心、热爱探索的小精灵",
    "胆小害羞": "一只胆小害羞、容易受惊的小精灵",
    "傲娇独立": "一只傲娇独立、口是心非的小精灵",
    "完全随机": "一只充满了个性、独一无二的小精灵",
}
_GREETINGS: dict[str, tuple[str, ...]] = {
    "活泼好动": ("主人好呀！", "嘿嘿，我来啦！", "见到你真好！"),
    "安静温顺": ("主人好...", "我在听呢", "很高兴见到你"),
    "好奇探索": ("主人好！", "我有点好奇", "可以和我说说吗？"),
    "胆小害羞": ("呜...主人好", "那个...你、你好...", "唔...被发现了"),
    "傲娇独立": ("哼，你来了啊", "我才不是在等你", "有事就说嘛"),
    "完全随机": ("你好呀！", "咦，是你啊", "很高兴见到你"),
}


class FinalElfieWorkspaceAdapter:
    """Materialize one accepted candidate through the Elfie profile authority."""

    def __init__(
        self,
        data_home: Path | None = None,
        *,
        db_path: str | None = None,
        catalog: SpeciesCatalog | None = None,
    ) -> None:
        if (data_home is None) == (db_path is None):
            raise ValueError("select exactly one workspace root source")
        self._data_home = data_home
        self._db_path = db_path
        self._catalog = catalog

    @classmethod
    def from_database_path(
        cls,
        db_path: str,
        *,
        catalog: SpeciesCatalog | None = None,
    ) -> FinalElfieWorkspaceAdapter:
        """Defer file-root resolution until a workspace operation is requested."""
        return cls(db_path=db_path, catalog=catalog)

    def _selected_data_home(self) -> Path:
        if self._db_path is not None:
            return data_home_from_db_path(self._db_path)
        if self._data_home is None:
            raise RuntimeError("workspace root source is unavailable")
        return self._data_home

    def materialize(self, reservation: AcceptedAdoptionReservation) -> str:
        try:
            # Resolve Canon before creating user files so a bad bundle fails
            # closed without leaving a partial profile behind.
            world_canon = load_world_canon()
            layout = ensure_final_elfie_layout(
                self._selected_data_home(), reservation.elfie_id
            )
            profile = create_visual_profile(
                elfie_id=reservation.elfie_id,
                display_name=reservation.name,
                species_id=reservation.species_id,
                seed=reservation.appearance_seed,
                height_direction=reservation.height,
                build_direction=reservation.build,
                appearance_overrides=(
                    None
                    if reservation.genesis_candidate is not None
                    else _appearance_overrides(reservation, catalog=self._catalog)
                ),
                appearance=(
                    reservation.genesis_candidate.appearance
                    if reservation.genesis_candidate is not None
                    else None
                ),
                origin=ElfieOrigin(birth_at=reservation.birth_date),
                catalog=self._catalog,
            )
            resolved = AppearanceResolver(self._catalog).resolve(profile)
            selfhood_seed = _selfhood_seed(
                reservation,
                resolved.height_scale,
                resolved.build_scale,
                catalog=self._catalog,
                world_canon=world_canon,
            )
            YamlProfileStoreAdapter(layout.profile.parent).save(profile)
            YamlSelfhoodSeedAdapter(layout.brain).save(selfhood_seed)
            YamlEnergyLimitsAdapter(layout.brain).save(
                _energy_limits(
                    reservation.appearance_seed,
                    reservation.height,
                    reservation.build,
                )
            )
            with SQLiteMemoryStoreAdapter(
                layout.knowledge_database, elfie_id=reservation.elfie_id
            ) as memory_store:
                GenesisMemoryCommitter().commit(
                    _genesis_bundle(
                        reservation,
                        profile,
                        selfhood_seed,
                        catalog=self._catalog,
                        world_canon=world_canon,
                    ),
                    memory_store,
                )
            _persist_portraits(layout.assets, reservation)
            return str(layout.workspace)
        except (KeyError, OSError, TypeError, ValueError, WorldCanonError) as error:
            self._release_quietly(reservation.elfie_id)
            raise ResidentAdmissionPortError(
                "unable to materialize Elfie profile"
            ) from error

    def release(self, elfie_id: str) -> None:
        try:
            workspace = (
                final_root_layout(self._selected_data_home()).elfie(elfie_id).workspace
            )
            if workspace.exists():
                shutil.rmtree(workspace)
        except (OSError, ValueError) as error:
            raise ResidentAdmissionPortError(
                "unable to release Elfie workspace"
            ) from error

    def _release_quietly(self, elfie_id: str) -> None:
        try:
            workspace = (
                final_root_layout(self._selected_data_home()).elfie(elfie_id).workspace
            )
            shutil.rmtree(workspace, ignore_errors=True)
        except ValueError:
            return


def _appearance_overrides(
    reservation: AcceptedAdoptionReservation,
    *,
    catalog: SpeciesCatalog | None = None,
) -> dict[str, object]:
    overrides: dict[str, object] = {}
    species = (
        catalog.definition(reservation.species_id, adoptable_only=True)
        if catalog is not None
        else get_species_definition(reservation.species_id, adoptable_only=True)
    )
    if reservation.face == "soft":
        overrides["face"] = {
            "cheek_fullness_bias": 0.42,
            "lower_face_fullness_bias": 0.28,
        }
    elif reservation.face == "defined":
        overrides["face"] = {
            "cheek_fullness_bias": -0.38,
            "lower_face_fullness_bias": -0.24,
        }
    if reservation.signature == "warm":
        overrides["coat"] = {
            "palette_id": _preferred_species_option(
                species.appearance.palettes,
                species.genesis.appearance_preferences.get("warm", ())
                if species.genesis is not None
                else (),
            )
        }
    elif reservation.signature == "marked":
        overrides["coat"] = {
            "pattern_id": _preferred_species_option(
                species.appearance.patterns,
                species.genesis.appearance_preferences.get("marked", ())
                if species.genesis is not None
                else (),
            )
        }
    return overrides


def _preferred_species_option(
    options: tuple[str, ...], preferred: tuple[str, ...]
) -> str:
    if not options:
        raise ValueError("物种外观 profile 至少需要一个可选项")
    return next((item for item in preferred if item in options), options[0])


def _selfhood_seed(
    reservation: AcceptedAdoptionReservation,
    height_scale: float,
    build_scale: float,
    *,
    catalog: SpeciesCatalog | None = None,
    world_canon=None,
) -> dict[str, object]:
    if reservation.genesis_candidate is not None:
        candidate = reservation.genesis_candidate
        species = _species_canon(reservation.species_id, catalog=catalog)
        world = world_canon or load_world_canon()
        big_five = {
            trait: round((value + 2.0) / 4.0, 4)
            for trait, value in zip(
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
        labels = candidate.personality.candidate.labels or ("独一无二",)
        return _canonical_selfhood_seed(
            reservation=reservation,
            species=species,
            world=world,
            big_five=big_five,
            interaction_tendencies=species.earth_first_contact_cues,
            coping_tendencies=species.common_sensory_biases,
            expression_tendencies=labels,
            values=(
                "尊重自愿选择，不把猜测说成亲历。",
                "不知道时说明不知道，并在真实接触中学习地球。",
            ),
            speech_markers=("呢",),
        )
    rng = random.Random(reservation.appearance_seed + 17)
    ranges = PERSONALITY_PRESETS.get(reservation.personality_style)
    if ranges is None:
        raise ValueError(f"unknown personality style: {reservation.personality_style}")
    big_five = {
        trait: round(rng.uniform(lower, upper), 4)
        for trait, (lower, upper) in ranges.items()
    }
    species = _species_canon(reservation.species_id, catalog=catalog)
    world = world_canon or load_world_canon()
    return _canonical_selfhood_seed(
        reservation=reservation,
        species=species,
        world=world,
        big_five=big_five,
        interaction_tendencies=species.earth_first_contact_cues,
        coping_tendencies=species.common_sensory_biases,
        # Store the reviewed vocabulary key.  The model projection deliberately
        # ignores arbitrary prose, so persisting the display description here
        # would silently discard the selected expression tendency.
        expression_tendencies=(reservation.personality_style,),
        values=(
            "尊重自愿选择，不把猜测说成亲历。",
            "不知道时说明不知道，并在真实接触中学习地球。",
        ),
        speech_markers=(rng.choice(_VERBAL_TICKS),),
    )


def _canonical_selfhood_seed(
    *,
    reservation: AcceptedAdoptionReservation,
    species,
    world,
    big_five: dict[str, float],
    interaction_tendencies: tuple[str, ...],
    coping_tendencies: tuple[str, ...],
    expression_tendencies: tuple[str, ...],
    values: tuple[str, ...],
    speech_markers: tuple[str, ...],
) -> dict[str, object]:
    """Materialize only the durable two-layer Selfhood document."""

    state = {
        "state_schema_version": 1,
        "revision": 1,
        "identity_core": {
            "elfie_id": reservation.elfie_id,
            "display_name": reservation.name,
            "species_id": reservation.species_id,
            "species_name": species.display_name,
            "home_world_id": world.world_id,
            "home_world_name": world.display_name,
            "home_region_id": world.known_region_id,
            "home_region_name": world.known_region_name,
            "earth_arrival_statement": world.earth_arrival_statement,
            "resident_role": "ElfieNest 居民",
        },
        "adaptive_self": {
            "big_five": big_five,
            "interaction_tendency_ids": interaction_tendencies,
            "coping_tendency_ids": coping_tendencies,
            "expression_tendency_ids": expression_tendencies,
            "value_ids": values,
            "speech_marker_ids": speech_markers,
            "source_event_ids": (),
        },
    }
    # Validate the complete typed hand-off before any sibling output is saved.
    validation_state = dict(state)
    validation_state["committed_at"] = datetime.fromtimestamp(0, timezone.utc)
    SelfhoodState.model_validate(validation_state)
    return state


def _genesis_bundle(
    reservation: AcceptedAdoptionReservation,
    profile,
    selfhood_seed: dict[str, object],
    *,
    catalog: SpeciesCatalog | None = None,
    world_canon=None,
) -> GenesisBundle:
    """Compile the bundled Canon into one deterministic personal brain."""
    species = _species_canon(reservation.species_id, catalog=catalog)
    world = world_canon or load_world_canon()
    adaptive_seed = selfhood_seed.get("adaptive_self", {})
    if not isinstance(adaptive_seed, dict):
        adaptive_seed = {}
    raw_big_five = adaptive_seed.get("big_five", {})
    if not isinstance(raw_big_five, dict):
        raw_big_five = {}
    big_five = BigFiveTraits(
        **{
            key: float(raw_big_five.get(key, 0.5))
            for key in (
                "openness",
                "conscientiousness",
                "extraversion",
                "agreeableness",
                "neuroticism",
            )
        }
    )
    speech_markers = adaptive_seed.get("speech_marker_ids", ())
    if not isinstance(speech_markers, (list, tuple)):
        speech_markers = ()
    verbal_tick = speech_markers[0] if speech_markers else None
    knowledge_seeds = _initial_knowledge_seeds(
        world,
        species_id=reservation.species_id,
    )
    names = _personal_names(reservation.appearance_seed)
    relationship_seeds = _initial_relationship_seeds(
        reservation,
        names,
    )
    episode_seeds = _initial_episode_seeds(
        reservation,
        names,
        world_canon=world,
    )
    manifest_id = f"genesis:{reservation.elfie_id}:{reservation.appearance_seed}:v0.2"
    input_ids = tuple(
        [seed.seed_id for seed in knowledge_seeds]
        + [seed.seed_id for seed in episode_seeds]
        + [seed.stable_relationship_id for seed in relationship_seeds]
    )
    content_hash = _bundle_content_hash(
        knowledge_seeds,
        episode_seeds,
        relationship_seeds,
    )
    state_for_bundle = dict(selfhood_seed)
    state_for_bundle.setdefault("committed_at", datetime.fromtimestamp(0, timezone.utc))
    bundle = GenesisBundle(
        profile_draft=ProfileDraft(profile),
        selfhood_state=SelfhoodState.model_validate(
            normalize_selfhood_mapping(state_for_bundle)
        ),
        personality_seed=PersonalitySeed(
            big_five=big_five,
            self_description=(
                f"我是 {reservation.name}，正式物种名是 {species.display_name}；"
                f"我来自 {world.display_name} 的"
                f"{world.known_region_name}。"
            ),
            speech_style=SelfhoodSpeechStyle(
                greetings=(),
                verbal_tick=None if verbal_tick is None else str(verbal_tick),
            ),
            norms=(
                *tuple(
                    str(item)
                    for item in adaptive_seed.get("value_ids", ())
                    if isinstance(item, str)
                ),
            ),
            behavior_anchors=tuple(
                str(item)
                for item in adaptive_seed.get("interaction_tendency_ids", ())
                if isinstance(item, str)
            ),
            sensory_biases=tuple(
                str(item)
                for item in adaptive_seed.get("coping_tendency_ids", ())
                if isinstance(item, str)
            ),
        ),
        memory_seeds=(),
        knowledge_seeds=knowledge_seeds,
        episode_seeds=episode_seeds,
        relationship_seeds=relationship_seeds,
        self_model_seed=SelfModelSeed(
            identity_summary=(
                f"我是 {reservation.name}，一只 {species.display_name}（{species.earth_shape_label}）。"
            ),
            known_facts=(
                f"我的家乡是 {world.display_name}。",
                f"我的家乡区域是 {world.known_region_name}。",
                f"我在地球的家是 {world.earth_home_name}。",
                world.earth_arrival_statement,
            ),
            unknown_facts=world.unknown_boundaries,
            knowledge_scope=(
                "公共世界事实来自版本化 Canon，个人掌握程度由 Genesis 明确标记。",
                "只把 Profile、Genesis 资料和亲历记忆当作我的身份依据。",
                "不把地球模型的常识冒充为 Elfaria 的亲历。",
            ),
            species_knowledge=species.common_knowledge,
            skills=("区分亲历、听闻和未确认信息", "在陌生设备前先询问用途"),
            habits=("先确认边界，再靠近陌生事物",),
            preferences=("逐步熟悉的新环境", "有明确约定的相处"),
            emotional_triggers=("被要求把猜测说成事实", "未经允许的突然靠近"),
            current_goal="在 ElfieNest 里通过真实相处逐步学会地球生活。",
            earth_adaptation=("地球设备仍有很多未知，不能凭模型常识补齐。",),
        ),
        biography_plan=BiographyEnrichmentPlan(),
        manifest=InitializationManifest(
            manifest_id=manifest_id,
            canon_version=world.canon_version,
            species_version=species.canon_version,
            reference_version="adoption-genesis.v1",
            status="validated",
            namespace=f"elfie:{reservation.elfie_id}",
            generator_version="genesis-knowledge.v0.1",
            schema_version=1,
            master_seed=reservation.appearance_seed,
            input_ids=input_ids,
            content_hash=content_hash,
            idempotency_key=manifest_id,
        ),
    )
    return replace(
        bundle,
        manifest=replace(
            bundle.manifest,
            output_ids=planned_genesis_output_ids(bundle),
        ),
    )


def _initial_knowledge_seeds(world, *, species_id: str) -> tuple[KnowledgeSeed, ...]:
    """Select a deterministic, useful subset without claiming every fact."""

    selected: list[KnowledgeSeed] = []
    for fact in world.knowledge:
        eligible = set(fact.eligibility)
        if fact.status == "active":
            if "all" not in eligible and species_id not in eligible:
                continue
            mastery: KnowledgeMastery = (
                "known"
                if fact.level == "common" or species_id in eligible
                else "partial"
            )
        else:
            mastery = "unknown"
        selected.append(
            KnowledgeSeed(
                seed_id=fact.fact_id,
                content=fact.statement,
                source="canon",
                source_ref=fact.source_ref,
                source_version=world.canon_version,
                scope=fact.scope,
                topic=fact.topic,
                aliases=fact.aliases,
                retrieval_terms=fact.retrieval_terms,
                certainty=fact.certainty,
                level=fact.level,
                mastery=mastery,
                status=fact.status,
                eligibility=fact.eligibility,
                related_ids=fact.related_ids,
                version=fact.version,
            )
        )
    if not selected:
        raise ValueError("World Canon 没有可供 Genesis 选择的知识")
    return tuple(selected)


def _personal_names(seed: int) -> tuple[str, ...]:
    """Stable personal-only names; they are not public World Canon entities."""

    pool = (
        "Nemi",
        "Ari",
        "Sora",
        "Tavi",
        "Mira",
        "Lio",
        "Ena",
        "Rin",
        "Kio",
        "Veya",
        "Oru",
        "Pela",
    )
    offset = seed % len(pool)
    return tuple(pool[offset:] + pool[:offset])


_RELATION_ROLE_ALIASES: dict[str, tuple[str, ...]] = {
    "family": ("家人", "亲人"),
    "friend": ("朋友",),
    "teacher": ("老师", "导师"),
    "elder": ("长老", "年长者"),
    "neighbor": ("邻居",),
    "route_keeper": ("路线维护者",),
    "learning_keeper": ("学习场所照料者",),
    "departure_guide": ("赴地引导者",),
    "program_contact": ("计划联系人",),
    "earth_contact": ("地球侧联系人",),
    "earth_household": ("领养家庭", "主人"),
}

_EPISODE_LABELS: dict[str, str] = {
    "early-home": "早期家乡生活",
    "learning-path": "成长学习阶段",
    "shared-space-choice": "公共空间的协作经历",
    "departure-decision": "报名赴地的决定",
    "arrival-nest": "抵达 ElfieNest",
}


def _initial_relationship_seeds(
    reservation: AcceptedAdoptionReservation,
    names: tuple[str, ...],
) -> tuple[RelationshipSeed, ...]:
    """Create a bounded private acquaintance graph for one Elfie."""

    roles = (
        ("kin-01", "family", 0.88, 0.95, ("early-home", "shared-space-choice")),
        ("kin-02", "family", 0.72, 0.72, ("early-home",)),
        ("friend-01", "friend", 0.78, 0.9, ("learning-path", "shared-space-choice")),
        ("friend-02", "friend", 0.58, 0.62, ("shared-space-choice",)),
        ("mentor-01", "teacher", 0.7, 0.82, ("learning-path", "departure-decision")),
        ("elder-01", "elder", 0.55, 0.78, ("shared-space-choice",)),
        ("neighbor-01", "neighbor", 0.42, 0.48, ("shared-space-choice",)),
        (
            "route-keeper",
            "route_keeper",
            0.5,
            0.56,
            ("early-home", "departure-decision"),
        ),
        ("learning-keeper", "learning_keeper", 0.48, 0.5, ("learning-path",)),
        (
            "departure-guide",
            "departure_guide",
            0.64,
            0.72,
            ("departure-decision", "arrival-nest"),
        ),
        (
            "program-contact",
            "program_contact",
            0.38,
            0.58,
            ("departure-decision", "arrival-nest"),
        ),
        ("earth-contact", "earth_contact", 0.3, 0.7, ("arrival-nest",)),
    )
    result: list[RelationshipSeed] = []
    for index, (person_id, role, trust, importance, episodes) in enumerate(roles):
        role_aliases = _RELATION_ROLE_ALIASES.get(role, ())
        result.append(
            RelationshipSeed(
                person_id=person_id,
                display_name=names[index],
                role=role,
                initial_trust=trust,
                shared_facts=(
                    f"我们曾一起经历过 {_EPISODE_LABELS.get(episodes[0], episodes[0])}。",
                    "具体家庭背景和每天的生活仍有未确认部分。",
                ),
                unknown_facts=("对方没有在共同经历中告诉我的完整生活。",),
                relationship_id=f"rel:{person_id}",
                subject_id=f"elfie:{reservation.elfie_id}",
                object_id=person_id,
                direction="elfie_to_person",
                familiarity="intimate" if importance >= 0.85 else "known",
                importance=importance,
                aliases=(names[index], role, *role_aliases),
                retrieval_terms=(role, person_id, *role_aliases),
                episode_ids=episodes,
                source="approved_seed",
                source_ref=f"approved-seed:adoption-genesis.v1#relationship-{person_id}",
                source_version="adoption-genesis.v1",
                certainty="high",
                version=1,
            )
        )
    result.append(
        RelationshipSeed(
            person_id=f"owner-{reservation.owner_user_id}",
            display_name="领养家庭",
            role="earth_household",
            initial_trust=0.25,
            shared_facts=(
                "对方为我准备了 ElfieNest。",
                "我们会通过真实相处逐步建立信任。",
            ),
            unknown_facts=("对方完整的生活、过去和每天的想法。",),
            relationship_id=f"rel:owner-{reservation.owner_user_id}",
            subject_id=f"elfie:{reservation.elfie_id}",
            object_id=f"owner-{reservation.owner_user_id}",
            direction="elfie_to_person",
            familiarity="acquainted",
            importance=0.9,
            aliases=("领养家庭", "主人", *_RELATION_ROLE_ALIASES["earth_household"]),
            retrieval_terms=(
                "主人",
                "领养",
                "家庭",
                *_RELATION_ROLE_ALIASES["earth_household"],
            ),
            episode_ids=("arrival-nest",),
            source="approved_seed",
            source_ref="approved-seed:adoption-genesis.v1#earth-household",
            source_version="adoption-genesis.v1",
            certainty="high",
            version=1,
        )
    )
    return tuple(result)


def _initial_episode_seeds(
    reservation: AcceptedAdoptionReservation,
    names: tuple[str, ...],
    *,
    world_canon,
) -> tuple[EpisodeSeed, ...]:
    """Build five linked life stages from home to Earth arrival."""

    source_version = "adoption-genesis.v1"
    homes_label = world_canon.place("mistyville_homes").label
    learning_label = world_canon.place("mistyville_learning_house").label
    square_label = world_canon.place("mistyville_square").label
    waystation_label = world_canon.place("mistyville_waystation").label
    gateway_label = world_canon.place("earth_gateway_station").label
    return (
        EpisodeSeed(
            seed_id="early-home",
            content=(
                f"在 {world_canon.known_region_name} 的{homes_label}，我和 {names[0]}、{names[1]} 一起长大。"
                "我很早就学会沿着熟悉的路径确认返回方向，也知道公共空间并不等于每个人都互相认识。"
            ),
            source="personal_memory",
            source_ref=f"approved-seed:{source_version}#early-home",
            source_version=source_version,
            scope="elfie",
            topic="biography.home",
            aliases=("小时候", "家乡生活", "居住区"),
            retrieval_terms=("返回方向", "熟悉的路径", "一起长大"),
            temporal_label="早期生活",
            life_stage="youth",
            place_ids=("mistyville_homes", "mistyville"),
            person_ids=("kin-01", "kin-02"),
            result="我形成了对家乡路径和边界的基本熟悉。",
            feeling="安全，也很依恋熟悉的返回路径。",
            impact="遇到陌生地方时，我会先确认边界和回去的办法。",
            emotional_tone="belonging",
            emotion_intensity=0.8,
            importance=0.8,
        ),
        EpisodeSeed(
            seed_id="learning-path",
            content=(
                f"后来我在{learning_label}和 {names[4]}、{names[2]} 一起学习。"
                "我第一次认真记录声音、气味和路径的差别，并发现复杂知识需要向熟悉它的人请教。"
            ),
            source="personal_memory",
            source_ref=f"approved-seed:{source_version}#learning-path",
            source_version=source_version,
            scope="elfie",
            topic="biography.learning",
            aliases=("学习经历", "学习场所", "老师"),
            retrieval_terms=("记录声音", "气味和路径", "请教"),
            temporal_label="成长阶段",
            life_stage="young_adult",
            place_ids=("mistyville_learning_house", "mistyville"),
            person_ids=("mentor-01", "friend-01"),
            result="我学会把观察到的线索和别人传授的经验分开。",
            feeling="好奇，但会对自己不知道的部分保持谨慎。",
            impact="面对陌生设备或说法时，我倾向先观察、再询问。",
            predecessor_ids=("early-home",),
            causal_links=(
                "early-home -> learning-path: 熟悉路径让我更愿意记录环境线索",
            ),
            emotional_tone="curiosity",
            emotion_intensity=0.7,
            importance=0.82,
        ),
        EpisodeSeed(
            seed_id="shared-space-choice",
            content=(
                f"在{square_label}，我和 {names[2]}、{names[5]}、{names[6]} 一起处理一次需要协作的日常事务。"
                "有人提出更快的办法，但没有先确认每个人是否愿意，我最后选择停下来重新约定。"
            ),
            source="personal_memory",
            source_ref=f"approved-seed:{source_version}#shared-space-choice",
            source_version=source_version,
            scope="elfie",
            topic="biography.choice",
            aliases=("公共空间的经历", "协作经历", "一次选择"),
            retrieval_terms=("重新约定", "是否愿意", "协作"),
            temporal_label="成年前后",
            life_stage="young_adult",
            place_ids=("mistyville_square", "mistyville"),
            person_ids=("friend-01", "elder-01", "neighbor-01"),
            result="事情慢了一点，但所有人都知道自己同意了什么。",
            feeling="安心，也更清楚信任需要兑现约定。",
            impact="我现在会把自愿、边界和可返回的选择放在效率之前。",
            predecessor_ids=("learning-path",),
            causal_links=(
                "learning-path -> shared-space-choice: 请教和记录让我看见协作中的未知",
            ),
            emotional_tone="trust",
            emotion_intensity=0.76,
            importance=0.88,
        ),
        EpisodeSeed(
            seed_id="departure-decision",
            content=(
                f"跨世界信号和初次确认之后，我在 {world_canon.known_region_name} 的{waystation_label}听 {names[4]}、{names[9]} 和 {names[10]} 说明赴地计划。"
                "我知道地球侧正在建设基站，也知道参加计划必须是自己的选择，于是决定报名。"
            ),
            source="personal_memory",
            source_ref=f"approved-seed:{source_version}#departure-decision",
            source_version=source_version,
            scope="elfie",
            topic="biography.earth_program",
            aliases=("报名赴地", "赴地决定", "为什么来地球"),
            retrieval_terms=("跨世界信号", "报名", "自己的选择", "基站"),
            temporal_label="赴地计划阶段",
            life_stage="mature",
            place_ids=("mistyville_waystation", "mistyville"),
            person_ids=("mentor-01", "departure-guide", "program-contact"),
            result="我报名并通过了赴地计划的准备流程。",
            feeling="紧张，但不是被迫离开；我想亲自确认另一个世界。",
            impact="我会把探索理解为带着边界去接触未知，而不是假装什么都懂。",
            predecessor_ids=("shared-space-choice",),
            causal_links=(
                "shared-space-choice -> departure-decision: 对自愿和约定的重视影响了我的报名选择",
            ),
            related_ids=(
                "story_signal",
                "story_confirmation",
                "story_station",
                "story_program",
            ),
            emotional_tone="resolve",
            emotion_intensity=0.86,
            importance=0.94,
        ),
        EpisodeSeed(
            seed_id="arrival-nest",
            content=(
                f"我从{waystation_label}出发，经由{gateway_label}抵达 {world_canon.earth_home_name}。"
                f"{names[9]} 和 {names[10]} 参与了交接，之后我第一次见到领养家庭。"
                "这里成为我的新家，但地球设备、当天巢内状态和许多生活细节仍需要真实相处后才能知道。"
            ),
            source="personal_memory",
            source_ref=f"approved-seed:{source_version}#arrival-nest",
            source_version=source_version,
            scope="elfie",
            topic="biography.arrival",
            aliases=("抵达地球", "第一次到 ElfieNest", "新家"),
            retrieval_terms=("地球侧基站", "交接", "新家", "巢内状态"),
            temporal_label="抵达地球时",
            life_stage="arrival",
            place_ids=("earth_gateway_station", "elfie_nest"),
            person_ids=(
                "departure-guide",
                "program-contact",
                "earth-contact",
                f"owner-{reservation.owner_user_id}",
            ),
            result="我安全抵达 ElfieNest，并开始和领养家庭建立真实关系。",
            feeling="惊奇、谨慎，也期待慢慢熟悉这里。",
            impact="来到地球后，我会把真实观测和过去记忆分开，不把猜测说成今天发生的事。",
            predecessor_ids=("departure-decision",),
            causal_links=(
                "departure-decision -> arrival-nest: 自主决定让我带着边界和期待抵达",
            ),
            related_ids=(
                "story_station",
                "story_program",
                "story_arrival",
                "earth_gateway_station",
            ),
            emotional_tone="wonder",
            emotion_intensity=0.9,
            importance=1.0,
        ),
    )


def _bundle_content_hash(knowledge, episodes, relationships) -> str:
    payload = {
        "knowledge": [seed.__dict__ for seed in knowledge],
        "episodes": [seed.__dict__ for seed in episodes],
        "relationships": [seed.__dict__ for seed in relationships],
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _species_canon(
    species_id: str,
    *,
    catalog: SpeciesCatalog | None = None,
) -> SpeciesCanon:
    if catalog is not None:
        return catalog.definition(species_id, adoptable_only=True).canon
    return get_species_canon_for_technical_id(species_id)


def _portrait_metadata(reservation: AcceptedAdoptionReservation) -> dict[str, object]:
    if not reservation.full_body_image_url and not reservation.headshot_image_url:
        return {}
    return {
        "portraits": {
            "full_body": "assets/portrait-full.png",
            "headshot": "assets/portrait-head.png",
        }
    }


def _persist_portraits(
    assets: Path,
    reservation: AcceptedAdoptionReservation,
) -> None:
    if not reservation.full_body_image_url and not reservation.headshot_image_url:
        return
    if not reservation.full_body_image_url or not reservation.headshot_image_url:
        raise ValueError("accepted Adoption portraits must contain both views")
    full_body = _decode_png_data_url(reservation.full_body_image_url)
    headshot = _decode_png_data_url(reservation.headshot_image_url)
    _write_private_asset(assets / "portrait-full.png", full_body)
    _write_private_asset(assets / "portrait-head.png", headshot)


def _decode_png_data_url(value: str) -> bytes:
    prefix = "data:image/png;base64,"
    if not value.startswith(prefix):
        raise ValueError("accepted Adoption portrait must be a PNG data URL")
    try:
        content = base64.b64decode(value[len(prefix) :], validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("accepted Adoption portrait is not valid base64") from error
    if not content.startswith(b"\x89PNG\r\n\x1a\n") or len(content) > 8 * 1024 * 1024:
        raise ValueError("accepted Adoption portrait is not a valid PNG")
    return content


def _write_private_asset(path: Path, content: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            os.chmod(path, 0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def _energy_limits(seed: int, height: str, build: str) -> dict[str, object]:
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


__all__ = ("FinalElfieWorkspaceAdapter",)
