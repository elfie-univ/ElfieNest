from __future__ import annotations

import pytest

from app.features.accounts import AccountPrincipal
from app.features.adoption import (
    AcceptAdoptionCommand,
    AdoptionCandidateSetExpired,
    AdoptionInvalid,
    AdoptionNestCapacityRecord,
    AdoptionPolicyRecord,
    AdoptionQuotaRecord,
    AdoptionService,
    CandidateAppearance,
    CreateCandidateSetCommand,
    GetAdoptionOptionsQuery,
    ReplyToCandidatesCommand,
    StaticSpeciesRuntimeReadiness,
)


class Policy:
    def load_policy(self) -> AdoptionPolicyRecord:
        return AdoptionPolicyRecord(
            default_elfie_limit=3,
            enabled_personality_styles=("好奇探索",),
        )


class Persistence:
    def __init__(self) -> None:
        self.used = 1
        self.limit = 2
        self.nest_used = 1
        self.nest_limit = 4

    def get_quota(self, owner_user_id: int, default_limit: int) -> AdoptionQuotaRecord:
        assert owner_user_id == 7
        assert default_limit == 3
        return AdoptionQuotaRecord(used=self.used, effective_limit=self.limit)

    def get_nest_capacity(self) -> AdoptionNestCapacityRecord:
        return AdoptionNestCapacityRecord(used=self.nest_used, maximum=self.nest_limit)


def principal() -> AccountPrincipal:
    return AccountPrincipal(
        user_id=7,
        account_id="alice",
        role="user",
        default_landing_page="chat",
    )


def candidate_command(**overrides: object) -> CreateCandidateSetCommand:
    values: dict[str, object] = {
        "species_id": "fox",
        "life_stage": "young_adult",
        "gender": "any",
        "appearance": CandidateAppearance(
            stature="tall",
            build="round",
            face="soft",
            signature="warm",
            priority="face",
        ),
        "answers": ("quiet", "research", "plan", "discuss", "steady"),
        "batch_number": 1,
    }
    values.update(overrides)
    return CreateCandidateSetCommand(**values)  # type: ignore[arg-type]


def test_options_expose_capacity_without_a_model_dependency() -> None:
    service = AdoptionService(Policy(), Persistence())

    options = service.get_options(principal(), GetAdoptionOptionsQuery())

    assert options.quota.used == 1
    assert options.quota.maximum == 2
    assert options.quota.remaining == 1
    assert options.nest_capacity.remaining == 3
    assert tuple(species.species_id for species in options.species) == ("fox", "dog")
    assert options.availability == "available"


def test_candidate_creation_rejects_a_species_without_a_runtime_package() -> None:
    service = AdoptionService(Policy(), Persistence())

    with pytest.raises(AdoptionInvalid, match="cat"):
        service.create_candidate_set(principal(), candidate_command(species_id="cat"))


def test_candidate_set_returns_five_distinct_runtime_appearances() -> None:
    service = AdoptionService(Policy(), Persistence())

    candidate_set = service.create_candidate_set(principal(), candidate_command())

    assert len(candidate_set.candidates) == 5
    visual_keys = {
        (
            item.runtime_appearance["material_parameters"]["palette_id"],
            item.runtime_appearance["material_parameters"]["region_recipe_id"],
            item.runtime_appearance["material_parameters"]["marking_id"],
        )
        for item in candidate_set.candidates
    }
    assert len(visual_keys) == 5
    assert all(item.age_years >= 3 for item in candidate_set.candidates)


def test_adoption_uses_the_validated_runtime_species_intersection() -> None:
    service = AdoptionService(
        Policy(),
        Persistence(),
        species_runtime=StaticSpeciesRuntimeReadiness(("fox",)),
    )

    options = service.get_options(principal(), GetAdoptionOptionsQuery())
    assert tuple(species.species_id for species in options.species) == ("fox",)
    with pytest.raises(AdoptionInvalid, match="dog"):
        service.create_candidate_set(principal(), candidate_command(species_id="dog"))


def test_reply_is_structural_and_acceptance_can_be_committed() -> None:
    persistence = Persistence()
    service = AdoptionService(Policy(), persistence)
    candidate_set = service.create_candidate_set(principal(), candidate_command())
    selected_ids = tuple(item.candidate_id for item in candidate_set.candidates[:2])

    replies = service.reply_to_candidates(
        principal(),
        ReplyToCandidatesCommand(
            candidate_set_id=candidate_set.candidate_set_id,
            candidate_ids=selected_ids,
            invitation_message="你好，想认识你。",
        ),
    )

    assert len(replies.replies) == 2
    assert all(reply.message for reply in replies.replies)
    assert not any(hasattr(reply, "reveal") for reply in replies.replies)
    accepted = next(reply for reply in replies.replies if reply.status == "accepted")
    reservation = service.prepare_accepted(
        principal(),
        AcceptAdoptionCommand(
            candidate_set_id=candidate_set.candidate_set_id,
            candidate_id=accepted.candidate.candidate_id,
            name="星砂",
        ),
    )

    assert reservation.name == "星砂"
    assert reservation.species_id == accepted.candidate.species_id
    assert reservation.candidate.age_years == accepted.candidate.age_years
    assert reservation.owner_user_id == 7


def test_successful_reply_retry_is_idempotent() -> None:
    service = AdoptionService(Policy(), Persistence())
    candidate_set = service.create_candidate_set(principal(), candidate_command())
    command = ReplyToCandidatesCommand(
        candidate_set_id=candidate_set.candidate_set_id,
        candidate_ids=(candidate_set.candidates[0].candidate_id,),
        invitation_message="你好",
    )

    first = service.reply_to_candidates(principal(), command)
    second = service.reply_to_candidates(principal(), command)

    assert second == first


def test_candidate_session_is_owner_scoped_and_supports_three_batches() -> None:
    service = AdoptionService(Policy(), Persistence())
    first = service.create_candidate_set(principal(), candidate_command())
    for batch_number in (2, 3):
        result = service.create_candidate_set(
            principal(),
            candidate_command(
                adoption_session_id=first.adoption_session_id,
                batch_number=batch_number,
            ),
        )
        assert result.batch_number == batch_number

    other = AccountPrincipal(
        user_id=8,
        account_id="bob",
        role="user",
        default_landing_page="chat",
    )
    with pytest.raises(AdoptionCandidateSetExpired):
        service.reply_to_candidates(
            other,
            ReplyToCandidatesCommand(
                candidate_set_id=first.candidate_set_id,
                candidate_ids=(first.candidates[0].candidate_id,),
            ),
        )
