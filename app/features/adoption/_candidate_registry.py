"""Short-lived, anonymous Genesis candidate workspaces."""

from __future__ import annotations

import re
import secrets
import time
from dataclasses import dataclass, replace
from datetime import date
from hashlib import blake2b

from elfie.genesis import (
    CandidateSignature,
    GenesisAppearanceIntent,
    GenesisCandidate,
    GenesisEngine,
    GenesisError,
)
from elfie.profile import (
    AppearanceResolver,
    ElfieIdentity,
    ElfieProfile,
    EmbodimentProfile,
    ProfileProvenance,
)

from .errors import AdoptionCandidateSetExpired, AdoptionInvalid, AdoptionUnavailable
from .models import (
    CandidateAppearance,
    CandidateGender,
    CandidateRepliesResult,
    CandidateReplyResult,
    CandidateReplyStatus,
    CandidateResult,
    CandidateSetResult,
    ExposedLifeStage,
    LifeStage,
    SpeciesId,
)
from .ports import AdoptionNarrativePort, CandidatePortraitPort

_CANDIDATE_TTL_SECONDS = 30 * 60
_MAX_CANDIDATE_BATCHES = 3
_LIFE_STAGES: tuple[ExposedLifeStage, ...] = (
    "youth",
    "young_adult",
    "mature",
    "elder",
)


@dataclass(frozen=True)
class CandidateSnapshot:
    """Private candidate data retained until an accepted candidate is committed."""

    public: CandidateResult
    genesis: GenesisCandidate
    personality_style: str
    height: str
    build: str
    appearance_seed: int
    face: str
    signature: str
    birth_date: str
    original_name: str = ""
    suggested_name: str = ""
    personal_story: str = ""


@dataclass(frozen=True)
class CandidateSetSnapshot:
    candidate_set_id: str
    adoption_session_id: str
    owner_user_id: int
    created_at: float
    batch_number: int
    candidates: tuple[CandidateSnapshot, ...]
    invited_candidate_ids: tuple[str, ...] = ()
    accepted_candidate_ids: tuple[str, ...] = ()
    invitation_message: str = ""
    reply_results: tuple[CandidateReplyResult, ...] = ()


@dataclass(frozen=True)
class CandidateSessionSnapshot:
    adoption_session_id: str
    owner_user_id: int
    created_at: float
    batch_count: int
    signatures: tuple[CandidateSignature, ...] = ()
    intent_fingerprint: str = ""


