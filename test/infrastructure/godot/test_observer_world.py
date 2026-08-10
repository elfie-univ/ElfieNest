from __future__ import annotations

from app.orchestration.observer import ObserverWorldIntent
from infrastructure.godot.observer_world import GodotObserverWorldAdapter
from nest.godot_gateway.observer import ObserverSemanticEntity, WorldChangingIntent


def test_adapter_translates_semantics_without_geometry_and_delivers_intent() -> None:
    submitted: list[WorldChangingIntent] = []
    adapter = GodotObserverWorldAdapter(
        entities=lambda: {
            "fox-1": ObserverSemanticEntity(
                room_id="local-nest",
                zone_id="dorm",
                posture="resting",
                species_id="fox",
                appearance={"height_scale": 1.0},
                home_anchor_id="dorm-01/bed-01",
            )
        },
        intent_sink=submitted.append,
    )

    entities = adapter.list_entities()
    adapter.submit_intent(ObserverWorldIntent(actor_id="fox-1", interaction="greet"))

    assert entities[0].entity_id == "fox-1"
    assert entities[0].appearance == (("height_scale", 1.0),)
    assert submitted == [
        WorldChangingIntent(
            kind="request_interaction",
            actor_id="fox-1",
            interaction="greet",
        )
    ]
