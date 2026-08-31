"""Focused tests for the two-layer Brain-owned Selfhood contract."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from elfie.brain.selfhood.contracts import (
    AdaptiveSelf,
    BigFiveTraits,
    IdentityCore,
    ProfileAnchorSnapshot,
    SelfhoodState,
)
from elfie.brain.selfhood.system import SelfhoodGrowthDisabledError, SelfhoodSystem

NOW = datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc)


def _seed(*, display_name: str = "小狐", openness: float = 0.8) -> dict:
    return {
        "state_schema_version": 1,
        "revision": 1,
        "identity_core": {
            "elfie_id": "elfie-1",
            "display_name": display_name,
            "species_id": "fox",
            "species_name": "Saevi",
            "home_world_id": "elfaria",
            "home_world_name": "Elfaria",
            "home_region_id": "north",
            "home_region_name": "北境",
            "earth_arrival_statement": "我被领养来到地球。",
            "resident_role": "居民",
        },
        "adaptive_self": {
            "big_five": {
                "openness": openness,
                "conscientiousness": 0.6,
                "extraversion": 0.2,
                "agreeableness": 0.8,
                "neuroticism": 0.3,
            },
            "interaction_tendency_ids": ["先观察边缘、声音和可离开的路径"],
            "value_ids": ["尊重自愿选择，不把猜测说成亲历。"],
            "speech_marker_ids": ["哒"],
        },
    }


def test_seed_is_two_layers_and_is_not_affected_by_source_mutation() -> None:
    raw = _seed()
    system = SelfhoodSystem.from_seed(raw, initial_at=NOW)

    assert system.snapshot().identity_core.display_name == "小狐"
    assert system.snapshot().adaptive_self.big_five.openness == 0.8
    assert system.snapshot().revision == 1
    raw["adaptive_self"]["big_five"]["openness"] = 0.1
    assert system.snapshot().adaptive_self.big_five.openness == 0.8


def test_prompt_projection_is_natural_language_and_has_no_raw_trait_numbers() -> None:
    projection = SelfhoodSystem.from_seed(_seed(), initial_at=NOW).prompt_projection()

    assert "小狐" in projection.identity_core_text
    assert "开放性" in projection.adaptive_self_text
    assert "0.8" not in projection.adaptive_self_text
    assert "先观察边缘、声音和可离开的路径" not in projection.adaptive_self_text
    assert "先观察环境边缘" in projection.adaptive_self_text


def test_incomplete_or_legacy_seed_fails_closed() -> None:
    with pytest.raises(ValueError, match="invalid Selfhood state"):
        SelfhoodSystem.from_seed({"big_five": {"openness": 0.8}}, initial_at=NOW)

    incomplete = SelfhoodSystem(initial_at=NOW)
    with pytest.raises(ValueError, match="identity_core is incomplete"):
        incomplete.prompt_projection()


def test_growth_is_disabled_until_memory_proposal_contract_exists() -> None:
    system = SelfhoodSystem.from_seed(_seed(), initial_at=NOW)
    before = system.snapshot()

    with pytest.raises(SelfhoodGrowthDisabledError):
        system.propose_update(object())

    assert system.snapshot() == before


def test_identity_core_is_immutable_for_dedicated_checkpoint_restore() -> None:
    system = SelfhoodSystem.from_seed(_seed(), initial_at=NOW)
    checkpoint = system.checkpoint()
    tampered = checkpoint.value.model_copy(
        update={
            "identity_core": checkpoint.value.identity_core.model_copy(
                update={"display_name": "另一只精灵"}
            )
        }
    )
    tampered_checkpoint = checkpoint.__class__(
        revision=checkpoint.revision,
        committed_at=checkpoint.committed_at,
        source_event_ids=checkpoint.source_event_ids,
        causation_id=checkpoint.causation_id,
        value=tampered,
        committed_candidate_ids=checkpoint.committed_candidate_ids,
    )

    with pytest.raises(ValueError, match="identity_core is immutable"):
        system.restore(tampered_checkpoint)


def test_profile_anchor_remains_external_and_requires_complete_identity() -> None:
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
        ProfileAnchorSnapshot(revision=1, captured_at=NOW, elfie_id="elfie-1")


def test_selfhood_state_has_exactly_identity_and_adaptive_layers() -> None:
    SelfhoodState(
        revision=1,
        committed_at=NOW,
        identity_core=IdentityCore(**_seed()["identity_core"]),
        adaptive_self=AdaptiveSelf(
            big_five=BigFiveTraits(**_seed()["adaptive_self"]["big_five"])
        ),
    )
    assert set(SelfhoodState.model_fields) == {
        "state_schema_version",
        "revision",
        "committed_at",
        "identity_core",
        "adaptive_self",
    }
