from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Dict, List

import pytest

from elfie import Elfie, ElfieFactory
from elfie.body import BodyMode, HeadlessBody, QuadrupedAnatomy
from elfie.profile import (
    ElfieProfileRepository,
    EmbodimentProfile,
    create_visual_profile,
)


def make_profile(config_dir: Path, elfie_id: str = "elfie-profile"):
    profile = create_visual_profile(
        elfie_id=elfie_id,
        display_name="小狐",
        species_id="fox",
        seed=42,
    )
    ElfieProfileRepository(config_dir).save(profile)
    return profile


class FakeGodotGateway:
    def __init__(self) -> None:
        self.callbacks: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}
        self.sent = []
        self.runtime_ready = False

    def register_callback(self, event_name: str, callback: Callable) -> None:
        self.callbacks.setdefault(event_name, []).append(callback)

    def send_action(self, action: str, payload: Dict[str, Any]) -> None:
        self.sent.append({"action": action, "payload": payload})


def test_factory_creates_canonical_elfie_without_copying_legacy_algorithms() -> None:
    elfie = ElfieFactory().create(elfie_id="elfie-new", memory_db_path=":memory:")

    assert isinstance(elfie, Elfie)
    assert elfie.brain is not None
    assert elfie.nervous_system is not None
    assert elfie.memory is not None
    assert elfie.identity.elfie_id == "elfie-new"


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
    assert elfie.current_body.snapshot().connected is True
    assert gateway.callbacks


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
    ElfieProfileRepository(tmp_path).save(profile)

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
    assert [item["body_id"] for item in elfie.describe()["available_bodies"]] == [
        "first",
        "second",
    ]


def test_factory_restore_preserves_legacy_directory_without_profile(
    tmp_path: Path,
) -> None:
    elfie = ElfieFactory().restore(
        tmp_path,
        elfie_id="legacy-elfie",
        memory_db_path=":memory:",
    )

    assert elfie.identity.elfie_id == "legacy-elfie"
    assert elfie.species_id == "fox"
    assert ElfieProfileRepository(tmp_path).load() == elfie.profile


def test_factory_migrates_legacy_config_into_canonical_profile(tmp_path: Path) -> None:
    (tmp_path / "personality.yaml").write_text(
        "metadata:\n  name: 老精灵\nbig_five:\n  openness: 0.75\n",
        encoding="utf-8",
    )
    (tmp_path / "capabilities.yaml").write_text(
        "actuators:\n  motion:\n    supported_actions: [walk]\n",
        encoding="utf-8",
    )
    (tmp_path / "system_limits.yaml").write_text(
        "limits:\n  energy:\n    max_value: 100\n",
        encoding="utf-8",
    )

    elfie = ElfieFactory().restore(
        tmp_path,
        elfie_id="legacy-config",
        memory_db_path=":memory:",
    )
    migrated = ElfieProfileRepository(tmp_path).load()

    assert migrated == elfie.profile
    assert migrated.identity.display_name == "老精灵"
    assert migrated.personality["big_five"]["openness"] == 0.75
    assert migrated.capabilities["actuators"]["motion"]["supported_actions"] == ["walk"]
    assert migrated.system_limits["limits"]["energy"]["max_value"] == 100


def test_restore_ignores_legacy_state_yaml(tmp_path: Path) -> None:
    # Given
    make_profile(tmp_path)
    explicit = HeadlessBody(body_id="headless-new")
    legacy_state = tmp_path / "state.yaml"
    legacy_content = (
        "schema_version: 1\n"
        "energy: 1\n"
        "emotions:\n"
        "  fear: 99\n"
        "current_body_id: old\n"
    )
    legacy_state.write_text(legacy_content, encoding="utf-8")

    # When
    elfie = ElfieFactory().restore(
        tmp_path,
        bodies=[explicit],
        current_body_id="headless-new",
        memory_db_path=":memory:",
    )

    # Then
    assert elfie.hypothalamus.energy == elfie.hypothalamus.max_energy
    assert elfie.amygdala.emotions["fear"] == 10.0
    assert elfie.current_body is explicit
    assert legacy_state.read_text(encoding="utf-8") == legacy_content


def test_restore_does_not_use_legacy_binding_without_explicit_body(
    tmp_path: Path,
) -> None:
    # Given
    make_profile(tmp_path)
    available = HeadlessBody(body_id="available")
    legacy_state = tmp_path / "state.yaml"
    legacy_content = "energy: 1\ncurrent_body_id: missing-body\n"
    legacy_state.write_text(legacy_content, encoding="utf-8")

    # When
    elfie = ElfieFactory().restore(
        tmp_path,
        bodies=[available],
        memory_db_path=":memory:",
    )

    # Then
    assert elfie.hypothalamus.energy == elfie.hypothalamus.max_energy
    assert elfie.current_body is None
    assert available.connected is False
    assert legacy_state.read_text(encoding="utf-8") == legacy_content
