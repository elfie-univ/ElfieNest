import base64
import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.orchestration.resident_admission import ResidentAdmissionPortError
from elfie import ElfieFactory
from elfie.factory import ElfieAssembly
from elfie.genesis import (
    GenesisAppearanceIntent,
    GenesisCompileInput,
    GenesisCompiler,
    GenesisEngine,
)
from infrastructure.persistence.configuration.species import (
    load_and_configure_species_catalog,
)
from infrastructure.persistence.configuration.world import load_genesis_source_package
from infrastructure.persistence.elfie_workspace.adoption_profiles import (
    FinalElfieWorkspaceAdapter,
)
from infrastructure.persistence.elfie_workspace.brain_state import (
    YamlEnergyLimitsAdapter,
    YamlSelfhoodSeedAdapter,
)
from infrastructure.persistence.layout.data_layout import final_root_layout
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter
from test.elfie.genesis.test_contracts import _compilation


@pytest.mark.parametrize("species_id", ("fox", "dog"))
def test_workspace_adapter_stages_publishes_and_reopens_one_compilation(
    tmp_path: Path, species_id: str
) -> None:
    compilation = _compilation("00000001", species_id=species_id)
    adapter = FinalElfieWorkspaceAdapter(tmp_path)

    staged = Path(adapter.stage(compilation))
    assert staged == tmp_path / "elfies" / ".staging" / "00000001"
    assert not final_root_layout(tmp_path).elfie("00000001").workspace.exists()
    assert (
        Path(
            adapter.reopen(
                "00000001",
                manifest_id=compilation.bundle.manifest.manifest_id,
                content_hash=compilation.bundle.manifest.content_hash,
            )
        )
        == staged
    )

    publication = adapter.publication("00000001")
    assert publication.manifest_id == compilation.bundle.manifest.manifest_id
    published = Path(adapter.publish("00000001"))
    assert published == tmp_path / "elfies" / "00000001"
    assert not staged.exists()
    assert (
        Path(
            adapter.reopen(
                "00000001",
                manifest_id=publication.manifest_id,
                content_hash=publication.content_hash,
                output_ids_hash=publication.output_ids_hash,
            )
        )
        == published
    )

    profile = YamlProfileStoreAdapter(published / "profile").load()
    selfhood_seed = YamlSelfhoodSeedAdapter(published / "brain").load()
    energy_limits = YamlEnergyLimitsAdapter(published / "brain").load()
    assert profile.to_dict() == compilation.profile.to_dict()
    assert set(profile.to_dict()) == {"schema_version", "identity", "appearance"}
    assert selfhood_seed["identity_core"]["elfie_id"] == "00000001"
    assert "world" not in selfhood_seed
    assert "canon" not in str(selfhood_seed).lower()
    assert energy_limits["limits"]

    with SQLiteMemoryStoreAdapter(
        published / "memory" / "knowledge.sqlite", elfie_id="00000001"
    ) as memory:
        elfie = ElfieFactory().restore(
            ElfieAssembly(
                profile=profile,
                selfhood_seed=selfhood_seed,
                energy_limits=energy_limits,
                memory_store=memory,
            )
        )
        assert elfie.selfhood_snapshot().species_name
        assert memory.count_episodes() == 5
        assert memory.count_graph_nodes("person") == 13
        assert memory.get_graph_node("genesis:self:00000001") is not None
        assert memory.get_graph_node("genesis:self-model:00000001") is not None
        assert memory.get_graph_node("genesis:receipt:00000001") is not None

    adapter.finalize("00000001")
    assert not (published / ".genesis-stage.json").exists()
    assert published.exists()


def test_workspace_adapter_round_trips_the_real_compile_envelope(
    tmp_path: Path,
) -> None:
    catalog = load_and_configure_species_catalog()
    source = load_genesis_source_package()
    candidate = (
        GenesisEngine(catalog=catalog)
        .generate_batch(
            master_seed=23,
            batch_number=1,
            species_id="fox",
            life_stage="mature",
            gender="female",
            appearance=GenesisAppearanceIntent(
                stature="standard",
                build="standard",
                face="soft",
                signature="warm",
                priority="face",
            ),
            answers=("observe", "research", "comfort", "adapt", "steady"),
        )
        .candidates[0]
    )
    request = GenesisCompileInput(
        elfie_id="00000011",
        owner_reference="envelope-owner",
        display_name="信使",
        species_id=candidate.species_id,
        gender=candidate.gender,
        life_stage=candidate.life_stage,
        age_years_at_adoption=candidate.age_years,
        appearance_seed=candidate.seed,
        height="standard",
        build="standard",
        face="soft",
        signature="warm",
        candidate=candidate,
        personality_style="好奇探索",
        adoption_anchor_at="2026-09-02T00:00:00+00:00",
        reservation_id="envelope:00000011",
        idempotency_key="envelope-submit:00000011",
    )
    compiler = GenesisCompiler(source, catalog=catalog)
    envelope = compiler.create_compile_envelope(request)
    adapter = FinalElfieWorkspaceAdapter(tmp_path)

    adapter.stage_envelope(envelope)
    recovered = adapter.load_envelope("00000011")

    assert recovered is not None
    assert recovered.to_dict() == envelope.to_dict()
    compilation = compiler.compile_envelope(recovered)
    adapter.stage(compilation)
    adapter.publish("00000011")
    adapter.finalize("00000011")

    assert adapter.load_envelope("00000011") is None
    assert (
        not final_root_layout(tmp_path)
        .elfie("00000011")
        .genesis_compile_envelope.exists()
    )


