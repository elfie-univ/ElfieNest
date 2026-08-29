from dataclasses import replace
from pathlib import Path

from elfie import Elfie, ElfieFactory
from elfie.body import BodyMode, HeadlessBody, QuadrupedAnatomy
from elfie.diagnostics import ElfieDiagnostics
from elfie.factory import ElfieAssembly
from elfie.profile import (
    EmbodimentProfile,
    create_visual_profile,
)
from infrastructure.godot import GodotTransport, NativeBody
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter
from infrastructure.persistence.profile_store import YamlProfileStoreAdapter


def test_memory_adapter_owns_workspace_knowledge_sqlite(tmp_path: Path) -> None:
    db_path = tmp_path / "memory" / "knowledge.sqlite"
    db_path.parent.mkdir()
    store = SQLiteMemoryStoreAdapter(db_path)
    assert db_path.is_file()
    with store.connection as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
    assert len(tables) == 13
    assert not (tmp_path / "graph_memory.db").exists()
    store.close()


def make_profile(config_dir: Path, elfie_id: str = "elfie-profile"):
    profile = create_visual_profile(
        elfie_id=elfie_id,
        display_name="小狐",
        species_id="fox",
        seed=42,
    )
    YamlProfileStoreAdapter(config_dir / "profile").save(profile)
    return profile


class FakeGodotGateway:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def send_body_command(
        self,
        payload: dict[str, object],
        *,
        cause_id: str,
    ) -> bool:
        self.sent.append({"payload": payload, "cause_id": cause_id})
        return True

    def cancel_body_command(self, *, command_id: str, actor_id: str) -> bool:
        self.sent.append({"command_id": command_id, "actor_id": actor_id})
        return True

    def register_body_sink(self, actor_id: str, sink: object) -> None:
        _ = actor_id, sink

    def unregister_body_sink(self, actor_id: str, sink: object) -> None:
        _ = actor_id, sink


def test_factory_consumes_typed_profile_and_memory_ports() -> None:
    profile = create_visual_profile(
        elfie_id="elfie-port",
        display_name="端口精灵",
        species_id="fox",
        seed=17,
    )

    elfie = ElfieFactory().create(
        ElfieAssembly(
            profile=profile,
            memory_store=SQLiteMemoryStoreAdapter.in_memory(),
        )
    )

    assert elfie.profile == profile


def test_factory_assembles_from_an_immutable_typed_dependency_record() -> None:
    profile = create_visual_profile(
        elfie_id="elfie-assembly",
        display_name="装配精灵",
        species_id="fox",
        seed=23,
    )
    store = SQLiteMemoryStoreAdapter.in_memory()

    elfie = ElfieFactory().assemble(ElfieAssembly(profile=profile, memory_store=store))

    assert elfie.profile == profile
    assert ElfieDiagnostics(elfie).memory.storage is store
    ElfieDiagnostics(elfie).memory.close()
    store.close()


def test_factory_creates_canonical_elfie_without_copying_legacy_algorithms() -> None:
    profile = create_visual_profile(
        elfie_id="elfie-new", display_name="新精灵", species_id="fox", seed=11
    )
    elfie = ElfieFactory().create(
        ElfieAssembly(
            profile=profile,
            memory_store=SQLiteMemoryStoreAdapter.in_memory(),
        )
    )

    assert isinstance(elfie, Elfie)
    assert ElfieDiagnostics(elfie).workspace is not None
    assert ElfieDiagnostics(elfie).nervous_system is not None
    assert ElfieDiagnostics(elfie).memory is not None
    assert elfie.identity.elfie_id == "elfie-new"
    assert not hasattr(elfie, "brain")


def test_elfie_facade_does_not_expose_mutable_subsystem_owners() -> None:
    elfie = ElfieFactory().create(
        ElfieAssembly(
            profile=create_visual_profile(
                elfie_id="facade-elfie",
                display_name="门面精灵",
                species_id="fox",
                seed=31,
            ),
            memory_store=SQLiteMemoryStoreAdapter.in_memory(),
        )
    )

    assert all(
        not hasattr(elfie, name)
        for name in (
            "memory",
            "amygdala",
            "hypothalamus",
            "selfhood",
            "perceptual_workspace",
            "activity_store",
            "communication",
            "nervous_system",
            "body_registry",
            "body_binding",
            "skills",
            "anatomy",
        )
    )


