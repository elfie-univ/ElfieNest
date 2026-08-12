"""Focused tests for the Brain-owned Selfhood/Profile boundary."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from elfie.brain.context_types import BigFiveTraits, ProfileAnchorSnapshot
from elfie.brain.selfhood import SelfhoodSystem
from elfie.brain.state_lifecycle import StateCommitStatus, StateRestoreError
from elfie.message_types import EventId

NOW = datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc)


def test_personality_seed_becomes_a_brain_snapshot_not_a_profile_reference() -> None:
    raw = {
        "metadata": {"description": "安静又好奇"},
        "big_five": {
            "openness": 0.9,
            "conscientiousness": 0.6,
            "extraversion": 0.2,
            "agreeableness": 0.8,
            "neuroticism": 0.3,
        },
        "speech_style": {"greetings": ["你好呀"], "verbal_ticks": "哒"},
    }

    system = SelfhoodSystem.from_personality_data(raw, initial_at=NOW)

    assert system.snapshot().big_five.openness == 0.9
    assert system.snapshot().self_description == "安静又好奇"
    assert system.snapshot().speech_style.verbal_tick == "哒"
    raw["big_five"]["openness"] = 0.1
    assert system.snapshot().big_five.openness == 0.9


def test_ordinary_turn_has_no_implicit_personality_mutation() -> None:
    system = SelfhoodSystem.from_personality_data(
        {"big_five": {"openness": 0.8}}, initial_at=NOW
    )
    before = system.snapshot()

    assert system.snapshot() == before
    assert (
        system.validate(
            system.propose_update(
                candidate_id=EventId("selfhood-candidate"),
                created_at=NOW,
                big_five=BigFiveTraits(openness=0.95),
                source_event_ids=(EventId("explicit-source"),),
            )
        ).status
        is StateCommitStatus.ACCEPTED
    )
    assert system.snapshot() == before


def test_selfhood_update_is_candidate_validated_and_stale_candidates_are_rejected() -> (
    None
):
    system = SelfhoodSystem.from_personality_data(
        {"big_five": {"openness": 0.8}}, initial_at=NOW
    )
    candidate = system.propose_update(
        candidate_id=EventId("selfhood-candidate"),
        created_at=NOW,
        big_five=BigFiveTraits(openness=0.95),
        source_event_ids=(EventId("explicit-source"),),
    )

    committed = system.commit(candidate)
    assert committed.status is StateCommitStatus.COMMITTED
    assert system.snapshot().revision == 1
    assert system.snapshot().big_five.openness == 0.95
    assert system.commit(candidate).status is StateCommitStatus.DUPLICATE

    wrong_owner = candidate.__class__(
        candidate_id=EventId("wrong-owner"),
        owner="emotion",
        base_revision=1,
        source_event_ids=(),
        causation_id=None,
        created_at=NOW,
        value=candidate.value.model_copy(update={"revision": 2}),
    )
    assert system.commit(wrong_owner).reason == "candidate_owner_mismatch"

    stale = candidate.__class__(
        candidate_id=EventId("stale-selfhood"),
        owner="selfhood",
        base_revision=0,
        source_event_ids=(),
        causation_id=None,
        created_at=NOW,
        value=candidate.value,
    )
    assert system.commit(stale).status is StateCommitStatus.STALE


def test_selfhood_restore_rejects_other_profile_and_older_checkpoint() -> None:
    system = SelfhoodSystem.from_personality_data(
        {"big_five": {"openness": 0.8}}, initial_at=NOW, profile_revision=3
    )
    checkpoint = system.checkpoint()
    other = SelfhoodSystem.from_personality_data(
        {"big_five": {"openness": 0.2}}, initial_at=NOW, profile_revision=4
    )
    with pytest.raises(ValueError, match="another Profile"):
        other.restore(checkpoint)

    candidate = system.propose_update(
        candidate_id=EventId("selfhood-next"),
        created_at=NOW,
        big_five=BigFiveTraits(openness=0.7),
    )
    system.commit(candidate)
    with pytest.raises(StateRestoreError):
        system.restore(checkpoint)


def test_profile_anchor_is_stable_and_cannot_be_partial() -> None:
    anchor = ProfileAnchorSnapshot(
        revision=1,
        captured_at=NOW,
        elfie_id="elfie-1",
        display_name="小狐",
        species_id="fox",
        appearance_seed=7,
        appearance_genome_version=1,
        primary_morphology="biped",
    )
    assert anchor.display_name == "小狐"
    with pytest.raises(ValidationError, match="identity anchors"):
        ProfileAnchorSnapshot(
            revision=1,
            captured_at=NOW,
            elfie_id="elfie-1",
        )
