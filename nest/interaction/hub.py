"""巢内广播和已发生的语音事件。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Literal, TypedDict, cast
from uuid import uuid4

from nest.events import (
    HeardUtterance,
    NestEventEnvelope,
    SemanticActionResult,
    SemanticVisualEntity,
    SemanticVisualScene,
)
from nest.state.store import NestState


class SpeechInput(TypedDict, total=False):
    event_id: str
    sender_id: str
    text: str
    emotion: str


class VisualInput(TypedDict):
    event_id: str
    observer_id: str
    description: str
    occurred_at: datetime


SemanticActionStatus = Literal["completed", "failed", "cancelled", "timed_out"]


class NestEventBus:
    """Emit typed Nest-owned events without parsing Elfie cognition."""

    def __init__(self, state: NestState) -> None:
        self._state = state
        self._sensory: Dict[str, List[SpeechInput]] = {}
        self._visual_sensory: Dict[str, List[VisualInput]] = {}
        self._pending_speech: Dict[str, tuple[str, str, str | None]] = {}
        self._pending_visual: Dict[str, tuple[str, int]] = {}
        self._pending_actions: Dict[str, tuple[str, str, str]] = {}
        self._event_outbox: List[NestEventEnvelope] = []
        self._emitted_event_ids: set[str] = set()

    def register_resident(self, elfie_id: str) -> None:
        self._sensory.setdefault(elfie_id, [])
        self._visual_sensory.setdefault(elfie_id, [])

    def remove_resident(self, elfie_id: str) -> None:
        self._sensory.pop(elfie_id, None)
        self._visual_sensory.pop(elfie_id, None)
        self._pending_speech = {
            command_id: pending
            for command_id, pending in self._pending_speech.items()
            if pending[0] != elfie_id
        }
        self._pending_visual = {
            observation_id: pending
            for observation_id, pending in self._pending_visual.items()
            if pending[0] != elfie_id
        }
        self._pending_actions = {
            command_id: pending
            for command_id, pending in self._pending_actions.items()
            if pending[0] != elfie_id
        }

    def queue_semantic_action(
        self,
        *,
        command_id: str,
        actor_id: str,
        target: str,
        resolved_anchor_id: str,
    ) -> bool:
        if (
            not command_id.strip()
            or actor_id not in self._state.residents
            or not target.strip()
            or not resolved_anchor_id.strip()
        ):
            return False
        self._pending_actions[command_id] = (
            actor_id,
            target,
            resolved_anchor_id,
        )
        return True

    def cancel_semantic_action(self, command_id: str) -> None:
        self._pending_actions.pop(command_id, None)

    def complete_semantic_action(
        self,
        *,
        command_id: str,
        status: str,
        reason: str | None,
        event_id: str,
        runtime_id: str | None = None,
        runtime_generation: int | None = None,
        world_revision: int | None = None,
        occurred_at: datetime | None = None,
    ) -> SemanticActionResult | None:
        pending = self._pending_actions.pop(command_id, None)
        if pending is None:
            return None
        actor_id, target, resolved_anchor_id = pending
        normalized_status: SemanticActionStatus = (
            cast(SemanticActionStatus, status)
            if status in {"completed", "failed", "cancelled", "timed_out"}
            else "failed"
        )
        result = SemanticActionResult(
            command_id=command_id,
            actor_id=actor_id,
            target=target,
            resolved_anchor_id=resolved_anchor_id,
            status=normalized_status,
            reason=reason,
        )
        targeted_event_id = f"{event_id}:{actor_id}"
        if targeted_event_id in self._emitted_event_ids:
            return result
        self._emitted_event_ids.add(targeted_event_id)
        self._event_outbox.append(
            NestEventEnvelope(
                event_id=targeted_event_id,
                owner="nest.action",
                cause_id=command_id,
                target_ids=(actor_id,),
                occurred_at=occurred_at or datetime.now(timezone.utc),
                payload=result,
                runtime_id=runtime_id,
                runtime_generation=runtime_generation,
                world_revision=world_revision,
            )
        )
        return result

    def queue_visual_observation(
        self,
        *,
        observation_id: str,
        observer_id: str,
        max_results: int = 32,
    ) -> bool:
        """Hold one short-lived semantic observation correlation."""
        if (
            not observation_id.strip()
            or observer_id not in self._state.residents
            or max_results < 1
            or max_results > 64
        ):
            return False
        self._pending_visual[observation_id] = (observer_id, max_results)
        return True

    def cancel_visual_observation(self, observation_id: str) -> None:
        self._pending_visual.pop(observation_id, None)

    def complete_visual_observation(
        self,
        *,
        observation_id: str,
        zone_id: str,
        visible_semantic_ids: tuple[str, ...],
        event_id: str,
        runtime_id: str | None = None,
        runtime_generation: int | None = None,
        world_revision: int | None = None,
        occurred_at: datetime | None = None,
    ) -> SemanticVisualScene | None:
        pending = self._pending_visual.pop(observation_id, None)
        if pending is None:
            return None
        observer_id, max_results = pending
        entities: list[SemanticVisualEntity] = []
        seen: set[str] = set()
        for semantic_id in visible_semantic_ids:
            if len(entities) >= max_results or semantic_id in seen:
                continue
            entity = self._resolve_visual_entity(
                semantic_id,
                observer_id=observer_id,
                zone_id=zone_id,
            )
            if entity is None:
                continue
            seen.add(semantic_id)
            entities.append(entity)
        scene = SemanticVisualScene(
            observation_id=observation_id,
            observer_id=observer_id,
            zone_id=zone_id,
            entities=tuple(entities),
        )
        targeted_event_id = f"{event_id}:{observer_id}"
        if targeted_event_id in self._emitted_event_ids:
            return scene
        self._emitted_event_ids.add(targeted_event_id)
        self._event_outbox.append(
            NestEventEnvelope(
                event_id=targeted_event_id,
                owner="nest.interaction",
                cause_id=observation_id,
                target_ids=(observer_id,),
                occurred_at=occurred_at or datetime.now(timezone.utc),
                payload=scene,
                runtime_id=runtime_id,
                runtime_generation=runtime_generation,
                world_revision=world_revision,
            )
        )
        labels = ", ".join(
            f"{entity.label}<{entity.semantic_id}>" for entity in entities
        )
        self._visual_sensory.setdefault(observer_id, []).append(
            {
                "event_id": targeted_event_id,
                "observer_id": observer_id,
                "description": (
                    f"区域 {zone_id} 可见语义对象: {labels}"
                    if labels
                    else f"区域 {zone_id} 没有可见语义对象"
                ),
                "occurred_at": occurred_at or datetime.now(timezone.utc),
            }
        )
        return scene

    def _resolve_visual_entity(
        self,
        semantic_id: str,
        *,
        observer_id: str,
        zone_id: str,
    ) -> SemanticVisualEntity | None:
        kind, separator, value = semantic_id.partition("/")
        if not separator or not value:
            return None
        if kind == "actor":
            if value == observer_id:
                return None
            resident = self._state.residents.get(value)
            if resident is None or not resident.active or resident.posture == "away":
                return None
            mirror = self._state.runtime_mirrors.get(value)
            if mirror is not None and mirror.current_zone_id not in {None, zone_id}:
                return None
            return SemanticVisualEntity(
                semantic_id=semantic_id,
                kind="actor",
                zone_id=zone_id,
                label=value,
            )
        catalog = self._state.world_catalog
        if catalog is None:
            return None
        if kind == "anchor":
            for zone in catalog.zones:
                for anchor in zone.anchors:
                    if (
                        anchor.anchor_id == value
                        and anchor.active
                        and zone.zone_id == zone_id
                    ):
                        return SemanticVisualEntity(
                            semantic_id=semantic_id,
                            kind="anchor",
                            zone_id=zone.zone_id,
                            label=anchor.label,
                        )
            return None
        if kind == "facility":
            for facility in catalog.facilities:
                if (
                    facility.facility_id == value
                    and facility.active
                    and facility.zone_id == zone_id
                ):
                    return SemanticVisualEntity(
                        semantic_id=semantic_id,
                        kind="facility",
                        zone_id=facility.zone_id,
                        label=facility.label,
                        capabilities=facility.capabilities,
                    )
        return None

    def queue_speech(
        self,
        *,
        command_id: str,
        sender_id: str,
        text: str,
        emotion: str | None = None,
    ) -> bool:
        """Hold speech content until Runtime returns the physical audience."""
        state = self._state.residents.get(sender_id)
        if not command_id.strip() or not text.strip() or state is None:
            return False
        self._pending_speech[command_id] = (sender_id, text, emotion)
        return True

    def cancel_speech(self, command_id: str) -> None:
        self._pending_speech.pop(command_id, None)

    def complete_speech_reach(
        self,
        *,
        command_id: str,
        audience_ids: tuple[str, ...],
        event_id: str,
        runtime_id: str | None = None,
        runtime_generation: int | None = None,
        world_revision: int | None = None,
        occurred_at: datetime | None = None,
    ) -> tuple[str, str | None] | None:
        pending = self._pending_speech.pop(command_id, None)
        if pending is None:
            return None
        sender_id, text, emotion = pending
        for elfie_id in dict.fromkeys(audience_ids):
            state = self._state.residents.get(elfie_id)
            if (
                elfie_id == sender_id
                or state is None
                or not state.active
                or state.posture == "away"
            ):
                continue
            targeted_event_id = f"{event_id}:{elfie_id}"
            if targeted_event_id in self._emitted_event_ids:
                continue
            self._emitted_event_ids.add(targeted_event_id)
            payload = HeardUtterance(
                utterance_id=event_id,
                sender_id=sender_id,
                text=text,
                emotion=emotion,
            )
            self._event_outbox.append(
                NestEventEnvelope(
                    event_id=targeted_event_id,
                    owner="nest.interaction",
                    cause_id=command_id,
                    target_ids=(elfie_id,),
                    occurred_at=occurred_at or datetime.now(timezone.utc),
                    payload=payload,
                    runtime_id=runtime_id,
                    runtime_generation=runtime_generation,
                    world_revision=world_revision,
                )
            )
            event: SpeechInput = {
                "event_id": targeted_event_id,
                "sender_id": sender_id,
                "text": text,
            }
            if emotion:
                event["emotion"] = emotion
            self._sensory.setdefault(elfie_id, []).append(event)
        return text, emotion

    def drain_event_outbox(self) -> tuple[NestEventEnvelope, ...]:
        events = tuple(self._event_outbox)
        self._event_outbox.clear()
        return events

    def broadcast_speech(self, sender_id: str, text: str) -> None:
        """Compatibility alias for a Nest-wide system announcement."""
        self.broadcast_system(text, sender_id=sender_id)

    def broadcast_system(self, text: str, *, sender_id: str = "nest") -> None:
        if not text:
            return
        event = SpeechInput(
            event_id=f"nest-system:{uuid4().hex}",
            sender_id=sender_id,
            text=text,
        )
        for elfie_id, state in self._state.residents.items():
            if elfie_id != sender_id and state.active and state.posture != "away":
                self._sensory.setdefault(elfie_id, []).append(event)

    def deliver_speech(
        self,
        *,
        sender_id: str,
        text: str,
        audience_ids: tuple[str, ...],
        event_id: str,
    ) -> None:
        if not text:
            return
        event = SpeechInput(
            event_id=event_id,
            sender_id=sender_id,
            text=text,
        )
        for elfie_id in audience_ids:
            state = self._state.residents.get(elfie_id)
            if (
                elfie_id == sender_id
                or state is None
                or not state.active
                or state.posture == "away"
            ):
                continue
            self._sensory.setdefault(elfie_id, []).append(event)

    def consume_sensory(self, elfie_id: str) -> str:
        events = self.consume_speech_events(elfie_id)
        return "；".join(
            f'[{event["sender_id"]} 说道]: "{event["text"]}"' for event in events
        )

    def consume_speech_events(self, elfie_id: str) -> tuple[SpeechInput, ...]:
        events = tuple(self._sensory.get(elfie_id, ()))
        self._sensory[elfie_id] = []
        return events

    def consume_visual_events(self, elfie_id: str) -> tuple[VisualInput, ...]:
        events = tuple(self._visual_sensory.get(elfie_id, ()))
        self._visual_sensory[elfie_id] = []
        return events
