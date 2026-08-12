"""Turn construction helpers invoked only by the Brain owner thread."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Tuple
from uuid import uuid4

from elfie.brain.context_builder import ThalamusContextBuilder
from elfie.brain.coordinator_ports import BrainContextSource
from elfie.brain.cortical_worker import CorticalTask
from elfie.brain.decision_decoder import DecisionDecodeSeed
from elfie.brain.decision_types import CancelPolicy, DecisionPlan, NoOpIntent
from elfie.brain.emotion.emotion_system import EmotionSystem
from elfie.brain.energy.energy import HypothalamusEnergy
from elfie.brain.limbic_appraiser import LimbicAppraiser
from elfie.brain.model_context_compiler import ModelContextCompiler, ModelTokenBudget
from elfie.brain.perception_types import (
    InternalPayload,
    InternalSignal,
    PerceptionEvent,
    SocialPayload,
    TurnFrame,
)
from elfie.brain.runtime_port import JsonSchemaDocument, ModelGenerationRequest
from elfie.message_types import (
    ActorId,
    ActorRef,
    ElfieId,
    EventId,
    IntentId,
    MessageMeta,
    PlanId,
    Priority,
    TraceId,
    TurnId,
)


class CoordinatorTurnFactory:
    """Build turns synchronously under Coordinator single-writer ownership."""

    def __init__(
        self,
        *,
        elfie_id: ElfieId,
        emotion: EmotionSystem,
        homeostasis: HypothalamusEnergy,
        appraiser: LimbicAppraiser,
        context_source: BrainContextSource,
        hard_timeout_seconds: float,
        allowed_tools: Tuple[str, ...] = (),
    ) -> None:
        self._elfie_id = elfie_id
        self._emotion = emotion
        self._homeostasis = homeostasis
        self._appraiser = appraiser
        self._context_source = context_source
        self._hard_timeout = hard_timeout_seconds
        self._allowed_tools = allowed_tools
        self._context_builder = ThalamusContextBuilder()
        self._compiler = ModelContextCompiler()

    def build_task(
        self,
        frame: TurnFrame,
        turn_id: TurnId,
        timestamp: float,
    ) -> CorticalTask:
        """Apply limbic inputs, seal snapshots, and compile one model request."""
        captured_at = datetime.fromtimestamp(timestamp, timezone.utc)
        for event in frame.events:
            stimulus = self._appraiser.appraise(event)
            if stimulus is not None:
                self._emotion.apply_stimulus(stimulus)
        emotion = self._emotion.snapshot(timestamp)
        homeostasis = self._homeostasis.snapshot(timestamp)
        conversation = self._context_source.conversation(frame, captured_at)
        memory = self._context_source.memory(frame, emotion, captured_at)
        capabilities = self._context_source.capabilities(captured_at)
        context = self._context_builder.assemble(
            frame=frame,
            emotion=emotion,
            homeostasis=homeostasis,
            conversation=conversation,
            memory=memory,
            capabilities=capabilities,
            captured_at=captured_at,
        )
        compiled = self._compiler.compile(
            context, budget=ModelTokenBudget(max_tokens=1024)
        )
        cause_ids = tuple(
            item.meta.event_id
            for item in frame.events + frame.state_updates + frame.media_samples
        )
        reply_channel_id, reply_conversation_id = self._owner_reply_target(frame)
        deadline = captured_at + timedelta(seconds=self._hard_timeout)
        seed = DecisionDecodeSeed(
            turn_id=turn_id,
            frame_id=frame.frame_id,
            context_revision=context.revision,
            capability_revision=capabilities.revision,
            created_at=captured_at,
            deadline=deadline,
            cause_event_ids=cause_ids,
            reply_channel_id=reply_channel_id,
            reply_conversation_id=reply_conversation_id,
        )
        request = ModelGenerationRequest(
            turn_id=seed.turn_id,
            frame_id=seed.frame_id,
            context_revision=seed.context_revision,
            capability_revision=seed.capability_revision,
            created_at=seed.created_at,
            deadline=seed.deadline,
            cause_event_ids=seed.cause_event_ids,
            source_domain=frame.source_domain,
            interaction_scope=frame.interaction_scope,
            response_scope=frame.response_scope,
            system_prompt="\n".join(compiled.policies),
            user_prompt=compiled.model_dump_json(),
            response_schema=JsonSchemaDocument(
                name="DecisionPlan",
                document=DecisionPlan.model_json_schema(),
            ),
            allowed_tools=self._allowed_tools,
        )
        return CorticalTask(
            request=request,
            seed=seed,
            tool_scope_id=self._elfie_id,
        )

    @staticmethod
    def _owner_reply_target(
        frame: TurnFrame,
    ) -> tuple[str | None, str | None]:
        """Return only the channel/conversation proven by an owner event."""
        for event in frame.events:
            payload = event.payload
            if not isinstance(payload, SocialPayload):
                continue
            if payload.sender.source_kind != "owner":
                continue
            return payload.channel_id, payload.conversation_id
        return None, None

    @staticmethod
    def noop_plan(seed: DecisionDecodeSeed, reason: str) -> DecisionPlan:
        """Create a trusted NoOp for timeout closure."""
        return DecisionPlan(
            plan_id=PlanId(f"timeout-{seed.turn_id}"),
            turn_id=seed.turn_id,
            frame_id=seed.frame_id,
            context_revision=seed.context_revision,
            capability_revision=seed.capability_revision,
            created_at=seed.created_at,
            deadline=seed.deadline,
            cause_event_ids=seed.cause_event_ids,
            intents=(
                NoOpIntent(
                    type="noop",
                    intent_id=IntentId(f"timeout-intent-{seed.turn_id}"),
                    cause_event_ids=seed.cause_event_ids,
                    dependency_ids=(),
                    deadline=seed.deadline,
                    cancel_policy=CancelPolicy.IF_NOT_STARTED,
                    reason=reason,
                ),
            ),
        )

    @staticmethod
    def autonomous_event(elfie_id: ElfieId, timestamp: float) -> PerceptionEvent:
        """Represent an internal drive as explicit perception, not a clock tick."""
        at = datetime.fromtimestamp(timestamp, timezone.utc)
        event_id = EventId(f"autonomous_{uuid4().hex}")
        return PerceptionEvent(
            meta=MessageMeta(
                event_id=event_id,
                elfie_id=elfie_id,
                source=ActorRef(
                    actor_id=ActorId(f"{elfie_id}:brain"),
                    source_kind="internal",
                ),
                occurred_at=at,
                received_at=at,
                trace_id=TraceId(f"autonomous:{event_id}"),
                priority=Priority.NORMAL,
            ),
            payload=InternalPayload(
                type="internal",
                signal=InternalSignal.AUTONOMOUS_DEADLINE,
                detail="autonomous cognitive deadline reached",
            ),
            salience=0.5,
        )


__all__ = ("CoordinatorTurnFactory",)
