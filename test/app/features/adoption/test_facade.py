from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.features.accounts import AccountPrincipal
from app.features.adoption import (
    AdoptionCandidateSetExpired,
    AdoptionGenerationTimeout,
    AdoptionInvalid,
    AdoptionNestCapacityRecord,
    AdoptionPolicyRecord,
    AdoptionPortCapacityReached,
    AdoptionQuotaRecord,
    AdoptionReservationRecord,
    AdoptionService,
    CandidateAppearance,
    CandidateReveal,
    CreateCandidateSetCommand,
    GetAdoptionOptionsQuery,
    ReplyToCandidatesCommand,
    ReserveAcceptedAdoptionCommand,
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
        self.reservations: list[AdoptionReservationRecord] = []
        self.released: list[str] = []

    def get_quota(self, owner_user_id: int, default_limit: int) -> AdoptionQuotaRecord:
        assert owner_user_id == 7
        assert default_limit == 3
        return AdoptionQuotaRecord(used=self.used, effective_limit=self.limit)

    def get_nest_capacity(self) -> AdoptionNestCapacityRecord:
        return AdoptionNestCapacityRecord(used=self.nest_used, maximum=self.nest_limit)

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


class Narrative:
    def __init__(self, *, ready: bool = True) -> None:
        self.ready = ready
        self.reveal_calls = 0

    def is_ready(self) -> bool:
        return self.ready

    def reveal(self, candidate, invitation_message: str) -> CandidateReveal:
        self.reveal_calls += 1
        assert candidate.species_id == "fox"
        assert invitation_message in ("", "你好，想认识你。")
        return CandidateReveal("Vulpes", "小狐", "我喜欢在安静的地方慢慢观察世界。")

    def reveal_many(self, candidates, invitation_message: str):
        return {
            candidate.candidate_id: self.reveal(candidate, invitation_message)
            for candidate in candidates
        }


class ConcurrentNarrative(Narrative):
    def __init__(self) -> None:
        super().__init__()
        self.barrier = threading.Barrier(3)

    def reveal(self, candidate, invitation_message: str) -> CandidateReveal:
        self.barrier.wait(timeout=2)
        return super().reveal(candidate, invitation_message)

    def reveal_many(self, candidates, invitation_message: str):
        with ThreadPoolExecutor(max_workers=len(candidates)) as executor:
            futures = {
                candidate.candidate_id: executor.submit(
                    self.reveal, candidate, invitation_message
                )
                for candidate in candidates
            }
            return {
                candidate_id: future.result()
                for candidate_id, future in futures.items()
            }


def principal() -> AccountPrincipal:
    return AccountPrincipal(
        user_id=7,
        account_id="alice",
        role="user",
        default_landing_page="chat",
    )


def candidate_command() -> CreateCandidateSetCommand:
    return CreateCandidateSetCommand(
        species_id="fox",
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
        batch_number=1,
    )


def test_options_expose_both_member_and_nest_capacity() -> None:
    service = AdoptionService(Policy(), Persistence())

    options = service.get_options(principal(), GetAdoptionOptionsQuery())

    assert options.quota.used == 1
    assert options.quota.maximum == 2
    assert options.quota.remaining == 1
    assert options.quota.can_adopt is True
    assert options.nest_capacity.used == 1
    assert options.nest_capacity.maximum == 4
    assert options.nest_capacity.remaining == 3
    assert tuple(species.species_id for species in options.species) == (
        "fox",
        "dog",
    )
    assert options.availability == "model_unavailable"


def test_options_are_available_only_when_capacity_and_remote_model_are_ready() -> None:
    service = AdoptionService(Policy(), Persistence(), narrative=Narrative())

    options = service.get_options(principal(), GetAdoptionOptionsQuery())

    assert options.availability == "available"


def test_options_prioritize_nest_full_over_member_quota_and_model_state() -> None:
    persistence = Persistence()
    persistence.used = persistence.limit
    persistence.nest_used = persistence.nest_limit
    service = AdoptionService(Policy(), persistence, narrative=Narrative(ready=False))

    options = service.get_options(principal(), GetAdoptionOptionsQuery())

    assert options.availability == "nest_full"


def test_candidate_creation_rejects_a_species_without_a_complete_runtime_package() -> (
    None
):
    service = AdoptionService(Policy(), Persistence())
    command = CreateCandidateSetCommand(
        **{**candidate_command().__dict__, "species_id": "cat"}
    )

    with pytest.raises(AdoptionInvalid, match="cat"):
        service.create_candidate_set(principal(), command)


def test_candidate_set_returns_five_distinct_v9_runtime_appearances() -> None:
    service = AdoptionService(Policy(), Persistence())

    candidate_set = service.create_candidate_set(principal(), candidate_command())

    assert len(candidate_set.candidates) == 5
    visual_keys = set()
    for candidate in candidate_set.candidates:
        resolved = candidate.runtime_appearance
        assert resolved["species_id"] == "fox"
        materials = resolved["material_parameters"]
        visual_keys.add(
            (
                materials["palette_id"],
                materials["region_recipe_id"],
                materials["marking_id"],
                materials["marking_placement"],
                tuple(
                    (
                        materials[f"region_{index}_id"],
                        materials[f"region_{index}_color_id"],
                    )
                    for index in range(3)
                    if materials[f"region_{index}_id"] != "none"
                ),
            )
        )
        active_regions = [
            materials[f"region_{index}_id"]
            for index in range(3)
            if materials[f"region_{index}_id"] != "none"
        ]
        assert len(active_regions) <= 2

    assert len(visual_keys) == 5


def test_adoption_uses_the_validated_runtime_species_intersection() -> None:
    service = AdoptionService(
        Policy(),
        Persistence(),
        narrative=Narrative(),
        species_runtime=StaticSpeciesRuntimeReadiness(("fox",)),
    )

    options = service.get_options(principal(), GetAdoptionOptionsQuery())
    assert tuple(species.species_id for species in options.species) == ("fox",)

    with pytest.raises(AdoptionInvalid, match="dog"):
        service.create_candidate_set(
            principal(),
            CreateCandidateSetCommand(
                **{**candidate_command().__dict__, "species_id": "dog"}
            ),
        )


def test_candidate_reply_and_reservation_preserve_accepted_snapshot() -> None:
    persistence = Persistence()
    service = AdoptionService(Policy(), persistence, narrative=Narrative())
    candidate_set = service.create_candidate_set(principal(), candidate_command())
    selected = candidate_set.candidates[:2]
    replies = service.reply_to_candidates(
        principal(),
        ReplyToCandidatesCommand(
            candidate_set_id=candidate_set.candidate_set_id,
            candidate_ids=tuple(candidate.candidate_id for candidate in selected),
        ),
    )
    accepted_reply = next(
        reply for reply in replies.replies if reply.status == "accepted"
    )

    reservation = service.prepare_accepted(
        principal(),
        ReserveAcceptedAdoptionCommand(
            candidate_set_id=candidate_set.candidate_set_id,
            candidate_id=accepted_reply.candidate.candidate_id,
            name="星砂",
        ),
    )

    assert reservation.name == "星砂"
    assert reservation.species_id == accepted_reply.candidate.species_id
    assert reservation.gender == accepted_reply.candidate.gender
    assert persistence.reservations == []

    service.publish_accepted(reservation)

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

    from app.features.adoption import AdoptionCandidateSetExpired

    with pytest.raises(AdoptionCandidateSetExpired):
        service.reply_to_candidates(
            other,
            ReplyToCandidatesCommand(
                candidate_set_id=candidate_set.candidate_set_id,
                candidate_ids=(candidate_set.candidates[0].candidate_id,),
            ),
        )


def test_candidate_session_allows_three_batches_and_rejects_the_fourth() -> None:
    service = AdoptionService(Policy(), Persistence())
    first = service.create_candidate_set(principal(), candidate_command())
    for expected_batch in (2, 3):
        next_batch = service.create_candidate_set(
            principal(),
            CreateCandidateSetCommand(
                **{
                    **candidate_command().__dict__,
                    "adoption_session_id": first.adoption_session_id,
                    "batch_number": expected_batch,
                }
            ),
        )
        assert next_batch.batch_number == expected_batch

    with pytest.raises(AdoptionInvalid, match="3 批"):
        service.create_candidate_set(
            principal(),
            CreateCandidateSetCommand(
                **{
                    **candidate_command().__dict__,
                    "adoption_session_id": first.adoption_session_id,
                    "batch_number": 4,
                }
            ),
        )


def test_candidate_batch_expires_after_registry_restart() -> None:
    first_service = AdoptionService(Policy(), Persistence())
    first = first_service.create_candidate_set(principal(), candidate_command())
    second_command = CreateCandidateSetCommand(
        **{
            **candidate_command().__dict__,
            "adoption_session_id": first.adoption_session_id,
            "batch_number": 2,
        }
    )
    original_second = first_service.create_candidate_set(principal(), second_command)

    restarted_service = AdoptionService(Policy(), Persistence())
    with pytest.raises(AdoptionCandidateSetExpired):
        restarted_service.create_candidate_set(principal(), second_command)

    assert original_second.adoption_session_id == first.adoption_session_id


def test_candidate_session_uses_an_absolute_five_hour_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.features.adoption import _candidate_registry

    clock = [100.0]
    monkeypatch.setattr(_candidate_registry.time, "monotonic", lambda: clock[0])
    service = AdoptionService(Policy(), Persistence(), narrative=Narrative())
    first = service.create_candidate_set(principal(), candidate_command())

    clock[0] = 100.0 + (5 * 60 * 60) - 1
    repeated = service.create_candidate_set(principal(), candidate_command())
    assert repeated == first

    clock[0] += 2
    with pytest.raises(AdoptionCandidateSetExpired):
        service.reply_to_candidates(
            principal(),
            ReplyToCandidatesCommand(
                candidate_set_id=first.candidate_set_id,
                candidate_ids=(first.candidates[0].candidate_id,),
            ),
        )


def test_slow_reveal_cannot_publish_after_the_absolute_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.features.adoption import _candidate_registry

    clock = [100.0]
    monkeypatch.setattr(_candidate_registry.time, "monotonic", lambda: clock[0])
    narrative = Narrative()

    def reveal_many(candidates, invitation_message: str):
        clock[0] = 100.0 + (5 * 60 * 60) + 1
        return {
            candidate.candidate_id: narrative.reveal(candidate, invitation_message)
            for candidate in candidates
        }

    monkeypatch.setattr(narrative, "reveal_many", reveal_many)
    service = AdoptionService(Policy(), Persistence(), narrative=narrative)
    candidate_set = service.create_candidate_set(principal(), candidate_command())

    with pytest.raises(AdoptionCandidateSetExpired):
        service.reply_to_candidates(
            principal(),
            ReplyToCandidatesCommand(
                candidate_set_id=candidate_set.candidate_set_id,
                candidate_ids=(candidate_set.candidates[0].candidate_id,),
            ),
        )


def test_invitation_timeout_rolls_back_to_a_retryable_candidate_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    narrative = Narrative()

    def timeout(*_args, **_kwargs):
        raise TimeoutError("model call exceeded deadline")

    monkeypatch.setattr(narrative, "reveal_many", timeout)
    service = AdoptionService(Policy(), Persistence(), narrative=narrative)
    candidate_set = service.create_candidate_set(principal(), candidate_command())
    command = ReplyToCandidatesCommand(
        candidate_set_id=candidate_set.candidate_set_id,
        candidate_ids=(candidate_set.candidates[0].candidate_id,),
    )

    with pytest.raises(AdoptionGenerationTimeout, match="超时"):
        service.reply_to_candidates(principal(), command)

    monkeypatch.setattr(
        narrative, "reveal_many", Narrative.reveal_many.__get__(narrative)
    )
    retry = service.reply_to_candidates(principal(), command)
    assert retry.replies[0].reveal is not None


def test_reply_uses_strong_model_reveal_before_reservation() -> None:
    persistence = Persistence()
    service = AdoptionService(Policy(), persistence, narrative=Narrative())
    candidate_set = service.create_candidate_set(principal(), candidate_command())
    candidate_id = candidate_set.candidates[0].candidate_id

    replies = service.reply_to_candidates(
        principal(),
        ReplyToCandidatesCommand(
            candidate_set_id=candidate_set.candidate_set_id,
            candidate_ids=(candidate_id,),
            invitation_message="你好，想认识你。",
        ),
    )

    assert replies.replies[0].reveal is not None
    reservation = service.prepare_accepted(
        principal(),
        ReserveAcceptedAdoptionCommand(
            candidate_set_id=candidate_set.candidate_set_id,
            candidate_id=candidate_id,
            name="小狐",
        ),
    )
    assert reservation.original_name == "Vulpes"
    assert reservation.personal_story == "我喜欢在安静的地方慢慢观察世界。"
    assert reservation.age_months == candidate_set.candidates[0].age_months
    assert reservation.life_stage == candidate_set.candidates[0].life_stage


def test_each_selected_candidate_has_an_independent_acceptance_draw(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.features.adoption import _candidate_registry

    monkeypatch.setattr(_candidate_registry, "_acceptance_score", lambda *_: 0.1)
    service = AdoptionService(Policy(), Persistence(), narrative=Narrative())
    candidate_set = service.create_candidate_set(principal(), candidate_command())

    replies = service.reply_to_candidates(
        principal(),
        ReplyToCandidatesCommand(
            candidate_set_id=candidate_set.candidate_set_id,
            candidate_ids=tuple(
                candidate.candidate_id for candidate in candidate_set.candidates[:3]
            ),
        ),
    )

    assert [reply.status for reply in replies.replies] == [
        "accepted",
        "accepted",
        "accepted",
    ]


def test_selected_candidate_reveals_run_concurrently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.features.adoption import _candidate_registry

    monkeypatch.setattr(_candidate_registry, "_acceptance_score", lambda *_: 0.1)
    narrative = ConcurrentNarrative()
    service = AdoptionService(Policy(), Persistence(), narrative=narrative)
    candidate_set = service.create_candidate_set(principal(), candidate_command())

    replies = service.reply_to_candidates(
        principal(),
        ReplyToCandidatesCommand(
            candidate_set_id=candidate_set.candidate_set_id,
            candidate_ids=tuple(
                candidate.candidate_id for candidate in candidate_set.candidates[:3]
            ),
            invitation_message="你好，想认识你。",
        ),
    )

    assert [reply.status for reply in replies.replies] == [
        "accepted",
        "accepted",
        "accepted",
    ]
    assert narrative.reveal_calls == 3


def test_reply_guarantees_at_least_one_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.features.adoption import _candidate_registry

    monkeypatch.setattr(_candidate_registry, "_acceptance_score", lambda *_: 0.99)
    service = AdoptionService(Policy(), Persistence(), narrative=Narrative())
    candidate_set = service.create_candidate_set(principal(), candidate_command())

    replies = service.reply_to_candidates(
        principal(),
        ReplyToCandidatesCommand(
            candidate_set_id=candidate_set.candidate_set_id,
            candidate_ids=tuple(
                candidate.candidate_id for candidate in candidate_set.candidates[:3]
            ),
        ),
    )

    assert sum(reply.status == "accepted" for reply in replies.replies) == 1


def test_successful_reply_retry_is_idempotent_and_does_not_call_model_twice() -> None:
    narrative = Narrative()
    service = AdoptionService(Policy(), Persistence(), narrative=narrative)
    candidate_set = service.create_candidate_set(principal(), candidate_command())
    command = ReplyToCandidatesCommand(
        candidate_set_id=candidate_set.candidate_set_id,
        candidate_ids=(candidate_set.candidates[0].candidate_id,),
        invitation_message="你好，想认识你。",
    )

    first = service.reply_to_candidates(principal(), command)
    second = service.reply_to_candidates(principal(), command)

    assert second == first
    assert narrative.reveal_calls == 1
