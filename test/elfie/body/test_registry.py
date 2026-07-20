import pytest

from elfie.body import (
    BodyNotFoundError,
    BodyRegistrationError,
    BodyRegistry,
    HeadlessBody,
)


def test_registry_registers_and_describes_existing_body_instances() -> None:
    registry = BodyRegistry()
    body = HeadlessBody(body_id="debug")

    registry.register(body)

    assert registry.require("debug") is body
    assert registry.describe_all()[0].body_id == "debug"
    assert "debug" in registry
    assert len(registry) == 1


def test_registry_rejects_duplicate_ids_and_missing_bodies() -> None:
    registry = BodyRegistry()
    registry.register(HeadlessBody(body_id="same"))

    with pytest.raises(BodyRegistrationError, match="已经注册"):
        registry.register(HeadlessBody(body_id="same"))
    with pytest.raises(BodyNotFoundError):
        registry.require("missing")
