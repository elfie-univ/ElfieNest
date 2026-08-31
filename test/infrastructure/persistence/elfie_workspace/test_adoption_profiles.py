import base64
from pathlib import Path

import pytest

from app.features.adoption import AcceptedAdoptionReservation
from app.orchestration.resident_admission import ResidentAdmissionPortError
from elfie import ElfieFactory
from elfie.factory import ElfieAssembly
from elfie.genesis import GenesisAppearanceIntent, GenesisEngine
from infrastructure.persistence.elfie_workspace.adoption_profiles import (
    FinalElfieWorkspaceAdapter,
)
from infrastructure.persistence.elfie_workspace.brain_state import (
    YamlEnergyLimitsAdapter,
    YamlSelfhoodSeedAdapter,
)
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter


@pytest.mark.parametrize(
    ("species_id", "species_name"),
    (("fox", "Saevi"), ("dog", "Tovren")),
)
def test_workspace_adapter_materializes_the_final_elfie_profile(
    tmp_path: Path,
    species_id: str,
    species_name: str,
) -> None:
    adapter = FinalElfieWorkspaceAdapter(tmp_path)
    reservation = AcceptedAdoptionReservation(
        elfie_id="00000001",
        owner_user_id=7,
        name="星砂",
        species_id=species_id,
        personality_style="好奇探索",
        height="tall",
        build="plump",
        appearance_seed=42,
        face="soft",
        signature="warm",
        gender="female",
        birth_date="2000-01-01",
    )

    workspace = adapter.materialize(reservation)
    workspace_path = Path(workspace)
    profile_store = YamlProfileStoreAdapter(Path(workspace) / "profile")
    with SQLiteMemoryStoreAdapter(
        Path(workspace) / "memory" / "knowledge.sqlite"
    ) as memory_store:
        elfie = ElfieFactory().restore(
            ElfieAssembly(
                profile=profile_store.load(),
                selfhood_seed=YamlSelfhoodSeedAdapter(workspace_path / "brain").load(),
                energy_limits=YamlEnergyLimitsAdapter(workspace_path / "brain").load(),
                memory_store=memory_store,
            )
        )

        assert elfie.profile.identity.display_name == "星砂"
        assert elfie.profile.identity.species_id == species_id
        assert elfie.profile.identity.origin.home_world_id == "elfaria"
        assert elfie.selfhood_snapshot().species_name == species_name
        assert elfie.selfhood_snapshot().sensory_biases
        assert elfie.selfhood_snapshot().species_knowledge
        assert any(
            "Elfaria" in fact for fact in elfie.selfhood_snapshot().identity_facts
        )
        assert any("尊重自愿选择" in norm for norm in elfie.selfhood_snapshot().norms)
        assert memory_store.count_episodes() == 5
        assert memory_store.get_graph_node("genesis:self:00000001") is not None
        known_elfie = memory_store.get_graph_node("genesis:self:00000001")
        assert known_elfie is not None
        assert (
            known_elfie.properties["species"],
            known_elfie.properties["is_self"],
        ) == (
            species_name,
            True,
        )
        self_model = memory_store.get_graph_node("genesis:self-model:00000001")
        assert self_model is not None
        assert self_model.properties["species_knowledge"]
        person = memory_store.get_graph_node("genesis:person:owner-7")
        assert person is not None
        assert (
            person.properties["relationship_label"],
            person.properties["is_owner"],
        ) == (
            "earth_household",
            True,
        )

    first_profile = profile_store.load()
    first_selfhood = YamlSelfhoodSeedAdapter(workspace_path / "brain").load()
    first_energy = YamlEnergyLimitsAdapter(workspace_path / "brain").load()
    adapter.materialize(reservation)
    second_profile = profile_store.load()
    assert second_profile == first_profile
    assert YamlSelfhoodSeedAdapter(workspace_path / "brain").load() == first_selfhood
    assert YamlEnergyLimitsAdapter(workspace_path / "brain").load() == first_energy

    adapter.release(reservation.elfie_id)


def test_workspace_materialization_cleans_all_files_when_genesis_commit_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = FinalElfieWorkspaceAdapter(tmp_path)
    reservation = AcceptedAdoptionReservation(
        elfie_id="00000006",
        owner_user_id=7,
        name="失败回滚精灵",
        species_id="fox",
        personality_style="好奇探索",
        height="standard",
        build="standard",
        appearance_seed=46,
        face="soft",
        signature="warm",
        gender="female",
        birth_date="2001-01-01",
    )

    def fail_commit(*_args, **_kwargs):
        raise OSError("synthetic memory publish failure")

    monkeypatch.setattr(
        "infrastructure.persistence.elfie_workspace.adoption_profiles.GenesisMemoryCommitter.commit",
        fail_commit,
    )

    with pytest.raises(ResidentAdmissionPortError):
        adapter.materialize(reservation)

    assert not (tmp_path / "elfies" / reservation.elfie_id).exists()


