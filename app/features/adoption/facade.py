"""Authorized Adoption use-cases over one policy and ownership fact path."""

from __future__ import annotations

import secrets

from app.features.accounts import AccountPrincipal
from elfie.profile import get_species_definition, list_species_definitions

from ._candidate_registry import CandidateRegistry
from .errors import (
    AdoptionCapacityReached,
    AdoptionInvalid,
    AdoptionNestCapacityReached,
    AdoptionOwnerNotFound,
    AdoptionUnavailable,
)
from .models import (
    AcceptedAdoptionReservation,
    AdoptionAvailability,
    AdoptionNestCapacity,
    AdoptionOptionsResult,
    AdoptionQuota,
    AdoptionSpecies,
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
    AdoptionNarrativePort,
    AdoptionPersistencePort,
    AdoptionPolicyPort,
    AdoptionPortCapacityReached,
    AdoptionPortError,
    AdoptionPortNestCapacityReached,
    AdoptionPortOwnerNotFound,
    CandidatePortraitPort,
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
        portraits: CandidatePortraitPort | None = None,
        narrative: AdoptionNarrativePort | None = None,
    ) -> None:
        self._policy = policy
        self._persistence = persistence
        self._narrative = narrative
        self._candidates = candidates or CandidateRegistry(
            portraits=portraits, narrative=narrative
        )

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
            nest_capacity = self._persistence.get_nest_capacity()
        except AdoptionPortError as error:
            raise AdoptionUnavailable("领养额度暂不可用") from error
        if quota is None:
            raise AdoptionOwnerNotFound("用户不存在")
        remaining = max(0, quota.effective_limit - quota.used)
        nest_remaining = max(0, nest_capacity.maximum - nest_capacity.used)
        availability: AdoptionAvailability = (
            "nest_full"
            if nest_remaining == 0
            else "member_quota_full"
            if remaining == 0
            else "available"
            if self._narrative_ready()
            else "model_unavailable"
        )
        return AdoptionOptionsResult(
            personality_styles=policy.enabled_personality_styles,
            species=tuple(
                _species_result(definition.species_id)
                for definition in list_species_definitions()
            ),
            heights=_HEIGHTS,
            builds=_BUILDS,
            life_stages=_LIFE_STAGES,
            quota=AdoptionQuota(
                used=quota.used,
                maximum=quota.effective_limit,
                remaining=remaining,
                can_adopt=remaining > 0,
            ),
            nest_capacity=AdoptionNestCapacity(
                used=nest_capacity.used,
                maximum=nest_capacity.maximum,
                remaining=nest_remaining,
            ),
            availability=availability,
        )

    def create_candidate_set(
        self,
        principal: AccountPrincipal,
        command: CreateCandidateSetCommand,
    ) -> CandidateSetResult:
        policy = self._load_policy()
        try:
            get_species_definition(command.species_id)
        except ValueError as error:
            raise AdoptionInvalid(
                f"不支持的 species_id={command.species_id!r}"
            ) from error
        return self._candidates.create(
            owner_user_id=principal.user_id,
            species_id=command.species_id,
            life_stage=command.life_stage,
            gender=command.gender,
            appearance=command.appearance,
            answers=command.answers,
            personality_styles=policy.enabled_personality_styles,
            adoption_session_id=command.adoption_session_id,
            batch_number=command.batch_number,
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
            invitation_message=command.invitation_message,
        )

    def prepare_accepted(
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
        try:
            get_species_definition(candidate.public.species_id)
        except ValueError as error:
            raise AdoptionInvalid(
                f"不支持的 species_id={candidate.public.species_id!r}"
            ) from error
        elfie_id = f"{secrets.randbelow(100_000_000):08d}"
        reservation = AcceptedAdoptionReservation(
            elfie_id=elfie_id,
            owner_user_id=principal.user_id,
            name=name,
            original_name=candidate.original_name,
            species_id=candidate.public.species_id,
            personality_style=candidate.personality_style,
            height=candidate.height,
            build=candidate.build,
            appearance_seed=candidate.appearance_seed,
            face=candidate.face,
            signature=candidate.signature,
            gender=candidate.public.gender,
            birth_date=candidate.birth_date,
            genesis_candidate=candidate.genesis,
            personal_story=candidate.personal_story,
            age_months=candidate.public.age_months,
            life_stage=candidate.public.life_stage,
            full_body_image_url=(
                command.full_body_image_url or candidate.public.full_body_image_url
            ),
            headshot_image_url=(
                command.headshot_image_url or candidate.public.headshot_image_url
            ),
        )

        return reservation

    def publish_accepted(self, reservation: AcceptedAdoptionReservation) -> None:
        """Atomically publish one fully constructed Elfie as a final resident."""
        policy = self._load_policy()
        try:
            self._persistence.reserve(
                AdoptionReservationRecord(
                    elfie_id=reservation.elfie_id,
                    owner_user_id=reservation.owner_user_id,
                    name=reservation.name,
                    original_name=reservation.original_name,
                    species_id=reservation.species_id,
                    gender=reservation.gender,
                    birth_date=reservation.birth_date,
                    summary=reservation.personality_style,
                ),
                policy.default_elfie_limit,
            )
        except AdoptionPortCapacityReached as error:
            raise AdoptionCapacityReached(error.limit) from error
        except AdoptionPortNestCapacityReached as error:
            raise AdoptionNestCapacityReached(error.limit) from error
        except AdoptionPortOwnerNotFound as error:
            raise AdoptionOwnerNotFound("用户不存在") from error
        except AdoptionPortError as error:
            raise AdoptionUnavailable("无法保存领养关系") from error

    def _load_policy(self) -> AdoptionPolicyRecord:
        try:
            return self._policy.load_policy()
        except AdoptionPortError as error:
            raise AdoptionUnavailable("领养规则暂不可用") from error

    def _narrative_ready(self) -> bool:
        """Expose the same strong-model gate used by the reveal stage."""
        if self._narrative is None:
            return False
        try:
            return self._narrative.is_ready()
        except (OSError, RuntimeError, ValueError):
            return False


__all__ = ("AdoptionService",)


def _species_result(species_id: str) -> AdoptionSpecies:
    definition = get_species_definition(species_id)
    return AdoptionSpecies(
        species_id=definition.species_id,
        canon_id=definition.canon_id,
        display_name=definition.display_name,
        display_name_zh=definition.display_name_zh,
        earth_shape_label=definition.earth_shape_label,
        scene_id=definition.scene_id,
        sort_order=definition.sort_order,
    )
