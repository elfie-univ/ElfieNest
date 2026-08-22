"""Shared typed fixtures for NervousSystem perception bridge tests."""

from __future__ import annotations

from datetime import datetime, timezone

from elfie.body.contracts import (
    BodyId,
    BodySensorEvent,
    EnvironmentSample,
    HeardUtterancePayload,
    NestFactNoticePayload,
    ProprioceptionSample,
    SemanticActionResultPayload,
    SemanticVisualScenePayload,
    TactileImpact,
    UtteranceFinal,
    VisionSample,
)
from elfie.brain.workspace.contracts import TriggerReason
from elfie.brain.workspace.system import EventWorkspace
from elfie.message_types import ActorId, ActorRef, ElfieId, EventId, TurnId

NOW = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)
ELFIE_ID = ElfieId("elfie-nervous")
BODY_ID = BodyId("body-nervous")
OWNER = ActorRef(actor_id=ActorId("owner-near"), source_kind="microphone")
ROOM = ActorRef(actor_id=ActorId("room-left"), source_kind="microphone")


def body_event(
    event_id: str,
    source: ActorRef,
    payload: (
        UtteranceFinal
        | VisionSample
        | TactileImpact
        | ProprioceptionSample
        | EnvironmentSample
        | HeardUtterancePayload
        | NestFactNoticePayload
        | SemanticVisualScenePayload
        | SemanticActionResultPayload
    ),
    *,
    cause_id: str | None = None,
) -> BodySensorEvent:
    """Build one typed Body event with stable test identity."""
    return BodySensorEvent(
        event_id=EventId(event_id),
        cause_id=EventId(cause_id) if cause_id is not None else None,
        body_id=BODY_ID,
        source=source,
        occurred_at=NOW,
        received_at=NOW,
        payload=payload,
    )


def claim_all(workspace: EventWorkspace):
    """Seal and claim every currently visible workspace write."""
    frame_id = workspace.seal(reason=TriggerReason.MANUAL, captured_at=NOW)
    assert frame_id is not None
    return workspace.claim(frame_id, TurnId(f"turn-{frame_id}"))
