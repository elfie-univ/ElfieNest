"""Translate Nest room facts into the typed physical perception boundary."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.orchestration.nest_session import NestSession
from elfie.body import BodyId, BodySensorEvent, TactileImpact, UtteranceFinal
from elfie.message_types import ActorId, ActorRef, EventId
from nest import Nest


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
    pending_speech = nest.consume_sensory_input(elfie_id)
    if pending_speech:
        events.append(
            BodySensorEvent(
                event_id=EventId(f"nest-room-speech:{uuid4().hex}"),
                body_id=body_id,
                source=ActorRef(
                    actor_id=ActorId("nest-room"),
                    source_kind="room",
                ),
                occurred_at=captured_at,
                received_at=captured_at,
                payload=UtteranceFinal(
                    kind="utterance_final",
                    text=pending_speech,
                ),
            )
        )

    tactile = session.consume_tactile(elfie_id)
    if (
        float(tactile.get("impact_force", 0.0)) > 0.0
        or float(tactile.get("gentle_stroke", 0.0)) > 0.0
    ):
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
                    force_newtons=float(tactile.get("impact_force", 0.0)),
                ),
            )
        )
    return events


__all__ = ("collect_world_sensory_events",)
