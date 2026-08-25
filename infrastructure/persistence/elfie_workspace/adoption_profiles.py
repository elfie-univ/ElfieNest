"""Final Elfie profile-workspace Adapter used by Resident Admission."""

from __future__ import annotations

import base64
import binascii
import os
import random
import shutil
from pathlib import Path

from app.features.adoption import AcceptedAdoptionReservation
from app.orchestration.resident_admission import ResidentAdmissionPortError
from elfie.brain.selfhood import PERSONALITY_PRESETS
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
    SPECIES_CANON_VERSION,
    WORLD_CANON_VERSION,
    AppearanceResolver,
    ElfieOrigin,
    SpeciesCanon,
    SpeciesCatalog,
    create_visual_profile,
    get_species_canon_for_technical_id,
    get_species_definition,
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
            with SQLiteMemoryStoreAdapter(layout.knowledge_database) as memory_store:
                GenesisMemoryCommitter().commit(
                    _genesis_bundle(
                        reservation,
                        profile,
                        selfhood_seed,
                        catalog=self._catalog,
                    ),
                    memory_store,
                )
            _persist_portraits(layout.assets, reservation)
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
) -> dict[str, object]:
    if reservation.genesis_candidate is not None:
        candidate = reservation.genesis_candidate
        species = _species_canon(reservation.species_id, catalog=catalog)
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
        return {
            "metadata": {
                "name": reservation.name,
                "original_name": reservation.original_name,
                "personal_story": reservation.personal_story,
                "age_months": reservation.age_months,
                "life_stage": reservation.life_stage,
                "gender": reservation.gender,
                "version": "genesis-v1",
                "description": "、".join(labels),
                "appearance": {
                    "height": reservation.height,
                    "build": reservation.build,
                    "species": reservation.species_id,
                    "height_scale": height_scale,
                    "build_scale": build_scale,
                },
                **_portrait_metadata(reservation),
            },
            "big_five": big_five,
            # The reveal story is a display summary until a structured
            # biography is validated and committed by Genesis.  Keep the
            # runtime self-description anchored to Profile/Canon so an
            # unverified model paragraph cannot become an identity fact.
            "self_description": (
                f"我是 {reservation.name}，正式物种名是 {species.display_name}；"
                f"我来自 {ELFARIA_CANON.display_name} 的 "
                f"{ELFARIA_CANON.known_region_name}。"
            ),
            "species_name": species.display_name,
            "identity_facts": (
                f"正式物种名是 {species.display_name}，{species.earth_shape_label} 只是地球侧形态说明。",
                f"来自 {ELFARIA_CANON.display_name} 的 {ELFARIA_CANON.known_region_name}。",
                ELFARIA_CANON.earth_arrival_statement,
                f"{ELFARIA_CANON.earth_home_name} 是在地球生活的基地和家。",
            ),
            "behavior_anchors": species.earth_first_contact_cues,
            "sensory_biases": species.common_sensory_biases,
            "species_knowledge": species.common_knowledge,
            "knowledge_boundaries": ELFARIA_CANON.knowledge_boundaries,
            "norms": (
                "尊重自愿选择，不把猜测说成亲历。",
                "不知道时说明不知道，并在真实接触中学习地球。",
            ),
            "speech_style": {
                "greetings": ("你好，我来啦。", "很高兴见到你。"),
                "verbal_ticks": "呢",
            },
            "derivation": {
                "preset": "genesis-v1",
                "provenance": "questionnaire",
                "seed": candidate.seed,
            },
        }
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
    greetings = rng.sample(greeting_pool, rng.randint(2, min(3, len(greeting_pool))))
    species = _species_canon(reservation.species_id, catalog=catalog)
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
        "self_description": (
            f"我是 {reservation.name}，正式物种名是 {species.display_name}；"
            f"我来自 {ELFARIA_CANON.display_name} 的 {ELFARIA_CANON.known_region_name}。"
        ),
        "species_name": species.display_name,
        "identity_facts": (
            f"正式物种名是 {species.display_name}，{species.earth_shape_label} 只是地球侧形态说明。",
            f"来自 {ELFARIA_CANON.display_name} 的 {ELFARIA_CANON.known_region_name}。",
            ELFARIA_CANON.earth_arrival_statement,
            f"{ELFARIA_CANON.earth_home_name} 是在地球生活的基地和家。",
        ),
        "behavior_anchors": species.earth_first_contact_cues,
        "sensory_biases": species.common_sensory_biases,
        "species_knowledge": species.common_knowledge,
        "knowledge_boundaries": ELFARIA_CANON.knowledge_boundaries,
        "norms": (
            "尊重自愿选择，不把猜测说成亲历。",
            "不知道时说明不知道，并在真实接触中学习地球。",
        ),
        "speech_style": {
            "greetings": greetings,
            "mutter_templates": mutter_templates,
            "verbal_ticks": rng.choice(_VERBAL_TICKS),
        },
    }


def _genesis_bundle(
    reservation: AcceptedAdoptionReservation,
    profile,
    selfhood_seed: dict[str, object],
    *,
    catalog: SpeciesCatalog | None = None,
) -> GenesisBundle:
    """Build the small, explicit set of facts known at first arrival."""
    species = _species_canon(reservation.species_id, catalog=catalog)
    raw_big_five = selfhood_seed.get("big_five", {})
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
    speech_style = selfhood_seed.get("speech_style", {})
    if not isinstance(speech_style, dict):
        speech_style = {}
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
            sensory_biases=species.common_sensory_biases,
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
            species_knowledge=species.common_knowledge,
        ),
        biography_plan=BiographyEnrichmentPlan(
            allowed_memory_seed_ids=(
                "arrival-gateway",
                "first-home",
                "earth-first-contact",
            ),
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
