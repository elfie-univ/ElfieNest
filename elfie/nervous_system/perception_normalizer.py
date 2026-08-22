"""Normalize typed Body sensor events into Brain perception writes."""

from __future__ import annotations

from typing import Dict, Tuple

from elfie.body.contracts import (
    BodySensorEvent,
    EnvironmentSample,
    HeardUtterancePayload,
    NestFactNoticePayload,
    ProprioceptionSample,
    SemanticActionResultPayload,
    SemanticVisualScenePayload,
    TactileImpact,
    UtteranceFinal,
    VisionChange,
    VisionSample,
)
from elfie.brain.workspace.contracts import (
    PerceptionEvent,
    PerceptionMediaSample,
    PerceptionStateUpdate,
    PerceptionWrite,
    PhysicalModality,
    PhysicalPayload,
)
from elfie.message_types import (
    ElfieId,
    EventId,
    MessageMeta,
    Priority,
    TraceId,
)
from elfie.nervous_system.signal_filter import SensoryDamSignalFilter


class UnsupportedSensorPayloadError(TypeError):
    """Typed failure for a Body payload outside the declared union."""

    def __init__(self, payload_type: str) -> None:
        self.payload_type = payload_type
        super().__init__(f"unsupported sensor payload: {payload_type}")


class BodyPerceptionNormalizer:
    """Stateful physical filtering and typed workspace normalization."""

    def __init__(
        self,
        elfie_id: ElfieId,
        signal_filter: SensoryDamSignalFilter,
    ) -> None:
        self._elfie_id = elfie_id
        self._signal_filter = signal_filter
        self._media_filter = SensoryDamSignalFilter()
        self._state_revisions: Dict[str, int] = {}
        self._state_values: Dict[str, bool | float | str] = {}
        self._media_ordinals: Dict[str, int] = {}

    def normalize(self, event: BodySensorEvent) -> Tuple[PerceptionWrite, ...]:
        """Route one discriminated Body payload to journal, state, or media."""
        payload = event.payload
        if isinstance(payload, HeardUtterancePayload):
            emotion = f" emotion={payload.emotion};" if payload.emotion else ""
            return self._reliable(
                event,
                PhysicalModality.UTTERANCE,
                f"sender={payload.sender_id};{emotion} text={payload.text}",
                (),
                salience=0.8,
            )
        if isinstance(payload, SemanticVisualScenePayload):
            entities = ", ".join(
                f"{entity.label}<{entity.semantic_id}>" for entity in payload.entities
            )
            return self._reliable(
                event,
                PhysicalModality.VISION,
                f"zone={payload.zone_id}; visible={entities or 'none'}",
                (),
                salience=0.6,
            )
        if isinstance(payload, SemanticActionResultPayload):
            reason = f"; reason={payload.reason}" if payload.reason else ""
            return self._reliable(
                event,
                PhysicalModality.PROPRIOCEPTION,
                (
                    f"action={payload.target}; anchor={payload.resolved_anchor_id}; "
                    f"status={payload.status}{reason}"
                ),
                (),
                salience=0.7,
            )
        if isinstance(payload, NestFactNoticePayload):
            details = [
                f"fact_type={payload.fact_type}",
                f"fact_id={payload.fact_id}",
                f"summary={payload.summary}",
            ]
            for key in ("zone_id", "active", "lights_on", "quiet_mode", "phase"):
                value = getattr(payload, key)
                if value is not None:
                    rendered = str(value).lower() if isinstance(value, bool) else value
                    details.append(f"{key}={rendered}")
            return self._reliable(
                event,
                PhysicalModality.ENVIRONMENT,
                "; ".join(details),
                (),
                salience=0.6,
            )
        if isinstance(payload, UtteranceFinal):
            return self._reliable(
                event,
                PhysicalModality.UTTERANCE,
                payload.text,
                (payload.audio,) if payload.audio is not None else (),
                salience=0.8,
            )
        if isinstance(payload, VisionChange):
            return self._reliable(
                event,
                PhysicalModality.VISION,
                payload.description,
                (payload.media,) if payload.media is not None else (),
                salience=0.6,
            )
        if isinstance(payload, TactileImpact):
            force_newtons = payload.force_newtons or 0.0
            content = f"location={payload.location}; force_newtons={force_newtons:g}"
            return self._reliable(
                event,
                PhysicalModality.TOUCH,
                content,
                (),
                salience=min(1.0, 0.4 + force_newtons / 30.0),
            )
        if isinstance(payload, VisionSample):
            return (self._media(event, payload),)
        if isinstance(payload, ProprioceptionSample):
            return self._proprioception(event, payload)
        if isinstance(payload, EnvironmentSample):
            return self._environment(event, payload)
        raise UnsupportedSensorPayloadError(type(payload).__name__)

    def _reliable(
        self,
        event: BodySensorEvent,
        modality: PhysicalModality,
        content: str,
        media: tuple,
        *,
        salience: float,
    ) -> Tuple[PerceptionWrite, ...]:
        filter_input = {
            "has_new_message": True,
            "user_message": content,
            "message_id": str(event.event_id),
        }
        if media:
            filter_input["images"] = tuple(item.uri for item in media)
        if not self._signal_filter.filter_noise(filter_input):
            return ()
        return (
            PerceptionEvent(
                meta=self._meta(event, event.event_id),
                payload=PhysicalPayload(
                    type="physical",
                    body_id=str(event.body_id),
                    body_generation=event.body_generation,
                    modality=modality,
                    content=content,
                    media=media,
                ),
                salience=salience,
            ),
        )

    def _media(
        self,
        event: BodySensorEvent,
        payload: VisionSample,
    ) -> PerceptionMediaSample:
        stream_id = f"body:{event.body_id}:vision"
        ordinal = self._media_ordinals.get(stream_id, 0) + 1
        self._media_ordinals[stream_id] = ordinal
        self._media_filter.filter_noise({"images": (payload.media.uri,)})
        return PerceptionMediaSample(
            meta=self._meta(event, event.event_id),
            body_id=str(event.body_id),
            body_generation=event.body_generation,
            stream_id=stream_id,
            ordinal=ordinal,
            captured_at=event.occurred_at,
            media=payload.media,
        )

    def _proprioception(
        self,
        event: BodySensorEvent,
        payload: ProprioceptionSample,
    ) -> Tuple[PerceptionWrite, ...]:
        prefix = f"body:{event.body_id}:proprioception"
        values: Tuple[Tuple[str, bool | str], ...] = (
            ("posture", payload.posture),
            ("arrived", payload.arrived),
        )
        if payload.target is not None:
            values += (("target", payload.target),)
        return tuple(
            self._state(event, f"{prefix}:{name}", value) for name, value in values
        )

    def _environment(
        self,
        event: BodySensorEvent,
        payload: EnvironmentSample,
    ) -> Tuple[PerceptionWrite, ...]:
        values: Tuple[Tuple[str, float], ...] = ()
        if payload.temperature_celsius is not None:
            values += (("temperature_celsius", payload.temperature_celsius),)
        if payload.humidity_ratio is not None:
            values += (("humidity_ratio", payload.humidity_ratio),)
        if payload.illuminance_lux is not None:
            values += (("illuminance_lux", payload.illuminance_lux),)
        if not values:
            return ()
        prefix = f"body:{event.body_id}:environment"
        return tuple(
            self._state(event, f"{prefix}:{name}", value)
            for name, value in values
            if self._state_values.get(f"{prefix}:{name}") != value
        )

    def _state(
        self,
        event: BodySensorEvent,
        state_key: str,
        value: bool | float | str,
    ) -> PerceptionStateUpdate:
        revision = self._state_revisions.get(state_key, 0) + 1
        self._state_revisions[state_key] = revision
        self._state_values[state_key] = value
        suffix = state_key.rsplit(":", 1)[-1]
        return PerceptionStateUpdate(
            meta=self._meta(event, EventId(f"{event.event_id}:{suffix}")),
            body_id=str(event.body_id),
            body_generation=event.body_generation,
            state_key=state_key,
            revision=revision,
            value=value,
        )

    def _meta(
        self,
        event: BodySensorEvent,
        event_id: EventId,
    ) -> MessageMeta:
        return MessageMeta(
            event_id=event_id,
            elfie_id=self._elfie_id,
            source=event.source,
            occurred_at=event.occurred_at,
            received_at=event.received_at,
            trace_id=TraceId(f"body:{event.event_id}"),
            causation_id=event.cause_id,
            priority=Priority.NORMAL,
        )


__all__ = ("BodyPerceptionNormalizer", "UnsupportedSensorPayloadError")
