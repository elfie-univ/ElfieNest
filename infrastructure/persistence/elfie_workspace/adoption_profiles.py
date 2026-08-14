"""Final Elfie profile-workspace Adapter used by Resident Admission."""

from __future__ import annotations

import random
import shutil
from dataclasses import replace
from pathlib import Path

from app.features.adoption import AcceptedAdoptionReservation
from app.orchestration.resident_admission import ResidentAdmissionPortError
from elfie.brain.selfhood.contracts import BigFiveTraits, SelfhoodSpeechStyle
from elfie.genesis import (
    BiographyEnrichmentPlan,
    GenesisBundle,
    GenesisMemoryCommitter,
    InitializationManifest,
    MemorySeed,
    PersonalitySeed,
    ProfileDraft,
    RelationshipSeed,
    SelfModelSeed,
)
from elfie.profile import (
    ELFARIA_CANON,
    PERSONALITY_PRESETS,
    SPECIES_CANON_VERSION,
    WORLD_CANON_VERSION,
    AppearanceResolver,
    ElfieOrigin,
    create_visual_profile,
    get_species_canon_for_technical_id,
    get_species_definition,
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
        "({name}无聊地咬了咬尾巴...)",
        "({name}趴在地上画圈圈...)",
        "(打哈欠) 没人理{name}呀...",
        "({name}盯着窗外发呆...)",
    ),
    "tired": (
        "({name}的耳朵耷拉下来了...)",
        "(揉眼睛) 呼...{name}要睡了...",
        "({name}打了个大大的哈欠...)",
    ),
    "jealous": (
        "哼，主人又忙别的了...",
        "({name}酸溜溜地撇过头...)",
        "({name}小声嘀咕着什么...)",
    ),
}
_ACTIONS = ("wag_tail", "wiggle_ears", "nod_head", "shake_head", "blink_eyes", "mutter")
_DESCRIPTIONS = {
    "活泼好动": "一只活泼好动、精力旺盛的小精灵",
    "安静温顺": "一只安静温顺、乖巧懂事的小精灵",
    "好奇探索": "一只充满好奇心、热爱探索的小精灵",
    "胆小害羞": "一只胆小害羞、容易受惊的小精灵",
    "傲娇独立": "一只傲娇独立、口是心非的小精灵",
    "完全随机": "一只充满了个性、独一无二的小精灵",
}
_GREETINGS: dict[str, tuple[str, ...]] = {
    "活泼好动": ("主人好呀！", "今天又是元气满满的一天！", "嘿嘿，我来啦！"),
    "安静温顺": ("主人好...", "今天也很安静呢", "嗯...我在的"),
    "好奇探索": ("咦？这是什么？", "主人快来看！", "那边好像有什么有趣的东西！"),
    "胆小害羞": ("呜...主人好", "那个...你、你好...", "唔...被发现了"),
    "傲娇独立": ("哼，我才不是想你呢！", "干嘛呀，人家正忙着呢", "哟，你来了啊"),
    "完全随机": ("你好呀！", "咦，是你啊", "嘿嘿，今天天气真不错"),
}


class FinalElfieWorkspaceAdapter:
    """Materialize one accepted candidate through the Elfie profile authority."""

    def __init__(
        self,
        data_home: Path | None = None,
        *,
        db_path: str | None = None,
    ) -> None:
        if (data_home is None) == (db_path is None):
            raise ValueError("select exactly one workspace root source")
        self._data_home = data_home
        self._db_path = db_path

    @classmethod
    def from_database_path(cls, db_path: str) -> FinalElfieWorkspaceAdapter:
        """Defer file-root resolution until a workspace operation is requested."""
        return cls(db_path=db_path)

    def _selected_data_home(self) -> Path:
        if self._db_path is not None:
            return data_home_from_db_path(self._db_path)
        if self._data_home is None:
            raise RuntimeError("workspace root source is unavailable")
        return self._data_home

    def materialize(self, reservation: AcceptedAdoptionReservation) -> str:
        try:
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
                appearance_overrides=_appearance_overrides(reservation),
                origin=ElfieOrigin(birth_at=reservation.birth_date),
            )
            resolved = AppearanceResolver().resolve(profile)
            profile = replace(
                profile,
                personality=_personality(
                    reservation, resolved.height_scale, resolved.build_scale
                ),
                capabilities=_capabilities(reservation.appearance_seed),
                system_limits=_system_limits(
                    reservation.appearance_seed,
                    reservation.height,
                    reservation.build,
                ),
            )
            YamlProfileStoreAdapter(layout.profile.parent).save(profile)
            with SQLiteMemoryStoreAdapter(layout.knowledge_database) as memory_store:
                GenesisMemoryCommitter().commit(
                    _genesis_bundle(reservation, profile), memory_store
                )
            return str(layout.workspace)
        except (OSError, TypeError, ValueError) as error:
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
) -> dict[str, object]:
    overrides: dict[str, object] = {}
    species = get_species_definition(reservation.species_id)
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
                species.appearance.palettes, ("golden", "cream")
            )
        }
    elif reservation.signature == "marked":
        overrides["coat"] = {
            "pattern_id": _preferred_species_option(
                species.appearance.patterns, ("face_mask", "tabby")
            )
        }
    return overrides


