"""Translate Nest room facts into the typed physical perception boundary."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from elfie.public import (
    ActorId,
    ActorRef,
    BodyId,
    BodySensorEvent,
    EventId,
    UtteranceFinal,
    VisionChange,
)
from nest.public import Nest

if TYPE_CHECKING:
    from app.orchestration.nest_session.session import NestSession


def collect_world_sensory_events(
    *,
    nest: Nest,
    session: NestSession,
    elfie_id: str,
    captured_at: datetime,
) -> list[BodySensorEvent]:
    """Convert only physical room facts into typed Body sensor events."""
    events: list[BodySensorEvent] = []
    elfie = session.elfies.get(elfie_id)
    current_body = getattr(elfie, "current_body", None)
    body_id = BodyId(
        str(getattr(current_body, "body_id", "") or f"nest-body:{elfie_id}")
    )
    body_generation = int(getattr(elfie, "current_body_generation", 1) or 1)
    for speech in nest.consume_speech_events(elfie_id):
        events.append(
            BodySensorEvent(
                event_id=EventId(speech["event_id"]),
                body_id=body_id,
                body_generation=body_generation,
                source=ActorRef(
                    actor_id=ActorId(speech["sender_id"]),
                    source_kind="elfie",
                ),
                occurred_at=captured_at,
                received_at=captured_at,
                payload=UtteranceFinal(
                    kind="utterance_final",
                    text=speech["text"],
                ),
            )
        )

    for visual in nest.consume_visual_events(elfie_id):
        occurred_at = visual["occurred_at"]
        events.append(
            BodySensorEvent(
                event_id=EventId(visual["event_id"]),
                body_id=body_id,
                body_generation=body_generation,
                source=ActorRef(
                    actor_id=ActorId("nest"),
                    source_kind="nest",
                ),
                occurred_at=occurred_at,
                received_at=captured_at,
                payload=VisionChange(
                    kind="vision_change",
                    description=visual["description"],
                ),
            )
        )

    return events


__all__ = ("collect_world_sensory_events",)
