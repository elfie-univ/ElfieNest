"""Translate one typed Nest event into the target Elfie's perception contract."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Union

from elfie.public import (
    ActorId,
    ActorRef,
    BodyId,
    BodySensorEvent,
    Elfie,
    EventId,
    HeardUtterancePayload,
    NestFactNoticePayload,
    SemanticActionResultPayload,
    SemanticVisualEntityPayload,
    SemanticVisualScenePayload,
)
from nest.public import (
    HeardUtterance,
    NestEventEnvelope,
    NestFactNotice,
    SemanticActionResult,
    SemanticVisualScene,
)

_NestBodyPayload = Union[
    HeardUtterancePayload,
    SemanticVisualScenePayload,
    SemanticActionResultPayload,
    NestFactNoticePayload,
]


def _body_scope(elfie: Elfie, target_id: str) -> tuple[BodyId, int]:
    current_body = getattr(elfie, "current_body", None)
    candidate_body_id = getattr(current_body, "body_id", None)
    body_id = (
        BodyId(candidate_body_id)
        if isinstance(candidate_body_id, str) and candidate_body_id.strip()
        else BodyId(f"nest-body:{target_id}")
    )
    candidate_generation = getattr(elfie, "current_body_generation", None)
    generation = (
        candidate_generation
        if isinstance(candidate_generation, int) and candidate_generation > 0
        else 1
    )
    return body_id, generation


def nest_event_to_body_sensor_event(
    *,
    envelope: NestEventEnvelope,
    target_id: str,
    elfie: Elfie,
    received_at: datetime | None = None,
) -> BodySensorEvent | None:
    """Preserve the Nest payload and causal identity at the Elfie boundary."""
    body_id, body_generation = _body_scope(elfie, target_id)
    source = ActorRef(actor_id=ActorId("nest"), source_kind="nest")
    payload = envelope.payload
    sensor_payload: _NestBodyPayload
    if isinstance(payload, HeardUtterance):
        sensor_payload = HeardUtterancePayload(
            kind="heard_utterance",
            utterance_id=payload.utterance_id,
            sender_id=payload.sender_id,
            text=payload.text,
            emotion=payload.emotion,
        )
        source = ActorRef(
            actor_id=ActorId(payload.sender_id),
            source_kind="elfie",
        )
    elif isinstance(payload, SemanticVisualScene):
        sensor_payload = SemanticVisualScenePayload(
            kind="semantic_visual_scene",
            observation_id=payload.observation_id,
            observer_id=payload.observer_id,
            zone_id=payload.zone_id,
            entities=tuple(
                SemanticVisualEntityPayload(
                    semantic_id=entity.semantic_id,
                    kind=entity.kind,
                    zone_id=entity.zone_id,
                    label=entity.label,
                    capabilities=entity.capabilities,
                )
                for entity in payload.entities
            ),
        )
    elif isinstance(payload, SemanticActionResult):
        sensor_payload = SemanticActionResultPayload(
            kind="semantic_action_result",
            command_id=payload.command_id,
            intent_id=payload.intent_id,
            actor_id=payload.actor_id,
            body_generation=payload.body_generation,
            target=payload.target,
            resolved_anchor_id=payload.resolved_anchor_id,
            status=payload.status,
            reason=payload.reason,
        )
    elif isinstance(payload, NestFactNotice):
        sensor_payload = NestFactNoticePayload(
            kind="nest_fact_notice",
            fact_type=payload.fact_type,
            fact_id=payload.fact_id,
            summary=payload.summary,
            zone_id=payload.zone_id,
            active=payload.active,
            lights_on=payload.lights_on,
            quiet_mode=payload.quiet_mode,
            phase=payload.phase,
        )
    else:
        return None

    return BodySensorEvent(
        event_id=EventId(envelope.event_id),
        cause_id=EventId(envelope.cause_id),
        body_id=body_id,
        body_generation=body_generation,
        source=source,
        occurred_at=envelope.occurred_at,
        received_at=received_at or datetime.now(timezone.utc),
        payload=sensor_payload,
    )


__all__ = ("nest_event_to_body_sensor_event",)