def _preferred_species_option(
    options: tuple[str, ...], preferred: tuple[str, ...]
) -> str:
    if not options:
        raise ValueError("物种外观 profile 至少需要一个可选项")
    return next((item for item in preferred if item in options), options[0])


def _personality(
    reservation: AcceptedAdoptionReservation,
    height_scale: float,
    build_scale: float,
) -> dict[str, object]:
    rng = random.Random(reservation.appearance_seed + 17)
    ranges = PERSONALITY_PRESETS.get(reservation.personality_style)
    if ranges is None:
        raise ValueError(f"unknown personality style: {reservation.personality_style}")
    big_five = {
        trait: round(rng.uniform(lower, upper), 4)
        for trait, (lower, upper) in ranges.items()
    }
    mutter_templates: dict[str, list[str]] = {}
    for mood, templates in _MUTTER_TEMPLATES.items():
        selected = rng.sample(templates, rng.randint(1, min(2, len(templates))))
        mutter_templates[mood] = [
            template.replace("{name}", reservation.name) for template in selected
        ]
    greeting_pool = _GREETINGS.get(
        reservation.personality_style,
        _GREETINGS["完全随机"],
    )
    greetings = rng.sample(
        greeting_pool, rng.randint(2, min(3, len(greeting_pool)))
    )
    return {
        "metadata": {
            "name": reservation.name,
            "version": "1.0",
            "description": _DESCRIPTIONS.get(
                reservation.personality_style,
                _DESCRIPTIONS["完全随机"],
            ),
            "appearance": {
                "height": reservation.height,
                "build": reservation.build,
                "species": reservation.species_id,
                "height_scale": height_scale,
                "build_scale": build_scale,
            },
        },
        "big_five": big_five,
        "speech_style": {
            "greetings": greetings,
            "mutter_templates": mutter_templates,
            "verbal_ticks": rng.choice(_VERBAL_TICKS),
        },
    }


