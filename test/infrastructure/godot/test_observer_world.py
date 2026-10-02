from __future__ import annotations

from app.orchestration.nest_session import ObserverSemanticEntity
from app.orchestration.observer import ObserverWorldIntent
from infrastructure.godot.observer_world import GodotObserverWorldAdapter


def test_adapter_translates_semantics_without_geometry_and_delivers_intent() -> None:
    submitted: list[tuple[str, str]] = []
    adapter = GodotObserverWorldAdapter(
        entities=lambda: {
            "saevi-1": ObserverSemanticEntity(
                room_id="local-nest",
                zone_id="dorm",
                posture="resting",
                species_id="saevi",
                appearance={"height_scale": 1.0},
                home_anchor_id="dorm-01/bed-01",
            )
        },
        intent_sink=lambda actor_id, interaction: submitted.append(
            (actor_id, interaction)
        ),
    )

    entities = adapter.list_entities()
    adapter.submit_intent(ObserverWorldIntent(actor_id="saevi-1", interaction="greet"))

    assert entities[0].entity_id == "saevi-1"
    assert entities[0].appearance == (("height_scale", 1.0),)
    assert submitted == [("saevi-1", "greet")]
