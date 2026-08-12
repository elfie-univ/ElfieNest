"""Authorized Adoption use-cases over one policy and ownership fact path."""

from __future__ import annotations

import secrets

from app.features.accounts import AccountPrincipal

from ._candidate_registry import CandidateRegistry
from .errors import (
    AdoptionCapacityReached,
    AdoptionInvalid,
    AdoptionOwnerNotFound,
    AdoptionUnavailable,
)
from .models import (
    AcceptedAdoptionReservation,
    AdoptionOptionsResult,
    AdoptionQuota,
    CandidateRepliesResult,
    CandidateSetResult,
    CreateCandidateSetCommand,
    GetAdoptionOptionsQuery,
    LifeStage,
    ReplyToCandidatesCommand,
    ReserveAcceptedAdoptionCommand,
)
from .port_models import AdoptionPolicyRecord, AdoptionReservationRecord
from .ports import (
    AdoptionPersistencePort,
    AdoptionPolicyPort,
    AdoptionPortCapacityReached,
    AdoptionPortError,
    AdoptionPortOwnerNotFound,
)

_HEIGHTS = ("short", "standard", "tall")
_BUILDS = ("slim", "standard", "plump")
_LIFE_STAGES: tuple[LifeStage, ...] = (
    "youth",
    "young_adult",
    "mature",
    "elder",
    "any",
)


class AdoptionService:
    def __init__(
        self,
        policy: AdoptionPolicyPort,
        persistence: AdoptionPersistencePort,
        candidates: CandidateRegistry | None = None,
    ) -> None:
        self._policy = policy
        self._persistence = persistence
        self._candidates = candidates or CandidateRegistry()

    def get_options(
        self,
        principal: AccountPrincipal,
        query: GetAdoptionOptionsQuery,
    ) -> AdoptionOptionsResult:
        _ = query
        policy = self._load_policy()
        try:
            quota = self._persistence.get_quota(
                principal.user_id,
                policy.default_elfie_limit,
            )
        except AdoptionPortError as error:
            raise AdoptionUnavailable("领养额度暂不可用") from error
        if quota is None:
            raise AdoptionOwnerNotFound("用户不存在")
        remaining = max(0, quota.effective_limit - quota.used)
        return AdoptionOptionsResult(
            personality_styles=policy.enabled_personality_styles,
            species_ids=policy.allowed_species_ids,
            heights=_HEIGHTS,
            builds=_BUILDS,
            life_stages=_LIFE_STAGES,
            quota=AdoptionQuota(
                used=quota.used,
                maximum=quota.effective_limit,
                remaining=remaining,
                can_adopt=remaining > 0,
            ),
        )

    def create_candidate_set(
        self,
        principal: AccountPrincipal,
        command: CreateCandidateSetCommand,
    ) -> CandidateSetResult:
        policy = self._load_policy()
        if command.species_id not in policy.allowed_species_ids:
            raise AdoptionInvalid(f"species_id 必须是 {policy.allowed_species_ids}")
        return self._candidates.create(
            owner_user_id=principal.user_id,
            species_id=command.species_id,
            life_stage=command.life_stage,
            gender=command.gender,
            appearance=command.appearance,
            answers=command.answers,
            personality_styles=policy.enabled_personality_styles,
        )

    def reply_to_candidates(
        self,
        principal: AccountPrincipal,
        command: ReplyToCandidatesCommand,
    ) -> CandidateRepliesResult:
        return self._candidates.reply(
            owner_user_id=principal.user_id,
            candidate_set_id=command.candidate_set_id,
            candidate_ids=command.candidate_ids,
        )

    def reserve_accepted(
        self,
        principal: AccountPrincipal,
        command: ReserveAcceptedAdoptionCommand,
    ) -> AcceptedAdoptionReservation:
        name = command.name.strip()
        if not name or len(name) > 20:
            raise AdoptionInvalid("名字长度必须在 1-20 字之间")
        candidate = self._candidates.accepted(
            owner_user_id=principal.user_id,
            candidate_set_id=command.candidate_set_id,
            candidate_id=command.candidate_id,
        )
        policy = self._load_policy()
        if candidate.public.species_id not in policy.allowed_species_ids:
            raise AdoptionInvalid(f"species_id 必须是 {policy.allowed_species_ids}")
        if candidate.personality_style not in policy.enabled_personality_styles:
            raise AdoptionInvalid("当前候选的性格风格已停用，请重新生成候选名单")
        elfie_id = f"{secrets.randbelow(100_000_000):08d}"
        reservation = AcceptedAdoptionReservation(
            elfie_id=elfie_id,
            owner_user_id=principal.user_id,
            name=name,
            species_id=candidate.public.species_id,
            personality_style=candidate.personality_style,
            height=candidate.height,
            build=candidate.build,
            appearance_seed=candidate.appearance_seed,
            face=candidate.face,
            signature=candidate.signature,
            gender=candidate.public.gender,
            birth_date=candidate.birth_date,
        )
        try:
            self._persistence.reserve(
                AdoptionReservationRecord(
                    elfie_id=reservation.elfie_id,
                    owner_user_id=reservation.owner_user_id,
                    name=reservation.name,
                    species_id=reservation.species_id,
                    gender=reservation.gender,
                    birth_date=reservation.birth_date,
                    summary=reservation.personality_style,
                ),
                policy.default_elfie_limit,
            )
        except AdoptionPortCapacityReached as error:
            raise AdoptionCapacityReached(error.limit) from error
        except AdoptionPortOwnerNotFound as error:
            raise AdoptionOwnerNotFound("用户不存在") from error
        except AdoptionPortError as error:
            raise AdoptionUnavailable("无法预留领养关系") from error
        return reservation

    def release_reservation(self, reservation: AcceptedAdoptionReservation) -> None:
        try:
            self._persistence.release(reservation.elfie_id)
        except AdoptionPortError as error:
            raise AdoptionUnavailable("无法回滚领养关系") from error

    def _load_policy(self) -> AdoptionPolicyRecord:
        try:
            return self._policy.load_policy()
        except AdoptionPortError as error:
            raise AdoptionUnavailable("领养规则暂不可用") from error


__all__ = ("AdoptionService",)
