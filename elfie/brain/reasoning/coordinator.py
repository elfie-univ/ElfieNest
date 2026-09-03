"""Single-owner Brain loop with a non-blocking reasoning worker."""

from __future__ import annotations

import logging
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import replace
from datetime import datetime, timezone
from threading import Event
from typing import Callable, Optional, Tuple
from uuid import uuid4

from elfie.brain.consolidation.system import consolidation_candidate_to_perception
from elfie.brain.emotion.appraiser import BrainClockPulse, EmotionAppraiser
from elfie.brain.emotion.contracts import (
    AffectDirection,
    AffectiveAppraisal,
    ChannelEffect,
)
from elfie.brain.emotion.emotion_system import EmotionSystem, EmotionTurnSnapshot
from elfie.brain.emotion.stimulus import EmotionStimulusEvent, StimulusSource
from elfie.brain.energy.energy import EnergySystem
from elfie.brain.journal import BrainJournal
from elfie.brain.motivation.system import recovery_candidate_to_perception
from elfie.brain.reasoning.coordinator_completion import (
    CompletionDisposition,
    CoordinatorCompletionHandler,
)
from elfie.brain.reasoning.coordinator_outcomes import (
    reasoning_failure_outcome,
    reasoning_stale_outcome,
    reasoning_timeout_outcome,
)
from elfie.brain.reasoning.coordinator_ports import BrainContextSource, TurnDecisionSink
from elfie.brain.reasoning.coordinator_runtime import (
    CoordinatorRuntime,
    TurnOutcomeBuffer,
)
from elfie.brain.reasoning.coordinator_turn import ReasoningRunController
from elfie.brain.reasoning.coordinator_types import (
    BarrierControl,
    FrameAffectTxn,
    InFlightTurn,
    PerceptionControl,
    StopControl,
    WorkerDoneControl,
)
from elfie.brain.reasoning.decision_decoder import (
    DecisionDecodeMode,
    DecisionDecodeReport,
    DecisionDecodeResult,
)
from elfie.brain.reasoning.decision_governance import govern_decision
from elfie.brain.reasoning.model_header import ReasoningConstitution
from elfie.brain.reasoning.run import (
    CognitiveStep,
    CognitiveStepKind,
    ReasoningRunResult,
    ReasoningStatus,
)
from elfie.brain.reasoning.settlement import TurnSettlementPort
from elfie.brain.reasoning.turn_outcome import TerminalStatus, TurnOutcome
from elfie.brain.reasoning.worker import ReasoningExecutionPort, ReasoningTurnResult
from elfie.brain.workspace.contracts import (
    IngestDisposition,
    PhysicalModality,
    PhysicalPayload,
)
from elfie.brain.workspace.system import EventWorkspace
from elfie.brain.workspace.trigger_policy import TurnTriggerPolicy
from elfie.brain.workspace.types import FrameLifecycleError
from elfie.message_types import ElfieId, EventId, TurnId

diagnostic_logger = logging.getLogger("elfienest.diagnostics.brain")