class CandidateRegistry:
    """Own the bounded candidate workspace used by the current API slice.

    The registry deliberately keeps Genesis output anonymous.  Names, stories and
    other prose are not part of a candidate-set response; a later model-backed
    reveal stage will add them only after an invitation is accepted.
    """

    def __init__(
        self,
        *,
        genesis: GenesisEngine | None = None,
        portraits: CandidatePortraitPort | None = None,
        narrative: AdoptionNarrativePort | None = None,
    ) -> None:
        self._genesis = genesis or GenesisEngine()
        self._portraits = portraits
        self._narrative = narrative
        self._candidate_sets: dict[str, CandidateSetSnapshot] = {}
        self._sessions: dict[str, CandidateSessionSnapshot] = {}

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
        adoption_session_id: str | None = None,
        batch_number: int = 1,
    ) -> CandidateSetResult:
        if len(answers) != 5 or any(not answer for answer in answers):
            raise AdoptionInvalid("answers 必须包含 5 个相处问题答案")
        if not personality_styles:
            raise AdoptionInvalid("当前没有可用的性格风格")
        if not 1 <= batch_number <= _MAX_CANDIDATE_BATCHES:
            raise AdoptionInvalid("最多只能生成 3 批匿名候选")
        self._purge_expired()
        intent = GenesisAppearanceIntent(
            stature=appearance.stature,
            build=appearance.build,
            face=appearance.face,
            signature=appearance.signature,
            priority=appearance.priority,
        )
        fingerprint = _intent_fingerprint(
            species_id, life_stage, gender, appearance, answers
        )
        session = self._get_or_create_session(
            adoption_session_id, owner_user_id, fingerprint
        )
        existing = next(
            (
                item
                for item in self._candidate_sets.values()
                if item.owner_user_id == owner_user_id
                and item.adoption_session_id == session.adoption_session_id
                and item.batch_number == batch_number
            ),
            None,
        )
        if existing is not None:
            return CandidateSetResult(
                candidate_set_id=existing.candidate_set_id,
                adoption_session_id=existing.adoption_session_id,
                batch_number=existing.batch_number,
                candidates=tuple(item.public for item in existing.candidates),
            )

        previous_signatures: tuple[CandidateSignature, ...] = ()
        batch = None
        for current_batch in range(1, batch_number + 1):
            batch = self._generate_batch(
                owner_user_id=owner_user_id,
                adoption_session_id=session.adoption_session_id,
                batch_number=current_batch,
                species_id=species_id,
                life_stage=life_stage,
                gender=gender,
                intent=intent,
                answers=answers,
                previous_signatures=previous_signatures,
            )
            previous_signatures += tuple(
                candidate.signature for candidate in batch.candidates
            )
        assert batch is not None
        candidate_set_id = secrets.token_urlsafe(18)
        candidates = tuple(
            self._snapshot(candidate, appearance) for candidate in batch.candidates
        )
        snapshot = CandidateSetSnapshot(
            candidate_set_id=candidate_set_id,
            adoption_session_id=session.adoption_session_id,
            owner_user_id=owner_user_id,
            created_at=time.monotonic(),
            batch_number=batch.batch_number,
            candidates=candidates,
        )
        self._candidate_sets[candidate_set_id] = snapshot
        self._sessions[session.adoption_session_id] = replace(
            session,
            batch_count=max(session.batch_count, batch.batch_number),
            signatures=(
                previous_signatures
                if batch.batch_number >= session.batch_count
                else session.signatures
            ),
        )
        return CandidateSetResult(
            candidate_set_id=candidate_set_id,
            adoption_session_id=session.adoption_session_id,
            batch_number=batch.batch_number,
            candidates=tuple(candidate.public for candidate in candidates),
        )

    def reply(
        self,
        *,
        owner_user_id: int,
        candidate_set_id: str,
        candidate_ids: tuple[str, ...],
        invitation_message: str = "",
    ) -> CandidateRepliesResult:
        if not 1 <= len(candidate_ids) <= 3 or len(set(candidate_ids)) != len(
            candidate_ids
        ):
            raise AdoptionInvalid("candidate_ids 必须选择 1-3 位候选")
        invitation_message = _validate_invitation_message(invitation_message)
        snapshot = self._get(candidate_set_id, owner_user_id=owner_user_id)
        lookup = {
            candidate.public.candidate_id: candidate
            for candidate in snapshot.candidates
        }
        if any(candidate_id not in lookup for candidate_id in candidate_ids):
            raise AdoptionCandidateSetExpired("候选名单已变化，请重新发送意向")
        if snapshot.invited_candidate_ids:
            if (
                snapshot.invited_candidate_ids == candidate_ids
                and snapshot.invitation_message == invitation_message
                and snapshot.reply_results
            ):
                return CandidateRepliesResult(
                    candidate_set_id=candidate_set_id,
                    replies=snapshot.reply_results,
                )
            raise AdoptionInvalid("这组邀请已经发送")
        narrative = self._narrative
        if narrative is not None and not narrative.is_ready():
            raise AdoptionUnavailable("强模型不可用，暂时不能生成候选身份")
        replies: list[CandidateReplyResult] = []
        accepted_ids = [
            candidate_id
            for candidate_id in candidate_ids
            if _acceptance_score(
                snapshot.adoption_session_id, candidate_id, "acceptance"
            )
            < 0.8
        ]
        if not accepted_ids:
            accepted_ids = [
                min(
                    candidate_ids,
                    key=lambda candidate_id: _acceptance_score(
                        snapshot.adoption_session_id, candidate_id, "guarantee"
                    ),
                )
            ]
        updated_candidates = list(snapshot.candidates)
        for candidate_id in candidate_ids:
            candidate = lookup[candidate_id]
            status: CandidateReplyStatus = (
                "accepted" if candidate_id in accepted_ids else "unsure"
            )
            if status == "accepted":
                if narrative is None:
                    reveal = None
                else:
                    try:
                        reveal = narrative.reveal(candidate.genesis, invitation_message)
                    except (OSError, RuntimeError, ValueError) as error:
                        raise AdoptionUnavailable("候选身份生成失败") from error
                    candidate = replace(
                        candidate,
                        original_name=reveal.original_name,
                        suggested_name=reveal.suggested_name,
                        personal_story=reveal.personal_story,
                    )
                    lookup[candidate_id] = candidate
                    updated_candidates = [
                        candidate if item.public.candidate_id == candidate_id else item
                        for item in updated_candidates
                    ]
            else:
                reveal = None
            replies.append(
                CandidateReplyResult(
                    candidate=candidate.public,
                    status=status,
                    message=(
                        "我读完你的同行意向了，愿意继续认识你。"
                        if status == "accepted"
                        else "我还想再想一想，但很高兴收到你的信。"
                    ),
                    reveal=reveal,
                )
            )
        self._candidate_sets[candidate_set_id] = replace(
            snapshot,
            candidates=tuple(updated_candidates),
            invited_candidate_ids=candidate_ids,
            accepted_candidate_ids=tuple(accepted_ids),
            invitation_message=invitation_message,
            reply_results=tuple(replies),
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

    def _get_or_create_session(
        self,
        adoption_session_id: str | None,
        owner_user_id: int,
        intent_fingerprint: str,
    ) -> CandidateSessionSnapshot:
        if adoption_session_id is None:
            return CandidateSessionSnapshot(
                adoption_session_id=secrets.token_urlsafe(18),
                owner_user_id=owner_user_id,
                created_at=time.monotonic(),
                batch_count=0,
                intent_fingerprint=intent_fingerprint,
            )
        session = self._sessions.get(adoption_session_id)
        if session is None:
            return CandidateSessionSnapshot(
                adoption_session_id=adoption_session_id,
                owner_user_id=owner_user_id,
                created_at=time.monotonic(),
                batch_count=0,
                intent_fingerprint=intent_fingerprint,
            )
        if session.owner_user_id != owner_user_id:
            raise AdoptionCandidateSetExpired("领养会话已失效，请重新开始")
        if session.intent_fingerprint != intent_fingerprint:
            raise AdoptionInvalid("领养意向已经变化，请重新开始")
        return session

    def _generate_batch(
        self,
        *,
        owner_user_id: int,
        adoption_session_id: str,
        batch_number: int,
        species_id: SpeciesId,
        life_stage: LifeStage,
        gender: CandidateGender,
        intent: GenesisAppearanceIntent,
        answers: tuple[str, ...],
        previous_signatures: tuple[CandidateSignature, ...],
    ):
        last_error: GenesisError | None = None
        for attempt in range(8):
            try:
                return self._genesis.generate_batch(
                    master_seed=_master_seed(
                        owner_user_id,
                        adoption_session_id,
                        batch_number,
                        attempt,
                    ),
                    batch_number=batch_number,
                    species_id=species_id,
                    life_stage=life_stage,
                    gender=gender,
                    appearance=intent,
                    answers=answers,
                    previous_signatures=previous_signatures,
                )
            except GenesisError as error:
                last_error = error
        raise AdoptionInvalid(str(last_error or "候选生成失败")) from last_error

    def _get(
        self, candidate_set_id: str, *, owner_user_id: int
    ) -> CandidateSetSnapshot:
        self._purge_expired()
        snapshot = self._candidate_sets.get(candidate_set_id)
        if snapshot is None or snapshot.owner_user_id != owner_user_id:
            raise AdoptionCandidateSetExpired("这份候选名单已失效，请重新发送意向")
        return snapshot

    def _purge_expired(self) -> None:
        now = time.monotonic()
        expired_sets = tuple(
            key
            for key, snapshot in self._candidate_sets.items()
            if now - snapshot.created_at > _CANDIDATE_TTL_SECONDS
        )
        for key in expired_sets:
            self._candidate_sets.pop(key, None)
        expired_sessions = tuple(
            key
            for key, session in self._sessions.items()
            if now - session.created_at > _CANDIDATE_TTL_SECONDS
        )
        for key in expired_sessions:
            self._sessions.pop(key, None)

    def _snapshot(
        self, candidate: GenesisCandidate, appearance: CandidateAppearance
    ) -> CandidateSnapshot:
        full_body_url, headshot_url = ("", "")
        if self._portraits is not None:
            try:
                full_body_url, headshot_url = self._portraits.render(candidate)
            except (OSError, RuntimeError, ValueError) as error:
                raise AdoptionUnavailable("候选肖像生成不可用") from error
        stage = candidate.life_stage
        public = CandidateResult(
            candidate_id=candidate.candidate_id,
            species_id=candidate.species_id,
            life_stage=stage,  # type: ignore[arg-type]
            age_months=candidate.age_months,
            gender=candidate.gender,  # type: ignore[arg-type]
            full_body_image_url=full_body_url,
            headshot_image_url=headshot_url,
            appearance_tags=_appearance_tags(candidate, appearance),
            personality_tags=candidate.personality.candidate.labels,
            runtime_appearance=_runtime_appearance(candidate),
        )
        return CandidateSnapshot(
            public=public,
            genesis=candidate,
            personality_style="Genesis",
            height=_height_label(candidate),
            build=_build_label(candidate),
            appearance_seed=candidate.seed,
            face=appearance.face,
            signature=appearance.signature,
            birth_date=_birth_date_for_age(candidate.age_months),
        )


def _appearance_tags(
    candidate: GenesisCandidate, intent: CandidateAppearance
) -> tuple[str, ...]:
    stature = (
        "小巧"
        if candidate.appearance.macro.stature_z <= -0.45
        else ("高挑" if candidate.appearance.macro.stature_z >= 0.45 else "适中")
    )
    build = (
        "轻盈"
        if candidate.appearance.macro.body_fat_z <= -0.45
        else ("圆润" if candidate.appearance.macro.body_fat_z >= 0.45 else "匀称")
    )
    face = {"soft": "柔和", "defined": "鲜明"}.get(intent.face, "均衡")
    signature = {"warm": "暖色", "marked": "花纹", "ears": "耳尾"}.get(
        intent.signature, "自然"
    )
    return (stature, build, face, signature)


def _runtime_appearance(candidate: GenesisCandidate) -> dict[str, object]:
    """Resolve the candidate genome into the payload owned by the Godot Web runtime."""
    profile = ElfieProfile(
        schema_version=1,
        identity=ElfieIdentity(
            elfie_id=f"candidate-{candidate.candidate_id}",
            display_name="anonymous-candidate",
            species_id=candidate.species_id,
        ),
        appearance=candidate.appearance,
        provenance=ProfileProvenance(
            generator_version="genesis-v1",
            master_seed=candidate.seed,
            appearance_seed=candidate.seed,
        ),
        embodiment=EmbodimentProfile(),
    )
    return AppearanceResolver().resolve(profile).to_payload()


def _height_label(candidate: GenesisCandidate) -> str:
    return (
        "short"
        if candidate.appearance.macro.stature_z < -0.35
        else ("tall" if candidate.appearance.macro.stature_z > 0.35 else "standard")
    )


def _build_label(candidate: GenesisCandidate) -> str:
    return (
        "slim"
        if candidate.appearance.macro.body_fat_z < -0.35
        else ("plump" if candidate.appearance.macro.body_fat_z > 0.35 else "standard")
    )


def _birth_date_for_age(age_months: int) -> str:
    today = date.today()
    total_months = today.year * 12 + today.month - 1 - age_months
    year, month = divmod(total_months, 12)
    return date(year, month + 1, min(today.day, 28)).isoformat()


def _intent_fingerprint(
    species_id: SpeciesId,
    life_stage: LifeStage,
    gender: CandidateGender,
    appearance: CandidateAppearance,
    answers: tuple[str, ...],
) -> str:
    values = (
        species_id,
        life_stage,
        gender,
        appearance.stature,
        appearance.build,
        appearance.face,
        appearance.signature,
        appearance.priority,
        *answers,
    )
    return blake2b("\x1f".join(values).encode("utf-8"), digest_size=16).hexdigest()


def _master_seed(
    owner_user_id: int,
    adoption_session_id: str,
    batch_number: int,
    attempt: int,
) -> int:
    material = f"{owner_user_id}:{adoption_session_id}:{batch_number}:{attempt}"
    return int.from_bytes(
        blake2b(material.encode("utf-8"), digest_size=8).digest(), "big"
    ) & ((1 << 63) - 1)


def _acceptance_score(
    adoption_session_id: str,
    candidate_id: str,
    purpose: str,
) -> float:
    material = f"{adoption_session_id}:{candidate_id}:{purpose}"
    value = int.from_bytes(
        blake2b(material.encode("utf-8"), digest_size=8).digest(), "big"
    )
    return value / float(1 << 64)


def _validate_invitation_message(value: str) -> str:
    if not isinstance(value, str):
        raise AdoptionInvalid("邀请附言必须是文本")
    value = value.strip()
    if not value:
        return ""
    cjk_count = len(re.findall(r"[\u3400-\u9fff]", value))
    word_count = len(value.split())
    if cjk_count and cjk_count > 50:
        raise AdoptionInvalid("邀请附言中文内容不能超过 50 字")
    if not cjk_count and word_count > 50:
        raise AdoptionInvalid("邀请附言英文内容不能超过 50 个单词")
    if cjk_count and word_count > 50:
        raise AdoptionInvalid("邀请附言不能超过 50 个字/单词")
    return value


__all__ = (
    "CandidateRegistry",
    "CandidateSessionSnapshot",
    "CandidateSnapshot",
    "CandidateSetSnapshot",
)