def test_factory_accepts_an_already_assembled_native_body() -> None:
    gateway = FakeGodotGateway()
    profile = create_visual_profile(
        elfie_id="elfie-native", display_name="原生精灵", species_id="fox", seed=12
    )

    elfie = ElfieFactory().create(
        ElfieAssembly(
            profile=profile,
            memory_store=SQLiteMemoryStoreAdapter.in_memory(),
            body=NativeBody(
                body_id="elfie-native",
                transport=GodotTransport(gateway, actor_id="elfie-native"),
            ),
        ),
    )

    assert elfie.current_body is not None
    assert elfie.current_body.body_id == "elfie-native"
    assert elfie.current_body.describe().mode is BodyMode.NATIVE
    assert elfie.current_body.snapshot_body().connected is True


def test_factory_restores_persisted_profile_and_identity(tmp_path: Path) -> None:
    profile = make_profile(tmp_path)
    db_path = tmp_path / "memory" / "knowledge.sqlite"
    db_path.parent.mkdir()

    elfie = ElfieFactory().restore(
        ElfieAssembly(
            profile=YamlProfileStoreAdapter(tmp_path / "profile").load(),
            memory_store=SQLiteMemoryStoreAdapter(db_path),
        )
    )

    assert elfie.profile is profile or elfie.profile.to_dict() == profile.to_dict()
    assert elfie.identity.display_name == "小狐"
    assert elfie.species_id == "fox"


def test_restore_preserves_profile_and_explicit_body_binding(tmp_path: Path) -> None:
    # Given
    profile = make_profile(tmp_path)
    explicit = HeadlessBody(body_id="explicit")

    # When
    elfie = ElfieFactory().restore(
        ElfieAssembly(
            profile=YamlProfileStoreAdapter(tmp_path / "profile").load(),
            memory_store=SQLiteMemoryStoreAdapter.in_memory(),
            bodies=(explicit,),
            current_body_id="explicit",
        )
    )

    # Then
    assert elfie.profile.to_dict() == profile.to_dict()
    assert elfie.current_body is explicit
    assert explicit.connected is True


def test_factory_uses_profile_embodiment_as_the_anatomy_source(
    tmp_path: Path,
) -> None:
    profile = replace(
        make_profile(tmp_path),
        embodiment=EmbodimentProfile(
            primary_morphology="quadruped",
            supported_morphologies=("quadruped",),
            skeleton_profile_id="quadruped_test_v1",
            capability_profile_id="fox_quadruped_v1",
        ),
    )
    YamlProfileStoreAdapter(tmp_path / "profile").save(profile)

    elfie = ElfieFactory().restore(
        ElfieAssembly(
            profile=YamlProfileStoreAdapter(tmp_path / "profile").load(),
            memory_store=SQLiteMemoryStoreAdapter.in_memory(),
        )
    )

    assert elfie.anatomy_type == "quadruped"
    assert isinstance(ElfieDiagnostics(elfie).anatomy, QuadrupedAnatomy)


def test_factory_registers_multiple_bodies_and_selects_current_body() -> None:
    first = HeadlessBody(body_id="first")
    second = HeadlessBody(body_id="second")
    profile = create_visual_profile(
        elfie_id="elfie-bodies", display_name="多身体精灵", species_id="fox", seed=13
    )

    elfie = ElfieFactory().create(
        ElfieAssembly(
            profile=profile,
            memory_store=SQLiteMemoryStoreAdapter.in_memory(),
            bodies=(first, second),
            current_body_id="second",
        )
    )

    assert elfie.current_body is second
    assert second.connected is True
    assert first.connected is False
    assert [
        item.body_id for item in ElfieDiagnostics(elfie).body_registry.describe_all()
    ] == [
        "first",
        "second",
    ]
