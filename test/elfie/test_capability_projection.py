from datetime import datetime, timezone

from elfie.body import BodyCapabilities, BodyCapabilityDescriptor, HeadlessBody
from elfie.brain_wiring import EffectiveCapabilityProjection
from elfie.communication import CommunicationHub

NOW = datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc)


def test_projection_uses_body_catalog_as_the_single_dynamic_fact_source() -> None:
    body = HeadlessBody(
        body_id="catalog-body",
        capabilities=BodyCapabilities(
            sensors=frozenset({"vision", "private.sensor"}),
            actions=frozenset({"move.forward", "private.action"}),
            action_catalog=(
                BodyCapabilityDescriptor(
                    capability_id="move.forward",
                    description="Move forward",
                    registration_source="godot.native_body",
                    return_schema={"type": "object"},
                ),
            ),
            input_catalog=(
                BodyCapabilityDescriptor(
                    capability_id="vision",
                    registration_source="godot.native_body",
                ),
            ),
        ),
    )
    projection = EffectiveCapabilityProjection(
        current_body=lambda: body,
        communication=CommunicationHub("catalog-elfie"),
    )

    capabilities = projection.current(NOW, {})

    assert capabilities.current_body is not None
    assert capabilities.current_body.actions == ("move.forward",)
    assert capabilities.current_body.sensors == ("vision",)
    assert capabilities.current_body.action_catalog[0].registration_source == (
        "godot.native_body"
    )
    assert capabilities.current_body.action_catalog[0].return_schema == {
        "type": "object"
    }
    assert capabilities.capability_catalog[0].capability_id == "move.forward"
    assert "private.action" not in {
        item.capability_id for item in capabilities.capability_catalog
    }
    assert body.capabilities.supports_action("private.action") is False
    assert body.capabilities.supports_sensor("private.sensor") is False
