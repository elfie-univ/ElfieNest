"""巢内广播和已发生的语音事件。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Literal, cast
from uuid import uuid4

from nest.events import (
    HeardUtterance,
    NestDomainEvent,
    NestEventEnvelope,
    NestFactNotice,
    SemanticActionResult,
    SemanticVisualEntity,
    SemanticVisualScene,
)
from nest.living_rules.living import LivingRulesState
from nest.space_facilities.catalog import SpaceFacilitiesState

SemanticActionStatus = Literal["completed", "failed", "cancelled", "timed_out"]


class NestEventBus:
    """Emit typed Nest-owned events without parsing Elfie cognition."""

    def __init__(
        self,
        living_rules: LivingRulesState,
        space: SpaceFacilitiesState,
    ) -> None:
        self._living_rules = living_rules
        self._space = space
        self._pending_speech: Dict[str, tuple[str, str, str | None]] = {}
        self._pending_visual: Dict[str, tuple[str, int]] = {}
        self._pending_actions: Dict[str, tuple[str, str, str, str, int]] = {}
        self._event_outbox: List[NestEventEnvelope] = []
        self._emitted_event_ids: set[str] = set()

    def remove_resident(self, elfie_id: str) -> None:
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
            if pending[1] != elfie_id
        }

    def queue_semantic_action(
        self,
        *,
        command_id: str,
        intent_id: str,
        actor_id: str,
        body_generation: int,
        target: str,
        resolved_anchor_id: str,
    ) -> bool:
        if (
            not command_id.strip()
            or not intent_id.strip()
            or not self._living_rules.is_present(actor_id)
            or isinstance(body_generation, bool)
            or body_generation < 1
            or not target.strip()
            or not resolved_anchor_id.strip()
        ):
            return False
        self._pending_actions[command_id] = (
            intent_id,
            actor_id,
            target,
            resolved_anchor_id,
            body_generation,
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
        intent_id, actor_id, target, resolved_anchor_id, body_generation = pending
        normalized_status: SemanticActionStatus = (
            cast(SemanticActionStatus, status)
            if status in {"completed", "failed", "cancelled", "timed_out"}
            else "failed"
        )
        result = SemanticActionResult(
            command_id=command_id,
            intent_id=intent_id,
            actor_id=actor_id,
            body_generation=body_generation,
            target=target,
            resolved_anchor_id=resolved_anchor_id,
            status=normalized_status,
            reason=reason,
        )
        if not self._emit_event(
            event_id=event_id,
            owner="nest.action",
            cause_id=command_id,
            target_ids=(actor_id,),
            payload=result,
            runtime_id=runtime_id,
            runtime_generation=runtime_generation,
            world_revision=world_revision,
            occurred_at=occurred_at,
        ):
            return result
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
            or not self._living_rules.is_present(observer_id)
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
        if not self._emit_event(
            event_id=event_id,
            owner="nest.elfie_interaction",
            cause_id=observation_id,
            target_ids=(observer_id,),
            payload=scene,
            runtime_id=runtime_id,
            runtime_generation=runtime_generation,
            world_revision=world_revision,
            occurred_at=occurred_at,
        ):
            return scene
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
            if not self._living_rules.is_present(value):
                return None
            mirror = self._living_rules.runtime_mirrors.get(value)
            if mirror is not None and mirror.current_zone_id not in {None, zone_id}:
                return None
            return SemanticVisualEntity(
                semantic_id=semantic_id,
                kind="actor",
                zone_id=zone_id,
                label=value,
            )
        catalog = self._space.world_catalog
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
        if (
            not command_id.strip()
            or not text.strip()
            or not self._living_rules.is_present(sender_id)
        ):
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
        target_ids = self._living_rules.eligible_event_audience(
            audience_ids,
            sender_id=sender_id,
        )
        if not target_ids:
            return text, emotion
        payload = HeardUtterance(
            utterance_id=event_id,
            sender_id=sender_id,
            text=text,
            emotion=emotion,
        )
        self._emit_event(
            event_id=event_id,
            owner="nest.elfie_interaction",
            cause_id=command_id,
            target_ids=target_ids,
            payload=payload,
            runtime_id=runtime_id,
            runtime_generation=runtime_generation,
            world_revision=world_revision,
            occurred_at=occurred_at,
        )
        return text, emotion

    def _emit_event(
        self,
        *,
        event_id: str,
        owner: str,
        cause_id: str,
        target_ids: tuple[str, ...],
        payload: NestDomainEvent,
        runtime_id: str | None,
        runtime_generation: int | None,
        world_revision: int | None,
        occurred_at: datetime | None,
    ) -> bool:
        """Append one deduplicated typed event for the single production consumer."""
        if not target_ids or event_id in self._emitted_event_ids:
            return False
        self._emitted_event_ids.add(event_id)
        self._event_outbox.append(
            NestEventEnvelope(
                event_id=event_id,
                owner=owner,
                cause_id=cause_id,
                target_ids=target_ids,
                occurred_at=occurred_at or datetime.now(timezone.utc),
                payload=payload,
                runtime_id=runtime_id,
                runtime_generation=runtime_generation,
                world_revision=world_revision,
            )
        )
        return True

    def drain_event_outbox(self) -> tuple[NestEventEnvelope, ...]:
        events = tuple(self._event_outbox)
        self._event_outbox.clear()
        return events

    def requeue_event_outbox(self, events: tuple[NestEventEnvelope, ...]) -> None:
        """Put failed target deliveries back without changing event identity."""
        if events:
            self._event_outbox[0:0] = list(events)

    def invalidate_runtime_state(self) -> None:
        """Drop short-lived Runtime correlations and facts across authority change."""
        self._pending_speech.clear()
        self._pending_visual.clear()
        self._pending_actions.clear()
        self._event_outbox.clear()
        self._emitted_event_ids.clear()

    def broadcast_system(self, text: str, *, sender_id: str = "nest") -> None:
        """Emit one typed broadcast event for all currently eligible residents."""
        if not text:
            return
        target_ids = self._living_rules.eligible_event_audience(
            sender_id=sender_id,
        )
        event_id = f"nest-system:{uuid4().hex}"
        self._emit_event(
            event_id=event_id,
            owner="nest.elfie_interaction",
            cause_id=event_id,
            target_ids=target_ids,
            payload=HeardUtterance(
                utterance_id=event_id,
                sender_id=sender_id,
                text=text,
            ),
            runtime_id=None,
            runtime_generation=None,
            world_revision=None,
            occurred_at=None,
        )

    def emit_fact_notice(
        self,
        *,
        fact_type: str,
        fact_id: str,
        summary: str,
        cause_id: str | None = None,
        target_ids: tuple[str, ...] | None = None,
        zone_id: str | None = None,
        active: bool | None = None,
        lights_on: bool | None = None,
        quiet_mode: bool | None = None,
        phase: str | None = None,
    ) -> bool:
        """Emit one owner-created semantic fact through the common outbox."""
        if not fact_id.strip() or not summary.strip():
            return False
        eligible_targets = self._living_rules.eligible_event_audience(
            target_ids,
        )
        if not eligible_targets:
            return False
        if fact_type not in {
            "facility_state_changed",
            "home_assignment_changed",
            "environment_phase_changed",
            "environment_desired_changed",
            "environment_rule_changed",
        }:
            return False
        owner_by_fact_type = {
            "facility_state_changed": "nest.space_facilities",
            "home_assignment_changed": "nest.living_rules",
            "environment_phase_changed": "nest.time_environment",
            "environment_desired_changed": "nest.time_environment",
            "environment_rule_changed": "nest.time_environment",
        }
        event_id = f"nest-fact:{uuid4().hex}"
        return self._emit_event(
            event_id=event_id,
            owner=owner_by_fact_type[fact_type],
            cause_id=cause_id or fact_id,
            target_ids=eligible_targets,
            payload=NestFactNotice(
                fact_type=cast(
                    Literal[
                        "facility_state_changed",
                        "home_assignment_changed",
                        "environment_phase_changed",
                        "environment_desired_changed",
                        "environment_rule_changed",
                    ],
                    fact_type,
                ),
                fact_id=fact_id,
                summary=summary,
                zone_id=zone_id,
                active=active,
                lights_on=lights_on,
                quiet_mode=quiet_mode,
                phase=phase,
            ),
            runtime_id=None,
            runtime_generation=None,
            world_revision=None,
            occurred_at=None,
        )
