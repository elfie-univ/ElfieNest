from typing_extensions import assert_never

from nest.events import (
    HomeAssignedEvent,
    NestDomainEvent,
    ResidentAdmittedEvent,
    RuntimeMirrorUpdatedEvent,
)


def describe_event(event: NestDomainEvent) -> str:
    if isinstance(event, ResidentAdmittedEvent):
        return f"resident:{event.elfie_id}"
    if isinstance(event, HomeAssignedEvent):
        return f"home:{event.elfie_id}:{event.home_anchor_id}"
    if isinstance(event, RuntimeMirrorUpdatedEvent):
        return f"runtime:{event.elfie_id}:{event.current_zone_id}"
    assert_never(event)


def test_nest_domain_events_are_closed_semantic_values() -> None:
    # Given
    admitted = ResidentAdmittedEvent(elfie_id="fox-1")
    assigned = HomeAssignedEvent(
        elfie_id="fox-1",
        home_zone_id="dorm-01",
        home_anchor_id="dorm-01/bed-01",
    )
    mirrored = RuntimeMirrorUpdatedEvent(
        elfie_id="fox-1",
        current_zone_id="activity-main",
        posture="standing",
        active_command_id="command-1",
    )

    # When / Then
    assert describe_event(admitted) == "resident:fox-1"
    assert describe_event(assigned) == "home:fox-1:dorm-01/bed-01"
    assert describe_event(mirrored) == "runtime:fox-1:activity-main"
