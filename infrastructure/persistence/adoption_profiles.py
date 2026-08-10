"""Final Elfie profile-workspace Adapter used by Resident Admission."""

from __future__ import annotations

import random
import shutil
from dataclasses import replace
from pathlib import Path

from ai_runtime.storage.data_layout import ensure_final_elfie_layout, final_root_layout
from app.features.adoption import AcceptedAdoptionReservation
from app.orchestration.resident_admission import ResidentAdmissionPortError
from elfie.profile import (
    PERSONALITY_PRESETS,
    AppearanceResolver,
    ElfieProfileRepository,
    create_visual_profile,
)

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

    def __init__(self, data_home: Path) -> None:
        self._data_home = data_home

    def materialize(self, reservation: AcceptedAdoptionReservation) -> str:
        try:
            layout = ensure_final_elfie_layout(self._data_home, reservation.elfie_id)
            profile = create_visual_profile(
                elfie_id=reservation.elfie_id,
                display_name=reservation.name,
                species_id=reservation.species_id,
                seed=reservation.appearance_seed,
                height_direction=reservation.height,
                build_direction=reservation.build,
                appearance_overrides=_appearance_overrides(reservation),
            )
            resolved = AppearanceResolver().resolve(profile)
            profile = replace(
                profile,
                personality=_personality(
                    reservation, resolved.height_scale, resolved.build_scale
                ),
                capabilities=_capabilities(),
                system_limits=_system_limits(reservation.height, reservation.build),
            )
            ElfieProfileRepository(layout.profile.parent).save(profile)
            return str(layout.workspace)
        except (OSError, TypeError, ValueError) as error:
            self._release_quietly(reservation.elfie_id)
            raise ResidentAdmissionPortError(
                "unable to materialize Elfie profile"
            ) from error

    def release(self, elfie_id: str) -> None:
        try:
            workspace = final_root_layout(self._data_home).elfie(elfie_id).workspace
            if workspace.exists():
                shutil.rmtree(workspace)
        except (OSError, ValueError) as error:
            raise ResidentAdmissionPortError(
                "unable to release Elfie workspace"
            ) from error

    def _release_quietly(self, elfie_id: str) -> None:
        try:
            workspace = final_root_layout(self._data_home).elfie(elfie_id).workspace
            shutil.rmtree(workspace, ignore_errors=True)
        except ValueError:
            return


def _appearance_overrides(
    reservation: AcceptedAdoptionReservation,
) -> dict[str, object]:
    overrides: dict[str, object] = {}
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
            "palette_id": "golden" if reservation.species_id == "fox" else "cream"
        }
    elif reservation.signature == "marked":
        overrides["coat"] = {"pattern_id": "face_mask"}
    return overrides


def _personality(
    reservation: AcceptedAdoptionReservation,
    height_scale: float,
    build_scale: float,
) -> dict[str, object]:
    ranges = PERSONALITY_PRESETS.get(reservation.personality_style)
    if ranges is None:
        raise ValueError(f"unknown personality style: {reservation.personality_style}")
    big_five = {
        trait: round(random.uniform(lower, upper), 4)
        for trait, (lower, upper) in ranges.items()
    }
    mutter_templates: dict[str, list[str]] = {}
    for mood, templates in _MUTTER_TEMPLATES.items():
        selected = random.sample(templates, random.randint(1, min(2, len(templates))))
        mutter_templates[mood] = [
            template.replace("{name}", reservation.name) for template in selected
        ]
    greeting_pool = _GREETINGS.get(
        reservation.personality_style,
        _GREETINGS["完全随机"],
    )
    greetings = random.sample(
        greeting_pool, random.randint(2, min(3, len(greeting_pool)))
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
            "verbal_ticks": random.choice(_VERBAL_TICKS),
        },
    }


def _capabilities() -> dict[str, object]:
    mandatory = ["nod_head", "blink_eyes"]
    optional = [action for action in _ACTIONS if action not in mandatory]
    actions = mandatory + random.sample(optional, random.randint(1, 3))
    random.shuffle(actions)
    return {
        "carrier_type": "smart_plush_toy",
        "actuators": {
            "speech": {
                "enabled": True,
                "max_words_per_minute": random.randint(80, 150),
            },
            "motion": {
                "enabled": True,
                "supported_actions": actions,
                "speed_limits": {
                    "max_servo_angle_speed": round(random.uniform(40, 80), 2)
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


def _system_limits(height: str, build: str) -> dict[str, object]:
    depletion_rate = random.uniform(0.003, 0.008)
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
                "depletion_per_remote_chat": round(random.uniform(2.0, 3.5), 2),
                "depletion_per_local_chat": round(random.uniform(0.3, 0.8), 2),
                "recovery_rate_sleep_per_sec": round(random.uniform(0.03, 0.08), 4),
            },
            "fatigue": {
                "initial_value": 0.0,
                "max_value": 100.0,
                "accumulation_rate_per_sec": round(random.uniform(0.002, 0.005), 4),
                "decay_rate_sleep_per_sec": round(random.uniform(0.03, 0.06), 4),
                "hibernation_threshold": 95.0,
                "wakeup_threshold": round(random.uniform(10.0, 20.0), 1),
            },
            "runtime_usage": {
                "observe_only": True,
                "daily_token_budget": random.randint(8000, 12000),
                "local_token_cost": 0,
                "remote_token_cost": 1,
            },
        }
    }


__all__ = ("FinalElfieWorkspaceAdapter",)
