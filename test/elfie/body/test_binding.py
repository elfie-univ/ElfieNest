import pytest

from elfie import Elfie
from elfie.body import BodyBinding, BodyRegistry, BodySwitchError, HeadlessBody
from elfie.profile import create_visual_profile
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter


class FailingBody(HeadlessBody):
    def connect(self) -> None:
        raise RuntimeError("连接失败")


class FailingReconnectBody(HeadlessBody):
    def __init__(self, body_id: str):
        super().__init__(body_id=body_id)
        self.connect_count = 0

    def connect(self) -> None:
        self.connect_count += 1
        if self.connect_count > 1:
            raise RuntimeError("恢复失败")
        super().connect()


def test_binding_switches_body_lifecycle_without_reimplementing_body() -> None:
    registry = BodyRegistry()
    first = HeadlessBody(body_id="first")
    second = HeadlessBody(body_id="second")
    binding = BodyBinding(registry)
    binding.register(first)
    binding.register(second)

    binding.bind("first")
    binding.bind("second")

    assert first.connected is False
    assert second.connected is True
    assert binding.current is second
    assert binding.current_body_id == "second"


def test_binding_restores_previous_body_when_new_connection_fails() -> None:
    binding = BodyBinding()
    first = HeadlessBody(body_id="first")
    failing = FailingBody(body_id="failing")
    binding.register_and_bind(first)
    binding.register(failing)

    with pytest.raises(RuntimeError, match="连接失败"):
        binding.bind("failing")

    assert binding.current is first
    assert first.connected is True
    assert failing.connected is False


def test_elfie_keeps_legacy_body_property_and_supports_formal_switching() -> None:
    first = HeadlessBody(body_id="first")
    first.connect()
    elfie = Elfie(
        character_profile=create_visual_profile(
            elfie_id="elfie-binding", display_name="绑定精灵", species_id="fox", seed=3
        ),
        memory_store=SQLiteMemoryStoreAdapter.in_memory(),
        body=first,
    )
    second = HeadlessBody(body_id="second")

    assert elfie.current_body is first
    assert elfie.body_binding.current is first
    assert elfie.body_registry.require("first") is first

    elfie.register_body(second)
    elfie.bind_body("second")

    assert elfie.current_body is second
    assert first.connected is False
    assert second.connected is True


def test_binding_clears_current_body_when_rollback_also_fails() -> None:
    binding = BodyBinding()
    first = FailingReconnectBody(body_id="first")
    failing = FailingBody(body_id="failing")
    binding.register_and_bind(first)
    binding.register(failing)

    with pytest.raises(BodySwitchError, match="恢复失败"):
        binding.bind("failing")

    assert binding.current is None
    assert first.connected is False
