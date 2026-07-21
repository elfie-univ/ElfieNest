"""Temporary adapter from legacy BodyEvent batches to typed perception."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Tuple

from elfie.body.contracts import (
    BodyId,
    BodySensorEvent,
    EnvironmentSample,
    ProprioceptionSample,
    TactileImpact,
    UtteranceFinal,
    VisionChange,
)
from elfie.body.types import BodyEvent
from elfie.message_types import ActorId, ActorRef, EventId


def adapt_legacy_body_events(
    events: Iterable[BodyEvent],
    *,
    body_id: BodyId,
) -> Tuple[Tuple[BodySensorEvent, ...], Dict[str, Any]]:
    """Build typed events plus the deprecated raw view used until Task 14."""
    typed_events: List[BodySensorEvent] = []
    raw: Dict[str, Any] = {"sensory_events": []}
    heard_messages: List[str] = []
    image_paths: List[str] = []

    for event in events:
        payload = dict(event.payload)
        raw["sensory_events"].append(
            {
                "event_id": event.event_id,
                "sensor": event.sensor,
                "source": event.source,
                "timestamp": event.timestamp,
                "payload": payload,
            }
        )
        raw.update(payload)
        heard = _heard_text(event.sensor, payload)
        if heard:
            heard_messages.append(heard)
        image_paths.extend(_image_paths(event.sensor, payload))
        typed = _to_typed_event(event, body_id=body_id, heard=heard)
        if typed is not None:
            typed_events.append(typed)

    if heard_messages:
        raw["has_new_message"] = True
        raw["user_message"] = "\n".join(heard_messages)
    if image_paths:
        raw["images"] = list(dict.fromkeys(image_paths))
    return tuple(typed_events), raw


def _to_typed_event(
    event: BodyEvent,
    *,
    body_id: BodyId,
    heard: str,
) -> BodySensorEvent | None:
    payload = dict(event.payload)
    if event.sensor == "hearing" and heard:
        typed_payload = UtteranceFinal(kind="utterance_final", text=heard)
    elif event.sensor == "vision":
        description = str(
            payload.get("description")
            or payload.get("caption")
            or f"legacy vision event from {event.source}"
        )
        typed_payload = VisionChange(kind="vision_change", description=description)
    elif event.sensor == "touch":
        typed_payload = TactileImpact(
            kind="tactile_impact",
            location=str(payload.get("location") or "unknown"),
            force_newtons=max(0.0, float(payload.get("impact_force", 0.0))),
        )
    elif event.sensor == "environment":
        typed_payload = EnvironmentSample(
            kind="environment_sample",
            temperature_celsius=_optional_float(payload.get("temperature")),
            humidity_ratio=_optional_float(payload.get("humidity_ratio")),
            illuminance_lux=_optional_float(payload.get("illuminance_lux")),
        )
    elif event.sensor == "proprioception":
        typed_payload = ProprioceptionSample(
            kind="proprioception_sample",
            posture=str(payload.get("posture") or "unknown"),
            target=str(payload["target"]) if payload.get("target") else None,
            arrived=bool(payload.get("arrived_at", False)),
        )
    else:
        return None

    event_time = datetime.fromtimestamp(event.timestamp, tz=timezone.utc)
    return BodySensorEvent(
        event_id=EventId(event.event_id),
        body_id=body_id,
        source=ActorRef(
            actor_id=ActorId(event.source),
            source_kind=event.source,
        ),
        occurred_at=event_time,
        received_at=event_time,
        payload=typed_payload,
    )


def _heard_text(sensor: str, payload: Dict[str, Any]) -> str:
    if sensor != "hearing":
        return ""
    return str(
        payload.get("user_message")
        or payload.get("transcript")
        or payload.get("text")
        or ""
    ).strip()


def _image_paths(sensor: str, payload: Dict[str, Any]) -> Tuple[str, ...]:
    if sensor != "vision":
        return ()
    candidates = payload.get("images", payload.get("image_paths", ()))
    if isinstance(candidates, str):
        candidates = (candidates,)
    paths = tuple(str(path) for path in candidates if str(path))
    single_path = payload.get("image") or payload.get("path")
    return paths + ((str(single_path),) if single_path else ())


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


__all__ = ("adapt_legacy_body_events",)