@pytest.mark.parametrize(
    "personality_style",
    ("活泼好动", "安静温顺", "好奇探索", "胆小害羞", "傲娇独立", "完全随机"),
)
def test_stage1_speech_templates_do_not_claim_unobserved_current_facts(
    tmp_path: Path,
    personality_style: str,
) -> None:
    adapter = FinalElfieWorkspaceAdapter(tmp_path)
    reservation = AcceptedAdoptionReservation(
        elfie_id="00000042",
        owner_user_id=7,
        name="模板精灵",
        species_id="fox",
        personality_style=personality_style,
        height="standard",
        build="standard",
        appearance_seed=42,
        face="soft",
        signature="warm",
        gender="female",
        birth_date="2000-01-01",
    )

    workspace = Path(adapter.materialize(reservation))
    seed = YamlSelfhoodSeedAdapter(workspace / "brain").load()
    speech_style = seed["speech_style"]
    rendered = "\n".join(
        [
            *(str(item) for item in speech_style["greetings"]),
            *(
                str(item)
                for values in speech_style.get("mutter_templates", {}).values()
                for item in values
            ),
        ]
    )

    assert not any(
        marker in rendered
        for marker in (
            "天气",
            "元气满满",
            "那边",
            "快来看",
            "正忙",
            "窗外",
            "盯着",
            "耳朵耷",
            "揉眼睛",
            "打哈欠",
            "咬了咬",
            "画圈圈",
        )
    )
    adapter.release(reservation.elfie_id)
    assert not Path(workspace).exists()


def test_workspace_adapter_uses_a_species_compatible_pattern_for_marked_signature(
    tmp_path: Path,
) -> None:
    adapter = FinalElfieWorkspaceAdapter(tmp_path)
    reservation = AcceptedAdoptionReservation(
        elfie_id="00000002",
        owner_user_id=7,
        name="星砂",
        species_id="dog",
        personality_style="好奇探索",
        height="standard",
        build="standard",
        appearance_seed=43,
        face="soft",
        signature="marked",
        gender="female",
        birth_date="2001-01-01",
    )

    workspace = adapter.materialize(reservation)
    profile = YamlProfileStoreAdapter(Path(workspace) / "profile").load()

    assert profile.identity.species_id == "dog"
    assert profile.appearance.coat.pattern_id in ("solid", "classic")
    assert profile.appearance.coat.marking_id != "none"
    assert profile.appearance.coat.marking_placement != "none"
    profile.validate()
    adapter.release(reservation.elfie_id)


def test_unverified_adoption_story_is_not_selfhood_identity_fact(
    tmp_path: Path,
) -> None:
    candidate = (
        GenesisEngine()
        .generate_batch(
            master_seed=99,
            batch_number=1,
            species_id="fox",
            life_stage="young_adult",
            gender="female",
            appearance=GenesisAppearanceIntent(
                stature="any",
                build="any",
                face="balanced",
                signature="any",
                priority="face",
            ),
            answers=("quiet", "explore", "plan", "discuss", "steady"),
        )
        .candidates[0]
    )
    story = "我有一段还没有经过正式记忆校验的自我介绍。"
    reservation = AcceptedAdoptionReservation(
        elfie_id="00000043",
        owner_user_id=7,
        name="故事精灵",
        species_id="fox",
        personality_style="Genesis",
        height="standard",
        build="standard",
        appearance_seed=candidate.seed,
        face="balanced",
        signature="any",
        gender="female",
        birth_date="2001-01-01",
        genesis_candidate=candidate,
        personal_story=story,
    )

    adapter = FinalElfieWorkspaceAdapter(tmp_path)
    workspace = Path(adapter.materialize(reservation))
    selfhood = YamlSelfhoodSeedAdapter(workspace / "brain").load()

    assert selfhood["self_description"] != story
    assert "Elfaria" in selfhood["self_description"]
    assert selfhood["metadata"]["personal_story"] == story
    adapter.release(reservation.elfie_id)


@pytest.mark.parametrize("species_id", ("dog", "fox"))
def test_workspace_adapter_persists_the_exact_accepted_candidate_appearance(
    tmp_path: Path,
    species_id: str,
) -> None:
    candidate = (
        GenesisEngine()
        .generate_batch(
            master_seed=77,
            batch_number=1,
            species_id=species_id,
            life_stage="young_adult",
            gender="female",
            appearance=GenesisAppearanceIntent(
                stature="any",
                build="any",
                face="balanced",
                signature="any",
                priority="face",
            ),
            answers=("quiet", "explore", "plan", "discuss", "steady"),
        )
        .candidates[0]
    )
    reservation = AcceptedAdoptionReservation(
        elfie_id="00000004" if species_id == "dog" else "00000005",
        owner_user_id=7,
        name="候选精灵",
        species_id=species_id,
        personality_style="Genesis",
        height="standard",
        build="standard",
        appearance_seed=candidate.seed,
        face="balanced",
        signature="any",
        gender="female",
        birth_date="2001-01-01",
        genesis_candidate=candidate,
    )

    adapter = FinalElfieWorkspaceAdapter(tmp_path)
    workspace = Path(adapter.materialize(reservation))
    profile = YamlProfileStoreAdapter(workspace / "profile").load()

    assert profile.appearance == candidate.appearance
    adapter.release(reservation.elfie_id)


def test_workspace_adapter_persists_both_accepted_portrait_views(
    tmp_path: Path,
) -> None:
    png = b"\x89PNG\r\n\x1a\nportrait"
    data_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    adapter = FinalElfieWorkspaceAdapter(tmp_path)
    reservation = AcceptedAdoptionReservation(
        elfie_id="00000003",
        owner_user_id=7,
        name="星砂",
        species_id="fox",
        personality_style="好奇探索",
        height="standard",
        build="standard",
        appearance_seed=42,
        face="soft",
        signature="warm",
        gender="female",
        birth_date="2000-01-01",
        full_body_image_url=data_url,
        headshot_image_url=data_url,
    )

    workspace = Path(adapter.materialize(reservation))

    assert (workspace / "assets" / "portrait-full.png").read_bytes() == png
    assert (workspace / "assets" / "portrait-head.png").read_bytes() == png
    adapter.release(reservation.elfie_id)
