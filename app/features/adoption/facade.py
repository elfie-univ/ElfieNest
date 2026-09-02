"""Authorized Adoption use-cases over one policy and ownership fact path."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from app.features.accounts import AccountPrincipal
from elfie.profile import SpeciesCatalog, SpeciesDefinition, current_species_catalog

from ._candidate_registry import CandidateRegistry
from .errors import (
    AdoptionInvalid,
    AdoptionOwnerNotFound,
    AdoptionUnavailable,
)
from .models import (
    AcceptAdoptionCommand,
    AcceptedGenesisReservation,
    AdoptionAppearanceControl,
    AdoptionAvailability,
    AdoptionNestCapacity,
    AdoptionOptionsResult,
    AdoptionQuota,
    AdoptionSpecies,
    AdoptionSpeciesImage,
    AdoptionSpeciesImages,
    CandidateRepliesResult,
    CandidateSetResult,
    CreateCandidateSetCommand,
    GetAdoptionOptionsQuery,
    LifeStage,
    ReplyToCandidatesCommand,
    SpeciesImageKind,
)
from .port_models import AdoptionPolicyRecord
from .ports import (
    AdoptionPersistencePort,
    AdoptionPolicyPort,
    AdoptionPortError,
    CandidatePortraitPort,
    SpeciesPresentationPort,
    SpeciesRuntimeReadinessPort,
    StaticSpeciesRuntimeReadiness,
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
        catalog: SpeciesCatalog | None = None,
        species_presentation: SpeciesPresentationPort | None = None,
        species_runtime: SpeciesRuntimeReadinessPort | None = None,
    ) -> None:
        self._policy = policy
        self._persistence = persistence
        self._catalog = catalog or current_species_catalog()
        self._species_presentation = species_presentation
        self._species_runtime = species_runtime or StaticSpeciesRuntimeReadiness(
            tuple(
                definition.godot_package_id
                for definition in self._catalog.definitions
                if definition.adoptable
            )
        )
        self._candidates = candidates or CandidateRegistry(
            portraits=portraits,
            catalog=self._catalog,
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
            else "species_unavailable"
            if not self._available_definitions()
            else "available"
        )
        return AdoptionOptionsResult(
            personality_styles=policy.enabled_personality_styles,
            species=tuple(
                _species_result(definition, self._species_presentation)
                for definition in self._available_definitions()
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
            self._require_adoptable_species(command.species_id)
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
        command: AcceptAdoptionCommand,
    ) -> AcceptedGenesisReservation:
        name = command.name.strip()
        if not name or len(name) > 20:
            raise AdoptionInvalid("名字长度必须在 1-20 字之间")
        candidate = self._candidates.accepted(
            owner_user_id=principal.user_id,
            candidate_set_id=command.candidate_set_id,
            candidate_id=command.candidate_id,
        )
        try:
            self._require_adoptable_species(candidate.public.species_id)
        except ValueError as error:
            raise AdoptionInvalid(
                f"不支持的 species_id={candidate.public.species_id!r}"
            ) from error
        full_body_image_url = (
            command.full_body_image_url or candidate.public.full_body_image_url
        )
        headshot_image_url = (
            command.headshot_image_url or candidate.public.headshot_image_url
        )
        acceptance_digest = _acceptance_digest(
            principal.user_id,
            command.candidate_set_id,
            command.candidate_id,
            full_body_image_url,
            headshot_image_url,
        )
        # The numeric identity is deterministic for one accepted decision.  A
        # collision is rejected by the durable Admission store instead of
        # silently replacing another resident.
        elfie_id = f"{(int(acceptance_digest[:16], 16) % 99_999_999) + 1:08d}"
        reservation = AcceptedGenesisReservation(
            reservation_id=f"admission:{acceptance_digest}",
            idempotency_key=f"adoption:{acceptance_digest}",
            elfie_id=elfie_id,
            owner_user_id=principal.user_id,
            name=name,
            candidate=candidate.genesis,
            adoption_anchor_at=datetime.now(timezone.utc).isoformat(),
            full_body_image_url=full_body_image_url,
            headshot_image_url=headshot_image_url,
        )

        return reservation

    def get_default_elfie_limit(self) -> int:
        """Return the current quota policy for the Admission transaction."""

        return self._load_policy().default_elfie_limit

    def get_species_image(
        self,
        principal: AccountPrincipal,
        species_id: str,
        image_kind: SpeciesImageKind,
    ) -> AdoptionSpeciesImage:
        """Return one catalog-owned PNG after the normal member check."""

        _ = principal
        try:
            self._require_adoptable_species(species_id)
            if self._species_presentation is None:
                raise AdoptionUnavailable("物种图片服务未装配")
            return self._species_presentation.read(species_id, image_kind)
        except ValueError as error:
            raise AdoptionInvalid(f"不支持的 species_id={species_id!r}") from error
        except AdoptionUnavailable:
            raise
        except (OSError, RuntimeError) as error:
            raise AdoptionUnavailable("物种图片暂不可用") from error

    def _load_policy(self) -> AdoptionPolicyRecord:
        try:
            return self._policy.load_policy()
        except AdoptionPortError as error:
            raise AdoptionUnavailable("领养规则暂不可用") from error

    def _available_definitions(self) -> tuple[SpeciesDefinition, ...]:
        return tuple(
            definition
            for definition in self._catalog.definitions
            if definition.adoptable
            and self._species_runtime.is_available(definition.godot_package_id)
        )

    def _require_adoptable_species(self, species_id: str) -> SpeciesDefinition:
        definition = self._catalog.definition(species_id, adoptable_only=True)
        if not self._species_runtime.is_available(definition.godot_package_id):
            raise ValueError(f"物种 {species_id!r} 的 Godot 资源包不可用")
        return definition


__all__ = ("AdoptionService",)


def _species_result(
    definition: SpeciesDefinition,
    presentation: SpeciesPresentationPort | None,
) -> AdoptionSpecies:
    if presentation is None:
        images = _default_species_images(definition.species_id)
    else:
        try:
            images = presentation.urls(definition.species_id)
        except (OSError, RuntimeError, ValueError) as error:
            raise AdoptionUnavailable("物种图片暂不可用") from error
    return AdoptionSpecies(
        species_id=definition.species_id,
        species_package_id=definition.species_package_id,
        display_name=definition.display_name,
        display_name_zh=definition.display_name_zh,
        earth_shape_label=definition.earth_shape_label,
        scene_id=definition.scene_id,
        sort_order=definition.sort_order,
        presentation_images=images,
        appearance_controls=tuple(
            AdoptionAppearanceControl(
                control_id=control_id,
                options=definition.appearance.control_options[control_id],
            )
            for control_id in definition.appearance.supported_controls
        ),
    )


def _default_species_images(species_id: str) -> AdoptionSpeciesImages:
    prefix = f"/api/v1/me/adoption/species/{species_id}/images"
    return AdoptionSpeciesImages(
        headshot_url=f"{prefix}/headshot",
        full_body_url=f"{prefix}/full-body",
    )


def _acceptance_digest(
    owner_user_id: int,
    candidate_set_id: str,
    candidate_id: str,
    full_body_image_url: str,
    headshot_image_url: str,
) -> str:
    """Build one stable accepted-candidate identity.

    The display name is deliberately excluded: changing it on a retry must
    address the same accepted candidate and therefore the same durable
    Admission record.  The selected portrait references remain part of the
    decision because they affect the immutable external appearance projection.
    """

    payload = {
        "candidate_id": candidate_id,
        "candidate_set_id": candidate_set_id,
        "full_body_image_sha256": hashlib.sha256(
            full_body_image_url.encode("utf-8")
        ).hexdigest(),
        "headshot_image_sha256": hashlib.sha256(
            headshot_image_url.encode("utf-8")
        ).hexdigest(),
        "owner_user_id": owner_user_id,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
