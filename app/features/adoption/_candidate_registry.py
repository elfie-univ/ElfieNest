"""Process-local, short-lived Adoption candidate snapshots."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, replace
from datetime import date

from elfie.profile import get_species_canon_for_technical_id

from .errors import AdoptionCandidateSetExpired, AdoptionInvalid
from .models import (
    CandidateAppearance,
    CandidateGender,
    CandidateRepliesResult,
    CandidateReplyResult,
    CandidateReplyStatus,
    CandidateResult,
    CandidateSetResult,
    ElfieGender,
    ExposedLifeStage,
    LifeStage,
    SpeciesId,
)

_CANDIDATE_TTL_SECONDS = 30 * 60
_LIFE_STAGES: tuple[ExposedLifeStage, ...] = (
    "youth",
    "young_adult",
    "mature",
    "elder",
)
_GENDERS: tuple[ElfieGender, ...] = ("male", "female")
_CANDIDATE_NAMES: dict[SpeciesId, tuple[tuple[str, str], ...]] = {
    "fox": (
        ("阿洛", "洛洛"),
        ("洛弥", "米娅"),
        ("柚子", "小柚"),
        ("星遥", "遥遥"),
        ("赤砂", "砂砂"),
    ),
    "dog": (
        ("布谷", "布布"),
        ("诺拉", "诺诺"),
        ("山雀", "小山"),
        ("米栗", "栗栗"),
        ("奥丘", "丘丘"),
    ),
    "cat": (
        ("弥弥", "米米"),
        ("阿澜", "澜澜"),
        ("星栖", "栖栖"),
        ("绒昼", "昼昼"),
        ("奈可", "可可"),
    ),
}
_PERSONALITY_TAGS: dict[str, tuple[str, str]] = {
    "活泼好动": ("主动回应", "喜欢热闹"),
    "安静温顺": ("温和陪伴", "慢慢熟悉"),
    "好奇探索": ("好奇探索", "喜欢分享"),
    "胆小害羞": ("细腻敏感", "需要安全感"),
    "傲娇独立": ("保留空间", "有自己的节奏"),
    "完全随机": ("独一无二", "等待认识"),
}


@dataclass(frozen=True)
class CandidateSnapshot:
    public: CandidateResult
    personality_style: str
    height: str
    build: str
    appearance_seed: int
    face: str
    signature: str
    birth_date: str


@dataclass(frozen=True)
class CandidateSetSnapshot:
    candidate_set_id: str
    owner_user_id: int
    created_at: float
    candidates: tuple[CandidateSnapshot, ...]
    invited_candidate_ids: tuple[str, ...] = ()
    accepted_candidate_ids: tuple[str, ...] = ()


class CandidateRegistry:
    """The existing 30-minute candidate workspace scoped to one process."""

    def __init__(self) -> None:
        self._candidate_sets: dict[str, CandidateSetSnapshot] = {}

    def create(
        self,
        *,
        owner_user_id: int,
        species_id: SpeciesId,
        life_stage: LifeStage,
        gender: CandidateGender,
        appearance: CandidateAppearance,
        answers: tuple[str, ...],
        personality_styles: tuple[str, ...],
    ) -> CandidateSetResult:
        if len(answers) != 5 or any(not answer for answer in answers):
            raise AdoptionInvalid("answers 必须包含 5 个相处问题答案")
        if not personality_styles:
            raise AdoptionInvalid("当前没有可用的性格风格")
        candidate_set_id = secrets.token_urlsafe(18)
        seed = secrets.randbits(63)
        candidates = tuple(
            self._build_candidate(
                species_id=species_id,
                life_stage=life_stage,
                gender=gender,
                appearance=appearance,
                answers=answers,
                index=index,
                seed=seed,
                personality_style=personality_styles[index % len(personality_styles)],
            )
            for index in range(5)
        )
        self._purge_expired()
        self._candidate_sets[candidate_set_id] = CandidateSetSnapshot(
            candidate_set_id=candidate_set_id,
            owner_user_id=owner_user_id,
            created_at=time.monotonic(),
            candidates=candidates,
        )
        return CandidateSetResult(
            candidate_set_id=candidate_set_id,
            candidates=tuple(candidate.public for candidate in candidates),
        )

    def reply(
        self,
        *,
        owner_user_id: int,
        candidate_set_id: str,
        candidate_ids: tuple[str, ...],
    ) -> CandidateRepliesResult:
        if not 1 <= len(candidate_ids) <= 3 or len(set(candidate_ids)) != len(
            candidate_ids
        ):
            raise AdoptionInvalid("candidate_ids 必须选择 1-3 位候选")
        snapshot = self._get(candidate_set_id, owner_user_id=owner_user_id)
        lookup = {
            candidate.public.candidate_id: candidate
            for candidate in snapshot.candidates
        }
        if any(candidate_id not in lookup for candidate_id in candidate_ids):
            raise AdoptionCandidateSetExpired("候选名单已变化，请重新发送意向")
        replies: list[CandidateReplyResult] = []
        accepted_ids: list[str] = []
        for index, candidate_id in enumerate(candidate_ids):
            candidate = lookup[candidate_id]
            status: CandidateReplyStatus = (
                "accepted" if index < max(1, min(2, len(candidate_ids))) else "unsure"
            )
            if status == "accepted":
                accepted_ids.append(candidate_id)
            replies.append(
                CandidateReplyResult(
                    candidate=candidate.public,
                    status=status,
                    message=(
                        "我读完你的同行意向了，愿意继续认识你，也想看看你说的 Nest。"
                        if status == "accepted"
                        else "我对这份意向还想再想一想，但很高兴收到你的信。"
                    ),
                )
            )
        self._candidate_sets[candidate_set_id] = replace(
            snapshot,
            invited_candidate_ids=candidate_ids,
            accepted_candidate_ids=tuple(accepted_ids),
        )
        return CandidateRepliesResult(
            candidate_set_id=candidate_set_id,
            replies=tuple(replies),
        )

    def accepted(
        self,
        *,
        owner_user_id: int,
        candidate_set_id: str,
        candidate_id: str,
    ) -> CandidateSnapshot:
        snapshot = self._get(candidate_set_id, owner_user_id=owner_user_id)
        if candidate_id not in snapshot.accepted_candidate_ids:
            from .errors import AdoptionCandidateNotAccepted

            raise AdoptionCandidateNotAccepted("这位候选还没有同意继续认识")
        for candidate in snapshot.candidates:
            if candidate.public.candidate_id == candidate_id:
                return candidate
        raise AdoptionCandidateSetExpired("没有找到这位候选，请重新生成名单")

    def _get(
        self,
        candidate_set_id: str,
        *,
        owner_user_id: int,
    ) -> CandidateSetSnapshot:
        self._purge_expired()
        snapshot = self._candidate_sets.get(candidate_set_id)
        if snapshot is None or snapshot.owner_user_id != owner_user_id:
            raise AdoptionCandidateSetExpired("这份候选名单已失效，请重新发送意向")
        return snapshot

    def _purge_expired(self) -> None:
        now = time.monotonic()
        expired = tuple(
            candidate_set_id
            for candidate_set_id, snapshot in self._candidate_sets.items()
            if now - snapshot.created_at > _CANDIDATE_TTL_SECONDS
        )
        for candidate_set_id in expired:
            self._candidate_sets.pop(candidate_set_id, None)

    @staticmethod
    def _build_candidate(
        *,
        species_id: SpeciesId,
        life_stage: LifeStage,
        gender: CandidateGender,
        appearance: CandidateAppearance,
        answers: tuple[str, ...],
        index: int,
        seed: int,
        personality_style: str,
    ) -> CandidateSnapshot:
        names = _CANDIDATE_NAMES[species_id][index]
        chosen_stage = (
            _LIFE_STAGES[index % len(_LIFE_STAGES)]
            if life_stage == "any"
            else life_stage
        )
        chosen_gender = _GENDERS[index % len(_GENDERS)] if gender == "any" else gender
        appearance_tags, height, build = _appearance_snapshot(appearance)
        personality_tags = _PERSONALITY_TAGS.get(
            personality_style,
            _PERSONALITY_TAGS["完全随机"],
        )
        species = get_species_canon_for_technical_id(species_id)
        question_hint = answers[index % len(answers)]
        public = CandidateResult(
            candidate_id=f"{seed:016x}-{index + 1}",
            original_name=names[0],
            suggested_name=names[1],
            species_id=species_id,
            life_stage=chosen_stage,
            gender=chosen_gender,
            image_url=f"/adoption/{species_id}.svg",
            appearance_tags=appearance_tags,
            personality_tags=personality_tags,
            introduction=(
                f"我的正式物种名是 {species.display_name}，外形接近 {species.earth_shape_label}；"
                f"我在报名表里写下了：{personality_tags[0]}，也愿意慢慢了解你的生活。"
            ),
            compatibility=f"你们都提到了“{question_hint}”，这可能是一个不错的开始。",
        )
        return CandidateSnapshot(
            public=public,
            personality_style=personality_style,
            height=height,
            build=build,
            appearance_seed=seed + index * 7919,
            face=appearance.face,
            signature=appearance.signature,
            birth_date=_birth_date_for_stage(chosen_stage, index),
        )


def _appearance_snapshot(
    appearance: CandidateAppearance,
) -> tuple[tuple[str, ...], str, str]:
    height = {"small": "short", "tall": "tall"}.get(
        appearance.stature,
        "standard",
    )
    build = {"slim": "slim", "round": "plump"}.get(
        appearance.build,
        "standard",
    )
    tags = (
        {
            "small": "小巧",
            "standard": "适中",
            "tall": "高挑",
            "any": "身量交给缘分",
        }.get(appearance.stature, "身量交给缘分"),
        {
            "slim": "轻盈",
            "standard": "匀称",
            "round": "圆润",
            "any": "体态自然",
        }.get(appearance.build, "体态自然"),
        {
            "soft": "圆润柔和",
            "balanced": "自然均衡",
            "defined": "利落鲜明",
            "any": "自然脸型",
        }.get(appearance.face, "自然脸型"),
    )
    signature = {
        "warm": "温暖毛色",
        "marked": "明显花纹",
        "ears": "特色耳尾",
    }.get(appearance.signature, "第一眼交给缘分")
    return tags + (signature,), height, build


def _birth_date_for_stage(stage: ExposedLifeStage, index: int) -> str:
    years = {"youth": 12, "young_adult": 22, "mature": 38, "elder": 58}[stage]
    return date(
        date.today().year - years,
        ((index + 1) * 2) % 12 + 1,
        (index + 4) % 25 + 1,
    ).isoformat()


__all__ = ("CandidateRegistry", "CandidateSnapshot")