def _genesis_bundle(
    reservation: AcceptedAdoptionReservation,
    profile,
) -> GenesisBundle:
    """Build the small, explicit set of facts known at first arrival."""
    species = get_species_canon_for_technical_id(reservation.species_id)
    personality = profile.personality
    raw_big_five = personality.get("big_five", {})
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
    speech_style = personality.get("speech_style", {})
    greeting_values = speech_style.get("greetings", ())
    verbal_tick = speech_style.get("verbal_ticks")
    manifest_id = f"genesis:{reservation.elfie_id}:{reservation.appearance_seed}:v0.1"
    return GenesisBundle(
        profile_draft=ProfileDraft(profile),
        personality_seed=PersonalitySeed(
            big_five=big_five,
            self_description=(
                f"我是 {reservation.name}，正式物种名是 {species.display_name}；"
                f"我来自 {ELFARIA_CANON.display_name} 的"
                f"{ELFARIA_CANON.known_region_name}。"
            ),
            speech_style=SelfhoodSpeechStyle(
                greetings=tuple(str(item) for item in greeting_values),
                verbal_tick=None if verbal_tick is None else str(verbal_tick),
            ),
            norms=(
                "尊重自愿选择，不把猜测说成亲历。",
                "不知道时说明不知道，并在真实接触中学习地球。",
            ),
            behavior_anchors=species.earth_first_contact_cues,
        ),
        memory_seeds=(
            MemorySeed(
                seed_id="home-world",
                content=(
                    f"我知道自己来自 {ELFARIA_CANON.display_name} 的"
                    f"{ELFARIA_CANON.known_region_name}；这是我能确认的家乡。"
                ),
                source="program_brief",
                certainty="high",
                emotional_tone="belonging",
                intensity=0.8,
            ),
            MemorySeed(
                seed_id="earth-plan",
                content=(
                    "赴地计划是我自愿参加的；地球侧工程人员建造并稳定了"
                    "传送阵和赴地设施。"
                ),
                source="program_brief",
                certainty="high",
                emotional_tone="trust",
                intensity=0.65,
            ),
            MemorySeed(
                seed_id="arrival-gateway",
                content=(
                    f"我通过传送阵来到地球，传送阵把我接收到 {ELFARIA_CANON.earth_home_name}。"
                ),
                source="personal_memory",
                certainty="high",
                emotional_tone="wonder",
                intensity=0.9,
            ),
            MemorySeed(
                seed_id="first-home",
                content=(
                    f"{ELFARIA_CANON.earth_home_name} 是我在地球的基地和家，"
                    "里面有我的房间、活动空间和与地球家庭相处的地方；"
                    "我的身份和记忆属于我自己。"
                ),
                source="personal_memory",
                certainty="high",
                emotional_tone="safety",
                intensity=0.8,
            ),
            MemorySeed(
                seed_id="earth-first-contact",
                content=(
                    "地球的设备和现代生活对我来说有很多新东西；我会先观察、"
                    "询问，再通过真实经历慢慢学会，而不是假装早就知道。"
                ),
                source="program_brief",
                certainty="high",
                emotional_tone="curiosity",
                intensity=0.75,
            ),
        ),
        relationship_seeds=(
            RelationshipSeed(
                person_id=f"owner-{reservation.owner_user_id}",
                display_name="领养家庭",
                role="earth_household",
                initial_trust=0.25,
                shared_facts=(
                    f"对方为我准备了 {ELFARIA_CANON.earth_home_name}。",
                    "我们会通过真实相处逐步建立信任。",
                ),
                unknown_facts=("对方完整的生活、过去和每天的想法。",),
            ),
        ),
        self_model_seed=SelfModelSeed(
            identity_summary=(
                f"我是 {reservation.name}，一只 {species.display_name}（{species.earth_shape_label}）。"
            ),
            known_facts=(
                f"我的家乡是 {ELFARIA_CANON.display_name}。",
                f"我的家乡区域是 {ELFARIA_CANON.known_region_name}。",
                f"我在地球的家是 {ELFARIA_CANON.earth_home_name}。",
                "地球侧帮助建设了传送阵和赴地设施。",
            ),
            unknown_facts=ELFARIA_CANON.knowledge_boundaries,
            knowledge_scope=(
                "只把 Profile、Genesis 资料和亲历记忆当作我的身份依据。",
                "不把地球模型的常识冒充为 Elfaria 的亲历。",
            ),
        ),
        biography_plan=BiographyEnrichmentPlan(
            allowed_memory_seed_ids=("arrival-gateway", "first-home", "earth-first-contact"),
            max_additional_memories=8,
            expires_after_events=12,
        ),
        manifest=InitializationManifest(
            manifest_id=manifest_id,
            canon_version=WORLD_CANON_VERSION,
            species_version=SPECIES_CANON_VERSION,
            reference_version="adoption-genesis.v0.1",
            status="validated",
        ),
    )


def _capabilities(seed: int) -> dict[str, object]:
    rng = random.Random(seed + 31)
    mandatory = ["nod_head", "blink_eyes"]
    optional = [action for action in _ACTIONS if action not in mandatory]
    actions = mandatory + rng.sample(optional, rng.randint(1, 3))
    rng.shuffle(actions)
    return {
        "carrier_type": "smart_plush_toy",
        "actuators": {
            "speech": {
                "enabled": True,
                "max_words_per_minute": rng.randint(80, 150),
            },
            "motion": {
                "enabled": True,
                "supported_actions": actions,
                "speed_limits": {
                    "max_servo_angle_speed": round(rng.uniform(40, 80), 2)
                },
            },
            "physics_limits": {
                "can_fly": False,
                "can_swim": False,
                "max_height_jump": 0.0,
                "requires_power_plug": False,
            },
        },
    }


def _system_limits(seed: int, height: str, build: str) -> dict[str, object]:
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