def test_workspace_adapter_does_not_overwrite_a_final_owner(
    tmp_path: Path,
) -> None:
    compilation = _compilation("00000002")
    adapter = FinalElfieWorkspaceAdapter(tmp_path)

    adapter.stage(compilation)
    adapter.publish("00000002")
    with pytest.raises(ResidentAdmissionPortError, match="already exists"):
        adapter.stage(compilation)
    assert adapter.publish("00000002").endswith("/00000002")


def test_workspace_staging_removes_new_workspace_when_memory_commit_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    compilation = _compilation("00000003")

    def fail_commit(*_args, **_kwargs):
        raise OSError("synthetic memory publish failure")

    monkeypatch.setattr(
        "infrastructure.persistence.elfie_workspace.adoption_profiles.GenesisMemoryCommitter.commit",
        fail_commit,
    )

    with pytest.raises(ResidentAdmissionPortError, match="stage"):
        FinalElfieWorkspaceAdapter(tmp_path).stage(compilation)

    assert not (tmp_path / "elfies" / ".staging" / "00000003").exists()
    assert not (tmp_path / "elfies" / "00000003").exists()


def test_workspace_adapter_persists_both_accepted_portrait_views(
    tmp_path: Path,
) -> None:
    png = b"\x89PNG\r\n\x1a\nportrait"
    data_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    compilation = replace(
        _compilation("00000004"),
        full_body_image_url=data_url,
        headshot_image_url=data_url,
    )

    adapter = FinalElfieWorkspaceAdapter(tmp_path)
    adapter.stage(compilation)
    workspace = Path(adapter.publish("00000004"))

    assert (workspace / "assets" / "portrait-full.png").read_bytes() == png
    assert (workspace / "assets" / "portrait-head.png").read_bytes() == png


@pytest.mark.parametrize(
    "full_body_url,headshot_url",
    (
        ("data:image/png;base64,not-base64", ""),
        ("", "data:image/png;base64,not-base64"),
    ),
)
def test_workspace_adapter_rejects_incomplete_or_invalid_portraits(
    tmp_path: Path, full_body_url: str, headshot_url: str
) -> None:
    compilation = replace(
        _compilation("00000005"),
        full_body_image_url=full_body_url,
        headshot_image_url=headshot_url,
    )

    with pytest.raises(ResidentAdmissionPortError):
        FinalElfieWorkspaceAdapter(tmp_path).stage(compilation)

    assert not (tmp_path / "elfies" / ".staging" / "00000005").exists()
    assert not (tmp_path / "elfies" / "00000005").exists()


def test_workspace_reopen_rejects_a_tampered_marker(
    tmp_path: Path,
) -> None:
    compilation = _compilation("00000006")
    adapter = FinalElfieWorkspaceAdapter(tmp_path)
    adapter.stage(compilation)
    marker = tmp_path / "elfies" / ".staging" / "00000006" / ".genesis-stage.json"
    payload = json.loads(marker.read_text(encoding="utf-8"))
    payload["content_hash"] = "0" * 64
    marker.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ResidentAdmissionPortError, match="integrity"):
        adapter.reopen("00000006")

    adapter.abort("00000006")


def test_workspace_reopen_rejects_a_missing_declared_output(
    tmp_path: Path,
) -> None:
    compilation = _compilation("00000007")
    adapter = FinalElfieWorkspaceAdapter(tmp_path)
    adapter.stage(compilation)
    memory_path = (
        tmp_path / "elfies" / ".staging" / "00000007" / "memory" / "knowledge.sqlite"
    )
    with SQLiteMemoryStoreAdapter(memory_path, elfie_id="00000007") as memory:
        knowledge_id = next(
            identifier
            for identifier in compilation.bundle.manifest.output_ids
            if ":knowledge:" in identifier
        )
        memory.conn.execute(
            "UPDATE nodes SET status='forgotten' WHERE node_id=?",
            (knowledge_id,),
        )
        memory.conn.commit()

    with pytest.raises(ResidentAdmissionPortError, match="integrity"):
        adapter.reopen("00000007")

    adapter.abort("00000007")
