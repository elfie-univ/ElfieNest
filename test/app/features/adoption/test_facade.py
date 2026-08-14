from __future__ import annotations

from app.features.accounts import AccountPrincipal
from app.features.adoption import (
    AdoptionPolicyRecord,
    AdoptionPortCapacityReached,
    AdoptionQuotaRecord,
    AdoptionReservationRecord,
    AdoptionService,
    CandidateAppearance,
    CreateCandidateSetCommand,
    GetAdoptionOptionsQuery,
    ReplyToCandidatesCommand,
    ReserveAcceptedAdoptionCommand,
    SpeciesId,
)


class Policy:
    def load_policy(self) -> AdoptionPolicyRecord:
        return AdoptionPolicyRecord(
            default_elfie_limit=3,
            allowed_species_ids=("dog", "fox", "cat"),
            enabled_personality_styles=("好奇探索",),
        )


class Persistence:
    def __init__(self) -> None:
        self.used = 1
        self.limit = 2
        self.reservations: list[AdoptionReservationRecord] = []
        self.released: list[str] = []

    def get_quota(self, owner_user_id: int, default_limit: int) -> AdoptionQuotaRecord:
        assert owner_user_id == 7
        assert default_limit == 3
        return AdoptionQuotaRecord(used=self.used, effective_limit=self.limit)

    def reserve(
        self, reservation: AdoptionReservationRecord, default_limit: int
    ) -> None:
        assert default_limit == 3
        if self.used >= self.limit:
            raise AdoptionPortCapacityReached(self.limit)
        self.reservations.append(reservation)
        self.used += 1

    def release(self, elfie_id: str) -> None:
        self.released.append(elfie_id)


def principal() -> AccountPrincipal:
    return AccountPrincipal(
        user_id=7,
        account_id="alice",
        role="user",
        default_landing_page="chat",
    )


def candidate_command(species_id: SpeciesId = "fox") -> CreateCandidateSetCommand:
    return CreateCandidateSetCommand(
        species_id=species_id,
        life_stage="young_adult",
        gender="any",
        appearance=CandidateAppearance(
            stature="tall",
            build="round",
            face="soft",
            signature="warm",
            priority="face",
        ),
        answers=("quiet", "research", "plan", "discuss", "steady"),
    )


def test_options_use_one_effective_quota_read() -> None:
    service = AdoptionService(Policy(), Persistence())

    options = service.get_options(principal(), GetAdoptionOptionsQuery())

    assert options.quota.used == 1
    assert options.quota.maximum == 2
    assert options.quota.remaining == 1
    assert options.quota.can_adopt is True


def test_candidate_reply_and_reservation_preserve_accepted_snapshot() -> None:
    persistence = Persistence()
    service = AdoptionService(Policy(), persistence)
    candidate_set = service.create_candidate_set(principal(), candidate_command())
    assert "Saevi" in candidate_set.candidates[0].introduction
    assert "fox-like" in candidate_set.candidates[0].introduction
    selected = candidate_set.candidates[:2]
    replies = service.reply_to_candidates(
        principal(),
        ReplyToCandidatesCommand(
            candidate_set_id=candidate_set.candidate_set_id,
            candidate_ids=tuple(candidate.candidate_id for candidate in selected),
        ),
    )

    reservation = service.reserve_accepted(
        principal(),
        ReserveAcceptedAdoptionCommand(
            candidate_set_id=candidate_set.candidate_set_id,
            candidate_id=replies.replies[0].candidate.candidate_id,
            name="星砂",
        ),
    )

    assert reservation.name == "星砂"
    assert reservation.species_id == selected[0].species_id
    assert reservation.gender == selected[0].gender
    assert persistence.reservations[0].owner_user_id == 7


def test_candidate_sets_remain_isolated_by_authenticated_member() -> None:
    service = AdoptionService(Policy(), Persistence())
    candidate_set = service.create_candidate_set(principal(), candidate_command())
    other = AccountPrincipal(
        user_id=8,
        account_id="bob",
        role="user",
        default_landing_page="chat",
    )

    import pytest

    from app.features.adoption import AdoptionCandidateSetExpired

    with pytest.raises(AdoptionCandidateSetExpired):
        service.reply_to_candidates(
            other,
            ReplyToCandidatesCommand(
                candidate_set_id=candidate_set.candidate_set_id,
                candidate_ids=(candidate_set.candidates[0].candidate_id,),
            ),
        )


def test_cat_candidate_uses_myelle_canon_and_stable_species_id() -> None:
    persistence = Persistence()
    service = AdoptionService(Policy(), persistence)

    candidate_set = service.create_candidate_set(principal(), candidate_command("cat"))

    assert candidate_set.candidates[0].species_id == "cat"
    assert "Myelle" in candidate_set.candidates[0].introduction
    assert "cat-like" in candidate_set.candidates[0].introduction
