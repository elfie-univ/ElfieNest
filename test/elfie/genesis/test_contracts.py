import pytest

from elfie.brain.selfhood.contracts import BigFiveTraits, SelfhoodSpeechStyle
from elfie.genesis import (
    BiographyEnrichmentPlan,
    GenesisBundle,
    GenesisValidationError,
    InitializationManifest,
    MemorySeed,
    PersonalitySeed,
    ProfileDraft,
    RelationshipSeed,
    SelfModelSeed,
)
from elfie.profile import (
    WORLD_CANON_VERSION,
    create_visual_profile,
    get_species_canon_for_technical_id,
)


def _bundle(memory_count: int = 2) -> GenesisBundle:
    profile = create_visual_profile(
        elfie_id="genesis-check",
        display_name="Lumi",
        species_id="fox",
        seed=23,
    )
    memory_seeds = tuple(
        MemorySeed(
            seed_id=f"m-{index}",
            content=f"A bounded event {index}",
            source="personal_memory",
        )
        for index in range(memory_count)
    )
    return GenesisBundle(
        profile_draft=ProfileDraft(profile=profile),
        personality_seed=PersonalitySeed(
            big_five=BigFiveTraits(openness=0.78),
            self_description="我来自 Elfaria 的迷雾镇。",
            speech_style=SelfhoodSpeechStyle(greetings=("你好",)),
            norms=("对不确定保持诚实。",),
        ),
        memory_seeds=memory_seeds,
        relationship_seeds=(
            RelationshipSeed(
                person_id="seli",
                display_name="Seli",
                role="mother",
                initial_trust=0.8,
            ),
        ),
        self_model_seed=SelfModelSeed(
            identity_summary="我是一只来自 Elfaria 的 Saevi。",
            known_facts=("我来自 Elfaria。",),
            unknown_facts=("我不知道 Elfaria 全部地图。",),
        ),
        biography_plan=BiographyEnrichmentPlan(
            allowed_memory_seed_ids=tuple(seed.seed_id for seed in memory_seeds),
            max_additional_memories=4,
            expires_after_events=8,
        ),
        manifest=InitializationManifest(
            manifest_id="manifest-genesis-check",
            canon_version=WORLD_CANON_VERSION,
            species_version=get_species_canon_for_technical_id("fox").canon_version,
            reference_version="sample-saevi-001.v0.1",
        ),
    )


def test_genesis_bundle_validates_bounded_creation_outputs() -> None:
    bundle = _bundle()

    assert bundle.validate() is None


def test_genesis_rejects_more_than_five_pre_arrival_events() -> None:
    bundle = _bundle(memory_count=6)

    with pytest.raises(GenesisValidationError, match="最多只能提供 5"):
        bundle.validate()
