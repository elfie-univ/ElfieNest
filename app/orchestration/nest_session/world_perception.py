"""Translate Nest room facts into the typed physical perception boundary."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from elfie.public import (
    ActorId,
    ActorRef,
    BodyId,
    BodySensorEvent,
    EventId,
    TactileImpact,
    UtteranceFinal,
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
    for speech in nest.consume_speech_events(elfie_id):
        events.append(
            BodySensorEvent(
                event_id=EventId(speech["event_id"]),
                body_id=body_id,
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

    tactile = session.consume_tactile(elfie_id)
    if tactile["intensity"] > 0.0:
        events.append(
            BodySensorEvent(
                event_id=EventId(f"nest-touch:{uuid4().hex}"),
                body_id=body_id,
                source=ActorRef(
                    actor_id=ActorId("nest-room"),
                    source_kind="room",
                ),
                occurred_at=captured_at,
                received_at=captured_at,
                payload=TactileImpact(
                    kind="tactile_impact",
                    location="body",
                    intensity=tactile["intensity"],
                    direction=tactile["direction"],
                    contact_kind=tactile["contact_kind"],
                    source_semantic_id=tactile["source_semantic_id"],
                    force_newtons=tactile["force_newtons_estimate"],
                ),
            )
        )
    return events


__all__ = ("collect_world_sensory_events",)
