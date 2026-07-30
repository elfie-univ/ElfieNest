import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from elfie import Elfie, ElfieFactory
from elfie.body import BodyMode, HeadlessBody, QuadrupedAnatomy
from elfie.profile import (
    ElfieProfileRepository,
    EmbodimentProfile,
    create_visual_profile,
)


def test_factory_defaults_workspace_memory_to_knowledge_sqlite(tmp_path: Path) -> None:
    # Given
    workspace = tmp_path / "workspace"

    # When
    elfie = ElfieFactory().create(config_dir=workspace, elfie_id="elfie-final-store")

    # Then
    db_path = workspace / "memory" / "knowledge.sqlite"
    assert db_path.is_file()
    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
    assert len(tables) == 9
    assert not (workspace / "graph_memory.db").exists()
    elfie.memory.close()


def make_profile(config_dir: Path, elfie_id: str = "elfie-profile"):
    profile = create_visual_profile(
        elfie_id=elfie_id,
        display_name="小狐",
        species_id="fox",
        seed=42,
    )
    ElfieProfileRepository(config_dir / "profile").save(profile)
    return profile


class FakeGodotGateway:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def send_body_command(
        self,
        payload: dict[str, object],
        *,
        correlation_id: str,
    ) -> bool:
        self.sent.append({"payload": payload, "correlation_id": correlation_id})
        return True

    def cancel_body_command(self, *, command_id: str, actor_id: str) -> bool:
        self.sent.append({"command_id": command_id, "actor_id": actor_id})
        return True


def test_factory_creates_canonical_elfie_without_copying_legacy_algorithms() -> None:
    elfie = ElfieFactory().create(elfie_id="elfie-new", memory_db_path=":memory:")

    assert isinstance(elfie, Elfie)
    assert elfie.perceptual_workspace is not None
    assert elfie.nervous_system is not None
    assert elfie.memory is not None
    assert elfie.identity.elfie_id == "elfie-new"
    assert not hasattr(elfie, "brain")


def test_factory_builds_and_connects_native_body_when_godot_gateway_is_supplied() -> (
    None
):
    gateway = FakeGodotGateway()

    elfie = ElfieFactory().create(
        elfie_id="elfie-native",
        memory_db_path=":memory:",
        godot_api=gateway,
    )

    assert elfie.current_body is not None
    assert elfie.current_body.body_id == "elfie-native"
    assert elfie.current_body.describe().mode is BodyMode.NATIVE
    assert elfie.current_body.snapshot_body().connected is True


def test_factory_restores_persisted_profile_and_identity(tmp_path: Path) -> None:
    profile = make_profile(tmp_path)

    elfie = ElfieFactory().restore(
        tmp_path,
        elfie_id="elfie-profile",
        memory_db_path=":memory:",
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
        tmp_path,
        bodies=[explicit],
        current_body_id="explicit",
        memory_db_path=":memory:",
    )

    # Then
    assert elfie.profile.to_dict() == profile.to_dict()
    assert elfie.current_body is explicit
    assert explicit.connected is True


def test_factory_uses_profile_embodiment_when_legacy_anatomy_is_absent(
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
    ElfieProfileRepository(tmp_path / "profile").save(profile)

    elfie = ElfieFactory().restore(tmp_path, memory_db_path=":memory:")

    assert elfie.anatomy_type == "quadruped"
    assert isinstance(elfie.anatomy, QuadrupedAnatomy)


def test_factory_rejects_identity_that_conflicts_with_profile(tmp_path: Path) -> None:
    make_profile(tmp_path)

    with pytest.raises(ValueError, match="与 profile 身份"):
        ElfieFactory().restore(
            tmp_path,
            elfie_id="different-id",
            memory_db_path=":memory:",
        )


def test_factory_registers_multiple_bodies_and_selects_current_body() -> None:
    first = HeadlessBody(body_id="first")
    second = HeadlessBody(body_id="second")

    elfie = ElfieFactory().create(
        elfie_id="elfie-bodies",
        memory_db_path=":memory:",
        bodies=[first, second],
        current_body_id="second",
    )

    assert elfie.current_body is second
    assert second.connected is True
    assert first.connected is False
    assert [item.body_id for item in elfie.body_registry.describe_all()] == [
        "first",
        "second",
    ]