class BrainCoordinator:
    """Own Brain mutation, frame claims, and one in-flight reasoning turn."""

    def __init__(
        self,
        *,
        elfie_id: ElfieId,
        workspace: EventWorkspace,
        emotion: EmotionSystem,
        homeostasis: EnergySystem,
        appraiser: EmotionAppraiser,
        context_source: BrainContextSource,
        constitution: ReasoningConstitution,
        reasoning_worker: ReasoningExecutionPort,
        plan_sink: TurnDecisionSink,
        settlement: TurnSettlementPort,
        initial_timestamp: float,
        next_autonomous_at: Optional[float] = None,
        hard_timeout_seconds: float = 45.0,
        trigger_policy: Optional[TurnTriggerPolicy] = None,
        allowed_tools: Tuple[str, ...] = (),
        motivation_blocked: Optional[Callable[[], bool]] = None,
        consolidation_blocked: Optional[Callable[[], bool]] = None,
        journal: BrainJournal | None = None,
        on_outcome: Callable[[TurnOutcome], None] | None = None,
        on_state_change: Callable[[], None] | None = None,
        reasoning_retention: int = 256,
    ) -> None:
        if reasoning_retention <= 0:
            raise ValueError("reasoning_retention must be positive")
        self._elfie_id = elfie_id
        self._workspace = workspace
        self._emotion = emotion
        self._homeostasis = homeostasis
        self._appraiser = appraiser
        self._context_source = context_source
        self._worker = reasoning_worker
        self._plan_sink = plan_sink
        self._settlement = settlement
        self._timestamp = initial_timestamp
        self._next_autonomous_at = next_autonomous_at
        self._hard_timeout = hard_timeout_seconds
        self._policy = trigger_policy or TurnTriggerPolicy()
        self._motivation_blocked = motivation_blocked or (lambda: False)
        self._consolidation_blocked = consolidation_blocked or (lambda: False)
        self._journal = journal
        self._on_state_change = on_state_change
        # A low-salience drive candidate still deserves one Brain turn.  Keep
        # this admission bit separate from event salience so Motivation cannot
        # accidentally be starved by the normal input thresholds.
        self._motivation_due = False
        self._consolidation_due = False
        self._turn_factory = ReasoningRunController(
            elfie_id=elfie_id,
            homeostasis=homeostasis,
            context_source=context_source,
            hard_timeout_seconds=hard_timeout_seconds,
            allowed_tools=allowed_tools,
            constitution=constitution,
        )
        self._runtime = CoordinatorRuntime(elfie_id, reasoning_worker)
        self._inflight: Optional[InFlightTurn] = None
        self._affect_txn: Optional[FrameAffectTxn] = None
        self._reasoning: OrderedDict[TurnId, ReasoningRunResult] = OrderedDict()
        self._reasoning_retention = reasoning_retention
        self._evicted_reasoning_count = 0
        self._outcomes = TurnOutcomeBuffer(
            on_record=self._outcome_recorder(journal, on_outcome)
        )
        self._completion = CoordinatorCompletionHandler(
            workspace=workspace,
            plan_sink=plan_sink,
            outcomes=self._outcomes,
            settlement=settlement,
            context_source=context_source,
        )

    def start(self) -> None:
        """Start worker and owner thread; repeated calls are idempotent."""
        self._runtime.start(self._run)

    def post_clock(self, pulse: BrainClockPulse) -> None:
        self._runtime.post(pulse)

    def notify_perception(self, *, urgent_reason: Optional[str] = None) -> None:
        self._runtime.post(PerceptionControl(urgent_reason))

    def synchronize(self, timeout: float = 1.0) -> None:
        """Wait until all mailbox messages posted before this call are handled."""
        reached = Event()
        self._runtime.post(BarrierControl(reached))
        if not reached.wait(timeout):
            raise TimeoutError("brain coordinator synchronization timed out")

    def stop(self) -> None:
        """Request explicit shutdown once and stop accepting reasoning work."""
        self._runtime.stop()

    def join(self) -> None:
        """Join both owner and reasoning threads; repeated calls are safe."""
        self._runtime.join()

    @property
    def is_alive(self) -> bool:
        return self._runtime.is_alive

    def outcomes(self) -> Tuple[TurnOutcome, ...]:
        return self._outcomes.snapshot()

    def wait_for_outcome(self, timeout: float = 1.0) -> None:
        self._outcomes.wait(timeout)

    def wait_for_outcome_count(self, count: int, *, timeout: float = 1.0) -> None:
        """Wait for a deterministic number of terminal cognitive turns."""
        self._outcomes.wait_for_count(count, timeout)

    def reasoning(self, turn_id: TurnId) -> Optional[ReasoningRunResult]:
        """Return the bounded cognitive trace for a completed worker turn."""
        return self._reasoning.get(turn_id)

    @property
    def evicted_reasoning_count(self) -> int:
        return self._evicted_reasoning_count

    def _remember_reasoning(
        self,
        turn_id: TurnId,
        reasoning: ReasoningRunResult,
    ) -> None:
        self._reasoning[turn_id] = reasoning
        self._reasoning.move_to_end(turn_id)
        while len(self._reasoning) > self._reasoning_retention:
            self._reasoning.popitem(last=False)
            self._evicted_reasoning_count += 1
            count = self._evicted_reasoning_count
            if count & (count - 1) == 0:
                diagnostic_logger.info(
                    "Brain reasoning trace retention evicted its oldest item",
                    extra={
                        "diagnostic_event": "bounded_retention_evict",
                        "component": "brain_reasoning",
                        "capacity": self._reasoning_retention,
                        "dropped_count": count,
                    },
                )

    def _run(self) -> None:
        while True:
            message = self._runtime.receive()
            if isinstance(message, StopControl):
                self._cancel_on_stop()
                return
            if isinstance(message, BrainClockPulse):
                self._handle_clock(message)
            elif isinstance(message, PerceptionControl):
                if message.urgent_reason is not None and self._inflight is not None:
                    self._mark_stale(self._inflight, message.urgent_reason)
                self._maybe_start_turn()
            elif isinstance(message, WorkerDoneControl):
                self._handle_worker_done(message)
            elif isinstance(message, BarrierControl):
                message.reached.set()

    def _handle_clock(self, pulse: BrainClockPulse) -> None:
        if pulse.timestamp < self._timestamp:
            raise ValueError("brain clock cannot move backwards")
        was_sleeping = self._homeostasis.is_sleeping
        self._homeostasis.advance_to(pulse.timestamp)
        if not was_sleeping and self._homeostasis.is_sleeping:
            self._emotion.reset_to_baseline(pulse.timestamp)
        else:
            self._emotion.advance_to(pulse.timestamp)
        self._timestamp = pulse.timestamp
        self._maybe_emit_motivation()
        self._maybe_emit_consolidation()
        if (
            self._inflight is not None
            and self._inflight.terminal_status is None
            and pulse.timestamp >= self._inflight.timeout_at
        ):
            self._timeout_turn(self._inflight)
        self._maybe_start_turn()
        if self._on_state_change is not None:
            self._on_state_change()

    @staticmethod
    def _outcome_recorder(
        journal: BrainJournal | None,
        observer: Callable[[TurnOutcome], None] | None,
    ) -> Callable[[TurnOutcome], None] | None:
        if journal is None and observer is None:
            return None

        def record(outcome: TurnOutcome) -> None:
            if journal is not None:
                journal.record_outcome(outcome)
            if observer is not None:
                observer(outcome)

        return record

    def _maybe_emit_motivation(self) -> None:
        evaluator = getattr(self._context_source, "evaluate_motivation", None)
        if evaluator is None:
            return
        now = datetime.fromtimestamp(self._timestamp, timezone.utc)
        candidate = evaluator(
            energy=self._homeostasis.energy,
            fatigue=self._homeostasis.fatigue,
            sleeping=self._homeostasis.is_sleeping,
            now=now,
            blocked=self._inflight is not None or self._motivation_blocked(),
        )
        if candidate is not None:
            ingest = self._workspace.publish(
                recovery_candidate_to_perception(candidate, elfie_id=self._elfie_id)
            )
            self._motivation_due = ingest.disposition is IngestDisposition.ACCEPTED

    def _maybe_emit_consolidation(self) -> None:
        evaluator = getattr(self._context_source, "evaluate_consolidation", None)
        if evaluator is None:
            return
        now = datetime.fromtimestamp(self._timestamp, timezone.utc)
        candidate = evaluator(
            sleeping=self._homeostasis.is_sleeping,
            now=now,
            blocked=self._inflight is not None or self._consolidation_blocked(),
        )
        if candidate is not None:
            ingest = self._workspace.publish(
                consolidation_candidate_to_perception(
                    candidate, elfie_id=self._elfie_id
                )
            )
            self._consolidation_due = ingest.disposition is IngestDisposition.ACCEPTED

    def _prepare_affect_transaction(
        self,
        frame,
    ) -> tuple[FrameAffectTxn, bool]:
        """Calculate this frame's fast affect once, retaining it across replay."""

        existing = self._affect_txn
        if existing is not None:
            if existing.frame_id != frame.frame_id:
                raise RuntimeError("another frame already owns the affect transaction")
            if existing.anchor.lifecycle_epoch != self._emotion.lifecycle_epoch:
                self._rebase_affect_transaction_after_sleep()
                existing = self._affect_txn
                if existing is None:
                    raise RuntimeError("affect transaction disappeared during rebase")
            return existing, False

        self._emotion.advance_to(self._timestamp)
        anchor = self._emotion.capture_turn_state()
        stable = self._emotion.snapshot_from_turn_state(anchor)
        scope_reader = getattr(self._context_source, "emotion_appraisal_scopes", None)
        indirect_scopes = tuple(scope_reader(frame)) if callable(scope_reader) else ()
        stimuli: list[EmotionStimulusEvent] = []
        scopes_by_id = {scope.scope_id: scope for scope in indirect_scopes}
        for event in frame.events:
            stimulus = self._appraiser.appraise(
                event,
                trusted_scopes=indirect_scopes,
            )
            if stimulus is None:
                continue
            for appraisal in stimulus.appraisals:
                current = scopes_by_id.get(appraisal.scope.scope_id)
                if current is not None and current != appraisal.scope:
                    raise RuntimeError("conflicting appraisal scope identity")
                scopes_by_id[appraisal.scope.scope_id] = appraisal.scope
            guidance = self._emotion.guidance_appraisal(
                stimulus.cause_key,
                event_id=event.meta.event_id,
            )
            if guidance is not None:
                stimulus = stimulus.model_copy(
                    update={"appraisals": stimulus.appraisals + (guidance,)}
                )
            stimuli.append(stimulus)
        fast_candidate = self._emotion.candidate_from(
            anchor,
            tuple(stimuli),
            timestamp=self._timestamp,
        )
        return (
            FrameAffectTxn(
                frame_id=frame.frame_id,
                anchor=anchor,
                fast_candidate=fast_candidate,
                stable_snapshot=stable,
                appraisal_scopes=tuple(scopes_by_id.values()),
                fast_stimuli=tuple(stimuli),
            ),
            True,
        )

    def _rebase_affect_transaction_after_sleep(self) -> None:
        """Keep replay identity while invalidating every pre-sleep candidate."""

        if self._affect_txn is None:
            return
        baseline = self._emotion.capture_turn_state()
        snapshot = self._emotion.snapshot_from_turn_state(baseline)
        self._affect_txn = replace(
            self._affect_txn,
            anchor=baseline,
            fast_candidate=baseline,
            stable_snapshot=snapshot,
            fast_stimuli=(),
        )

    def _maybe_start_turn(self) -> None:
        if self._inflight is not None:
            return
        autonomous_due = (
            self._ensure_autonomous_event()
            or self._motivation_due
            or self._consolidation_due
        )
        metrics = self._workspace.metrics()
        now = datetime.fromtimestamp(self._timestamp, timezone.utc)
        decision = self._policy.evaluate(
            metrics,
            now=now,
            autonomous_due=autonomous_due,
        )
        if decision.reason is None or decision.cutoff_seq is None:
            return
        turn_id = TurnId(f"turn_{uuid4().hex}")
        try:
            frame = self._workspace.claim_frame(
                decision.cutoff_seq,
                turn_id=turn_id,
                reason=decision.reason,
                captured_at=now,
            )
        except FrameLifecycleError as error:
            if error.reason != "no perception writes are available":
                raise
            self._motivation_due = False
            self._consolidation_due = False
            return
        try:
            if self._journal is not None:
                self._journal.record_run_started(frame, turn_id)
            requires_model = self._requires_model(frame)
            affect_txn, is_new_affect_txn = self._prepare_affect_transaction(frame)
            conversation = self._turn_factory.observe_conversation(frame, now)
            self._flush_pending_handoffs()
            task = self._turn_factory.build_task(
                frame,
                turn_id,
                self._timestamp,
                emotion=affect_txn.stable_snapshot,
                appraisal_scopes=affect_txn.appraisal_scopes,
                requires_model=requires_model,
                conversation=conversation,
            )
            if requires_model:
                future = self._worker.submit(task)
            else:
                future = Future()
                future.set_result(self._no_model_result(task))
            if is_new_affect_txn:
                if not self._emotion.commit_turn_state(affect_txn.fast_candidate):
                    raise RuntimeError(
                        "emotion lifecycle changed during turn admission"
                    )
                self._affect_txn = affect_txn
        except Exception as error:  # noqa: BLE001 - claim boundary owns failure mapping
            self._homeostasis.release_cognitive_budget(turn_id)
            released = self._workspace.release(
                frame.frame_id,
                turn_id,
                type(error).__name__,
            )
            if getattr(released, "value", None) == "dead_lettered":
                self._affect_txn = None
            self._outcomes.record(
                reasoning_failure_outcome(
                    turn_id=turn_id,
                    frame_id=frame.frame_id,
                    error_code=type(error).__name__,
                )
            )
            return
        if self._motivation_due and any(
            str(event.meta.event_id).startswith("motivation:recovery:")
            for event in frame.events
        ):
            self._motivation_due = False
        if self._consolidation_due and any(
            str(event.meta.event_id).startswith("consolidation:")
            for event in frame.events
        ):
            self._consolidation_due = False
        inflight = InFlightTurn(
            frame=frame,
            task=task,
            future=future,
            timeout_at=self._timestamp + self._hard_timeout,
        )
        self._inflight = inflight
        future.add_done_callback(
            lambda completed: self._runtime.post(WorkerDoneControl(turn_id, completed))
        )

    @staticmethod
    def _requires_model(frame) -> bool:
        """Admit model work for decisions and meaningful embodied outcomes."""

        if any(
            getattr(event.payload, "sender", None) is not None
            and event.payload.sender.source_kind == "owner"
            for event in frame.events
        ):
            return True
        if (
            str(frame.source_domain) == "SourceDomain.INTERNAL"
            or getattr(frame.source_domain, "value", None) == "internal"
        ):
            return True
        return any(
            event.salience >= 0.75
            or (
                isinstance(event.payload, PhysicalPayload)
                and event.payload.modality is PhysicalModality.PROPRIOCEPTION
                and event.payload.content.startswith("action=")
            )
            for event in frame.events
        )

    @staticmethod
    def _no_model_result(task) -> ReasoningTurnResult:
        """Build an auditable local NoOp for routine frames without inference."""

        plan = ReasoningRunController.noop_plan(task.seed, "routine_frame_no_model")
        report = DecisionDecodeReport(
            selected_mode=DecisionDecodeMode.JSON_TEXT,
            validation_errors=(),
            repair_count=0,
            fallback_reason="routine_frame_no_model",
            model_id="none",
            provider="brain",
            token_count=None,
            latency_ms=0.0,
        )
        decode = DecisionDecodeResult(plan=plan, report=report)
        reasoning = ReasoningRunResult(
            status=ReasoningStatus.SAFE_NOOP,
            steps=(
                CognitiveStep(
                    ordinal=1,
                    kind=CognitiveStepKind.VERIFY,
                    status="skipped",
                    summary="routine frame handled without model inference",
                ),
            ),
            model_calls=0,
            tool_calls=0,
            failure_reason="routine_frame_no_model",
            decode=decode,
        )
        return ReasoningTurnResult(decode=decode, reasoning=reasoning)

    def _flush_pending_handoffs(self) -> None:
        """Flush the Context Workspace handoff before Memory Recall is pinned."""
        capture = getattr(self._settlement, "capture_episodes", None)
        if callable(capture):
            self._context_source.flush_pending_handoffs(capture)

    def _handle_worker_done(self, control: WorkerDoneControl) -> None:
        inflight = self._inflight
        if inflight is None or control.turn_id != inflight.task.seed.turn_id:
            return
        slow_candidate: EmotionTurnSnapshot | None = None
        try:
            result = control.future.result()
        except Exception:  # noqa: BLE001 - completion handler owns failure mapping
            self._homeostasis.settle_cognitive_budget(control.turn_id, consumed=0.25)
        else:
            self._remember_reasoning(control.turn_id, result.reasoning)
            consumed = (
                result.reasoning.model_calls
                + (0.5 * result.reasoning.tool_calls)
                + (0.1 * len(result.reasoning.steps))
            )
            self._homeostasis.settle_cognitive_budget(
                control.turn_id,
                consumed=max(0.25, consumed),
            )
            slow_candidate = self._slow_emotion_candidate(inflight, result)
        disposition = self._completion.complete(inflight, control)
        if disposition is CompletionDisposition.COMMITTED:
            if slow_candidate is not None:
                if self._emotion.commit_turn_state(slow_candidate):
                    self._record_slow_guidance(inflight, result)
                else:
                    diagnostic_logger.info(
                        "Ignored emotion feedback from an expired lifecycle epoch",
                        extra={
                            "diagnostic_event": "emotion_feedback_epoch_expired",
                            "turn_id": str(control.turn_id),
                        },
                    )
            self._affect_txn = None
        elif disposition is CompletionDisposition.DEAD_LETTERED:
            self._affect_txn = None
        self._inflight = None
        if self._on_state_change is not None:
            self._on_state_change()
        # Perception controls posted while the worker was running only wake
        # the coordinator once. Re-evaluate the workspace after closing the
        # claim so a queued follow-up message can form its own Turn.
        self._maybe_start_turn()

    def _slow_emotion_candidate(
        self,
        inflight: InFlightTurn,
        result: ReasoningTurnResult,
    ) -> EmotionTurnSnapshot | None:
        """Calculate a reviewed replacement from the pre-fast frame anchor."""

        if inflight.terminal_status is not None:
            return None
        if result.reasoning.status not in {
            ReasoningStatus.COMPLETED,
            ReasoningStatus.SAFE_NOOP,
        }:
            return None
        txn = self._affect_txn
        if txn is None or txn.frame_id != inflight.frame.frame_id:
            return None
        if txn.anchor.lifecycle_epoch != self._emotion.lifecycle_epoch:
            return None
        feedback = result.decode.plan.emotion_feedback
        if feedback is None:
            return None
        try:
            scopes = {scope.scope_id: scope for scope in txn.appraisal_scopes}
            appraisals = []
            for model_appraisal in feedback.appraisals:
                scope = scopes.get(model_appraisal.scope_id)
                if scope is None:
                    raise ValueError("model selected an unknown appraisal scope")
                appraisals.append(
                    AffectiveAppraisal(
                        scope=scope,
                        effects=tuple(
                            ChannelEffect(
                                channel=effect.channel,
                                direction=effect.direction,
                                strength=effect.strength,
                                confidence=effect.confidence,
                            )
                            for effect in model_appraisal.effects
                        ),
                        reason="model-reviewed self appraisal",
                    )
                )
            stimuli: tuple[EmotionStimulusEvent, ...] = ()
            if appraisals:
                stimuli = (
                    EmotionStimulusEvent(
                        event_id=EventId(
                            f"emotion-feedback:{inflight.task.seed.turn_id}"
                        ),
                        appraisals=tuple(appraisals),
                        source=StimulusSource.MODEL,
                        cause_key=f"turn:{inflight.task.seed.turn_id}",
                    ),
                )
            return self._emotion.candidate_from(
                txn.anchor,
                stimuli,
                timestamp=self._timestamp,
            )
        except Exception as error:  # noqa: BLE001 - preserve completed turn
            diagnostic_logger.warning(
                "Model emotion feedback could not reconcile the turn",
                extra={
                    "diagnostic_event": "emotion_feedback_reconcile_failed",
                    "turn_id": str(inflight.task.seed.turn_id),
                    "error": type(error).__name__,
                },
            )
            return None

    def _record_slow_guidance(
        self,
        inflight: InFlightTurn,
        result: ReasoningTurnResult,
    ) -> None:
        """Retain only explicit corrections to a fast rise for the same cause."""

        feedback = result.decode.plan.emotion_feedback
        txn = self._affect_txn
        if feedback is None or txn is None:
            return
        scopes = {scope.scope_id: scope for scope in txn.appraisal_scopes}
        fast_by_event = {stimulus.event_id: stimulus for stimulus in txn.fast_stimuli}
        for model_appraisal in feedback.appraisals:
            scope = scopes.get(model_appraisal.scope_id)
            if scope is None:
                return
            stimulus = fast_by_event.get(scope.cause_event_id)
            if stimulus is None or stimulus.cause_key is None:
                continue
            fast_rises = {
                effect.channel
                for appraisal in stimulus.appraisals
                for effect in appraisal.effects
                if effect.direction is AffectDirection.INCREASE
                and not appraisal.scope.scope_id.startswith("guidance:")
            }
            updates = tuple(
                ChannelEffect(
                    channel=effect.channel,
                    direction=effect.direction,
                    strength=effect.strength,
                    confidence=effect.confidence * scope.relationship_weight,
                )
                for effect in model_appraisal.effects
                if effect.direction is AffectDirection.INCREASE
                or effect.channel in fast_rises
            )
            if updates:
                self._emotion.update_cause_guidance(stimulus.cause_key, updates)

    def _mark_stale(self, inflight: InFlightTurn, reason: str) -> None:
        if inflight.terminal_status is not None:
            return
        inflight.terminal_status = TerminalStatus.STALE
        inflight.terminal_reason = reason
        self._plan_sink.cancel_stale(inflight.task.seed.turn_id, reason)
        self._worker.abandon(inflight.future)
        self._homeostasis.settle_cognitive_budget(
            inflight.task.seed.turn_id,
            consumed=0.5,
        )
        try:
            self._settlement.settle(inflight.task.state_candidates)
        except Exception as error:  # noqa: BLE001 - owner commit boundary
            released = self._workspace.release(
                inflight.frame.frame_id,
                inflight.task.seed.turn_id,
                "turn_settlement_failed",
            )
            if getattr(released, "value", None) == "dead_lettered":
                self._affect_txn = None
            self._outcomes.record(
                reasoning_failure_outcome(
                    turn_id=inflight.task.seed.turn_id,
                    frame_id=inflight.frame.frame_id,
                    error_code=f"turn_settlement_failed:{type(error).__name__}",
                )
            )
            self._inflight = None
            return
        self._workspace.commit(
            inflight.frame.frame_id,
            inflight.task.seed.turn_id,
        )
        self._affect_txn = None
        self._outcomes.record(
            reasoning_stale_outcome(
                turn_id=inflight.task.seed.turn_id,
                frame_id=inflight.frame.frame_id,
                reason=reason,
            )
        )
        # The provider thread remains isolated and may finish later.  The
        # logical claim is closed now so the urgent event can form a fresh
        # independent Turn on the single-writer workspace.
        self._inflight = None

    def _timeout_turn(self, inflight: InFlightTurn) -> None:
        self._worker.abandon(inflight.future)
        self._homeostasis.settle_cognitive_budget(
            inflight.task.seed.turn_id,
            consumed=0.5,
        )
        try:
            self._settlement.settle(inflight.task.state_candidates)
        except Exception as error:  # noqa: BLE001 - owner commit boundary
            released = self._workspace.release(
                inflight.frame.frame_id,
                inflight.task.seed.turn_id,
                "turn_settlement_failed",
            )
            if getattr(released, "value", None) == "dead_lettered":
                self._affect_txn = None
            self._outcomes.record(
                reasoning_failure_outcome(
                    turn_id=inflight.task.seed.turn_id,
                    frame_id=inflight.frame.frame_id,
                    error_code=f"turn_settlement_failed:{type(error).__name__}",
                )
            )
            self._inflight = None
            return
        plan = self._turn_factory.noop_plan(
            inflight.task.seed,
            "reasoning_hard_timeout",
        )
        decision = govern_decision(inflight.frame, plan)
        if self._plan_sink.accept(decision):
            self._workspace.commit(inflight.frame.frame_id, inflight.task.seed.turn_id)
            self._affect_txn = None
            self._outcomes.record(reasoning_timeout_outcome(plan))
            inflight.terminal_status = TerminalStatus.TIMED_OUT
            inflight.terminal_reason = "reasoning_hard_timeout"
        else:
            released = self._workspace.release(
                inflight.frame.frame_id,
                inflight.task.seed.turn_id,
                "router_rejected_timeout",
            )
            if getattr(released, "value", None) == "dead_lettered":
                self._affect_txn = None
            self._outcomes.record(
                reasoning_failure_outcome(
                    turn_id=inflight.task.seed.turn_id,
                    frame_id=inflight.frame.frame_id,
                    error_code="router_rejected_timeout",
                )
            )
        self._inflight = None

    def _ensure_autonomous_event(self) -> bool:
        if (
            self._next_autonomous_at is None
            or self._timestamp < self._next_autonomous_at
        ):
            return False
        self._workspace.publish(
            self._turn_factory.autonomous_event(self._elfie_id, self._timestamp)
        )
        self._next_autonomous_at = None
        return True

    def _cancel_on_stop(self) -> None:
        inflight = self._inflight
        if inflight is None:
            return
        self._worker.abandon(inflight.future)
        self._homeostasis.settle_cognitive_budget(
            inflight.task.seed.turn_id,
            consumed=0.5,
        )
        if inflight.terminal_status is not None:
            self._inflight = None
            return
        self._plan_sink.cancel_stale(inflight.task.seed.turn_id, "coordinator_stopped")
        released = self._workspace.release(
            inflight.frame.frame_id,
            inflight.task.seed.turn_id,
            "coordinator_stopped",
        )
        if getattr(released, "value", None) == "dead_lettered":
            self._affect_txn = None
        self._inflight = None


__all__ = ("BrainCoordinator",)
