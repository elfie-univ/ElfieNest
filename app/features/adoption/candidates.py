"""现场生成领养候选，并在最终确认前保留不可变快照。

候选阶段是 MVP 的短生命周期工作集，不写入正式精灵表，也不预生成大量
精灵。最终确认时只允许使用这个快照中的候选参数，避免预览和落库结果不一致。
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, replace
from typing import Any, Mapping

from app.features.adoption.config import (
    get_allowed_personality_styles,
    get_allowed_species_ids,
)

LIFE_STAGES = ("youth", "young_adult", "mature", "elder")
GENDERS = ("male", "female")
_CANDIDATE_TTL_SECONDS = 30 * 60
_CANDIDATE_NAMES = {
    "fox": (("阿洛", "洛洛"), ("洛弥", "米娅"), ("柚子", "小柚"), ("星遥", "遥遥"), ("赤砂", "砂砂")),
    "dog": (("布谷", "布布"), ("诺拉", "诺诺"), ("山雀", "小山"), ("米栗", "栗栗"), ("奥丘", "丘丘")),
}
_PERSONALITY_TAGS = {
    "活泼好动": ("主动回应", "喜欢热闹"),
    "安静温顺": ("温和陪伴", "慢慢熟悉"),
    "好奇探索": ("好奇探索", "喜欢分享"),
    "胆小害羞": ("细腻敏感", "需要安全感"),
    "傲娇独立": ("保留空间", "有自己的节奏"),
    "完全随机": ("独一无二", "等待认识"),
}


class CandidateSetNotFound(ValueError):
    """候选工作集不存在、已过期或不属于当前用户。"""


@dataclass(frozen=True)
class CandidateSnapshot:
    candidate_id: str
    original_name: str
    suggested_name: str
    species_id: str
    life_stage: str
    gender: str
    image_url: str
    appearance_tags: tuple[str, ...]
    personality_tags: tuple[str, ...]
    introduction: str
    compatibility: str
    personality_style: str
    height: str
    build: str
    appearance_overrides: dict[str, Any]
    appearance_seed: int
    birth_date: str

    def public_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "original_name": self.original_name,
            "suggested_name": self.suggested_name,
            "species_id": self.species_id,
            "life_stage": self.life_stage,
            "gender": self.gender,
            "image_url": self.image_url,
            "appearance_tags": list(self.appearance_tags),
            "personality_tags": list(self.personality_tags),
            "introduction": self.introduction,
            "compatibility": self.compatibility,
        }


@dataclass(frozen=True)
class CandidateSet:
    candidate_set_id: str
    user_id: int
    created_at: float
    intent: dict[str, Any]
    candidates: tuple[CandidateSnapshot, ...]
    invited_candidate_ids: tuple[str, ...] = ()
    accepted_candidate_ids: tuple[str, ...] = ()


_CANDIDATE_SETS: dict[str, CandidateSet] = {}


def create_candidate_set(
    *,
    user_id: int,
    species_id: str,
    life_stage: str,
    gender: str,
    appearance: Mapping[str, Any],
    answers: list[str],
    db_path: str,
) -> CandidateSet:
    allowed_species = get_allowed_species_ids(db_path)
    if species_id not in allowed_species:
        raise ValueError(f"species_id 必须是 {allowed_species}")
    if life_stage not in (*LIFE_STAGES, "any"):
        raise ValueError("life_stage 必须是 youth、young_adult、mature、elder 或 any")
    if gender not in (*GENDERS, "any"):
        raise ValueError("gender 必须是 male、female 或 any")
    if len(answers) != 5 or any(not isinstance(answer, str) or not answer for answer in answers):
        raise ValueError("answers 必须包含 5 个相处问题答案")

    candidate_set_id = secrets.token_urlsafe(18)
    seed = secrets.randbits(63)
    allowed_styles = tuple(get_allowed_personality_styles(db_path))
    candidates = tuple(
        _build_candidate(
            species_id=species_id,
            life_stage=life_stage,
            gender=gender,
            appearance=appearance,
            answers=answers,
            index=index,
            seed=seed,
            personality_style=allowed_styles[index % len(allowed_styles)],
        )
        for index in range(5)
    )
    snapshot = CandidateSet(
        candidate_set_id=candidate_set_id,
        user_id=user_id,
        created_at=time.monotonic(),
        intent={
            "species_id": species_id,
            "life_stage": life_stage,
            "gender": gender,
            "appearance": dict(appearance),
            "answers": list(answers),
        },
        candidates=candidates,
    )
    _purge_expired()
    _CANDIDATE_SETS[candidate_set_id] = snapshot
    return snapshot


def get_candidate_set(candidate_set_id: str, *, user_id: int) -> CandidateSet:
    _purge_expired()
    snapshot = _CANDIDATE_SETS.get(candidate_set_id)
    if snapshot is None or snapshot.user_id != user_id:
        raise CandidateSetNotFound("这份候选名单已失效，请重新发送意向")
    return snapshot


def reply_to_candidates(
    candidate_set_id: str,
    *,
    user_id: int,
    candidate_ids: list[str],
) -> list[dict[str, Any]]:
    if not 1 <= len(candidate_ids) <= 3 or len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("candidate_ids 必须选择 1-3 位候选")
    snapshot = get_candidate_set(candidate_set_id, user_id=user_id)
    lookup = {candidate.candidate_id: candidate for candidate in snapshot.candidates}
    if any(candidate_id not in lookup for candidate_id in candidate_ids):
        raise CandidateSetNotFound("候选名单已变化，请重新发送意向")
    replies: list[dict[str, Any]] = []
    accepted_ids: list[str] = []
    for index, candidate_id in enumerate(candidate_ids):
        candidate = lookup[candidate_id]
        accepted = index < max(1, min(2, len(candidate_ids)))
        if accepted:
            accepted_ids.append(candidate_id)
        replies.append({
            **candidate.public_dict(),
            "status": "accepted" if accepted else "unsure",
            "message": (
                "我读完你的同行意向了，愿意继续认识你，也想看看你说的 Nest。"
                if accepted
                else "我对这份意向还想再想一想，但很高兴收到你的信。"
            ),
        })
    _CANDIDATE_SETS[candidate_set_id] = replace(
        snapshot,
        invited_candidate_ids=tuple(candidate_ids),
        accepted_candidate_ids=tuple(accepted_ids),
    )
    return replies


def find_candidate(candidate_set_id: str, *, user_id: int, candidate_id: str) -> CandidateSnapshot:
    snapshot = get_candidate_set(candidate_set_id, user_id=user_id)
    for candidate in snapshot.candidates:
        if candidate.candidate_id == candidate_id:
            return candidate
    raise CandidateSetNotFound("没有找到这位候选，请重新生成名单")


def is_accepted_candidate(candidate_set_id: str, *, user_id: int, candidate_id: str) -> bool:
    snapshot = get_candidate_set(candidate_set_id, user_id=user_id)
    return candidate_id in snapshot.accepted_candidate_ids


def _build_candidate(
    *,
    species_id: str,
    life_stage: str,
    gender: str,
    appearance: Mapping[str, Any],
    answers: list[str],
    index: int,
    seed: int,
    personality_style: str,
) -> CandidateSnapshot:
    names = _CANDIDATE_NAMES[species_id][index]
    chosen_stage = life_stage if life_stage != "any" else LIFE_STAGES[index % len(LIFE_STAGES)]
    chosen_gender = gender if gender != "any" else GENDERS[index % len(GENDERS)]
    appearance_tags, height, build, overrides = _appearance_snapshot(species_id, appearance, index)
    tags = _PERSONALITY_TAGS.get(personality_style, _PERSONALITY_TAGS["完全随机"])
    question_hint = answers[index % len(answers)]
    return CandidateSnapshot(
        candidate_id=f"{seed:016x}-{index + 1}",
        original_name=names[0],
        suggested_name=names[1],
        species_id=species_id,
        life_stage=chosen_stage,
        gender=chosen_gender,
        image_url=f"/adoption/{species_id}.svg",
        appearance_tags=appearance_tags,
        personality_tags=tags,
        introduction=f"我在报名表里写下了：{tags[0]}，也愿意慢慢了解你的生活。",
        compatibility=f"你们都提到了“{question_hint}”，这可能是一个不错的开始。",
        personality_style=personality_style,
        height=height,
        build=build,
        appearance_overrides=overrides,
        appearance_seed=seed + index * 7919,
        birth_date=_birth_date_for_stage(chosen_stage, index),
    )


def _appearance_snapshot(
    species_id: str,
    appearance: Mapping[str, Any],
    index: int,
) -> tuple[tuple[str, ...], str, str, dict[str, Any]]:
    stature = str(appearance.get("stature", "any"))
    build_choice = str(appearance.get("build", "any"))
    face = str(appearance.get("face", "any"))
    signature = str(appearance.get("signature", "any"))
    height = {"small": "short", "tall": "tall"}.get(stature, "standard")
    build = {"slim": "slim", "round": "plump"}.get(build_choice, "standard")
    overrides: dict[str, Any] = {}
    if face == "soft":
        overrides["face"] = {"cheek_fullness_bias": 0.42, "lower_face_fullness_bias": 0.28}
    elif face == "defined":
        overrides["face"] = {"cheek_fullness_bias": -0.38, "lower_face_fullness_bias": -0.24}
    if signature == "warm":
        overrides["coat"] = {"palette_id": "golden" if species_id == "fox" else "cream"}
    elif signature == "marked":
        overrides["coat"] = {"pattern_id": "face_mask"}
    tags = (
        {"small": "小巧", "standard": "适中", "tall": "高挑", "any": "身量交给缘分"}.get(stature, "身量交给缘分"),
        {"slim": "轻盈", "standard": "匀称", "round": "圆润", "any": "体态自然"}.get(build_choice, "体态自然"),
        {"soft": "圆润柔和", "balanced": "自然均衡", "defined": "利落鲜明", "any": "自然脸型"}.get(face, "自然脸型"),
    )
    if signature == "warm":
        tags += ("温暖毛色",)
    elif signature == "marked":
        tags += ("明显花纹",)
    elif signature == "ears":
        tags += ("特色耳尾",)
    else:
        tags += ("第一眼交给缘分",)
    return tags, height, build, overrides


def _birth_date_for_stage(stage: str, index: int) -> str:
    from datetime import date

    years = {"youth": 12, "young_adult": 22, "mature": 38, "elder": 58}.get(stage, 28)
    return date(date.today().year - years, ((index + 1) * 2) % 12 + 1, (index + 4) % 25 + 1).isoformat()


def _purge_expired() -> None:
    now = time.monotonic()
    expired = [key for key, value in _CANDIDATE_SETS.items() if now - value.created_at > _CANDIDATE_TTL_SECONDS]
    for key in expired:
        _CANDIDATE_SETS.pop(key, None)


__all__ = (
    "CandidateSetNotFound",
    "CandidateSnapshot",
    "create_candidate_set",
    "find_candidate",
    "get_candidate_set",
    "is_accepted_candidate",
    "reply_to_candidates",
)
