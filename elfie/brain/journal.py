"""Durable causal journal contracts for one continuous Brain.

The journal records facts; it never decides behavior.  On restart, unfinished
Runs and directives are closed as uncertain reconciliation facts instead of
being replayed and risking duplicate external effects.
"""

from __future__ import annotations

import json
from enum import Enum, unique
from hashlib import sha256
from threading import RLock
from typing import Callable, Optional, Protocol, Tuple

from pydantic import StringConstraints
from typing_extensions import Annotated

from elfie.brain.activity.system import ActivityRecord
from elfie.brain.continuity import BrainContinuityCheckpoint
from elfie.brain.reasoning.decision_types import TurnDecision
from elfie.brain.reasoning.execution_types import ExecutionReceipt
from elfie.brain.reasoning.turn_outcome import TurnOutcome
from elfie.brain.workspace.contracts import (
    ExecutionStatus,
    InternalPayload,
    InternalSignal,
    PerceptionEvent,
    TurnFrame,
    WorkspacePersistentState,
)
from elfie.message_types import (
    ActivityId,
    ActorId,
    ActorRef,
    CorrelationId,
    ElfieId,
    EventId,
    FrozenContractModel,
    IntentId,
    MessageMeta,
    PlanId,
    Priority,
    TraceId,
    TurnId,
    UTCDateTime,
)

_NonBlankText = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=8192, pattern=r".*\S.*"),
]
_IdempotencyKey = Annotated[
    str,
    StringConstraints(strict=True, min_length=1, max_length=512, pattern=r".*\S.*"),
]


@unique
class BrainJournalKind(str, Enum):
    """Closed fact categories required for restart reconciliation."""

    RUN_STARTED = "run_started"
    RUN_TERMINATED = "run_terminated"
    DIRECTIVE_ACCEPTED = "directive_accepted"
    DIRECTIVE_REJECTED = "directive_rejected"
    EXECUTION_RECEIPT = "execution_receipt"
    ACTIVITY_STATE = "activity_state"
    RUN_RECONCILED = "run_reconciled"
    DIRECTIVE_RECONCILED = "directive_reconciled"


class BrainJournalEntry(FrozenContractModel):
    """One append-only causal fact with stable cross-runtime identities."""

    entry_id: EventId
    elfie_id: ElfieId
    kind: BrainJournalKind
    occurred_at: UTCDateTime
    idempotency_key: _IdempotencyKey
    turn_id: Optional[TurnId] = None
    frame_id: Optional[EventId] = None
    plan_id: Optional[PlanId] = None
    intent_id: Optional[IntentId] = None
    activity_id: Optional[ActivityId] = None
    receipt_id: Optional[EventId] = None
    status: Optional[_NonBlankText] = None
    cause_event_ids: Tuple[EventId, ...] = ()
    detail: Optional[_NonBlankText] = None


class BrainJournalPort(Protocol):
    """Brain-owned durable journal and latest committed-state checkpoint Port."""

    def append(self, entry: BrainJournalEntry) -> bool:
        """Append once; return ``False`` for the same idempotent fact."""

    def entries(self) -> Tuple[BrainJournalEntry, ...]:
        """Return facts in durable append order."""

    def save_checkpoint(self, checkpoint: BrainContinuityCheckpoint) -> None:
        """Atomically replace the latest committed cognitive checkpoint."""

    def load_checkpoint(self) -> BrainContinuityCheckpoint | None:
        """Return the latest committed checkpoint, if one exists."""

    def load_workspace_state(self) -> WorkspacePersistentState:
        """Return restart-safe pending input and dedupe state."""

    def save_workspace_state(self, state: WorkspacePersistentState) -> None:
        """Atomically replace pending input and dedupe state."""


class InMemoryBrainJournal(BrainJournalPort):
    """Thread-safe test/default store with the same idempotency contract."""

    def __init__(self) -> None:
        self._entries: list[BrainJournalEntry] = []
        self._by_key: dict[str, BrainJournalEntry] = {}
        self._checkpoint: BrainContinuityCheckpoint | None = None
        self._workspace_state = WorkspacePersistentState()
        self._lock = RLock()

    def append(self, entry: BrainJournalEntry) -> bool:
        with self._lock:
            existing = self._by_key.get(entry.idempotency_key)
            if existing is not None:
                if existing != entry:
                    raise ValueError("Brain journal idempotency conflict")
                return False
            self._entries.append(entry)
            self._by_key[entry.idempotency_key] = entry
            return True

    def entries(self) -> Tuple[BrainJournalEntry, ...]:
        with self._lock:
            return tuple(self._entries)

    def save_checkpoint(self, checkpoint: BrainContinuityCheckpoint) -> None:
        with self._lock:
            self._checkpoint = checkpoint

    def load_checkpoint(self) -> BrainContinuityCheckpoint | None:
        with self._lock:
            return self._checkpoint

    def load_workspace_state(self) -> WorkspacePersistentState:
        with self._lock:
            return self._workspace_state

    def save_workspace_state(self, state: WorkspacePersistentState) -> None:
        with self._lock:
            self._workspace_state = state


class ReconciliationFact(FrozenContractModel):
    """One uncertain operation safely abandoned after process restart."""

    subject: Annotated[
        str,
        StringConstraints(strict=True, pattern=r"^(run|directive)$"),
    ]
    turn_id: TurnId
    plan_id: Optional[PlanId] = None
    intent_id: Optional[IntentId] = None
    cause_event_ids: Tuple[EventId, ...] = ()


class BrainJournal:
    """Typed recorder and deterministic restart reconciler over one store Port."""

    def __init__(
        self,
        *,
        elfie_id: ElfieId,
        store: BrainJournalPort,
        clock: Callable[[], UTCDateTime],
    ) -> None:
        self._elfie_id = elfie_id
        self._store = store
        self._clock = clock

    def record_run_started(self, frame: TurnFrame, turn_id: TurnId) -> None:
        self._append(
            BrainJournalKind.RUN_STARTED,
            f"run:{turn_id}:started",
            turn_id=turn_id,
            frame_id=frame.frame_id,
            cause_event_ids=tuple(event.meta.event_id for event in frame.events),
        )

    def record_outcome(self, outcome: TurnOutcome) -> None:
        self._append(
            BrainJournalKind.RUN_TERMINATED,
            f"run:{outcome.turn_id}:terminal",
            turn_id=outcome.turn_id,
            frame_id=outcome.frame_id,
            plan_id=outcome.plan_id,
            status=outcome.status.value,
            detail=(
                outcome.error_code
                or outcome.timeout_reason
                or outcome.stale_reason
                or outcome.fallback_reason
            ),
        )

    def record_decision(self, decision: TurnDecision) -> None:
        plan = decision.plan
        for intent in plan.intents:
            self._append(
                BrainJournalKind.DIRECTIVE_ACCEPTED,
                f"directive:{plan.plan_id}:{intent.intent_id}:accepted",
                turn_id=plan.turn_id,
                frame_id=plan.frame_id,
                plan_id=plan.plan_id,
                intent_id=intent.intent_id,
                status=ExecutionStatus.ACCEPTED.value,
                cause_event_ids=intent.cause_event_ids,
            )

    def record_rejection(self, decision: TurnDecision, detail: str) -> None:
        plan = decision.plan
        detail_digest = sha256(detail.encode("utf-8")).hexdigest()
        self._append(
            BrainJournalKind.DIRECTIVE_REJECTED,
            f"decision:{plan.plan_id}:rejected:{detail_digest}",
            turn_id=plan.turn_id,
            frame_id=plan.frame_id,
            plan_id=plan.plan_id,
            status=ExecutionStatus.REJECTED.value,
            detail=detail,
        )

    def record_receipt(self, receipt: ExecutionReceipt) -> None:
        self._append(
            BrainJournalKind.EXECUTION_RECEIPT,
            f"receipt:{receipt.receipt_id}",
            turn_id=receipt.turn_id,
            plan_id=receipt.plan_id,
            intent_id=receipt.intent_id,
            receipt_id=receipt.receipt_id,
            status=receipt.status.value,
            detail=receipt.error.code if receipt.error is not None else None,
        )

    def record_activity(
        self,
        record: ActivityRecord,
        *,
        detail: str | None = None,
    ) -> None:
        self._append(
            BrainJournalKind.ACTIVITY_STATE,
            f"activity:{record.activity_id}:revision:{record.revision}",
            activity_id=record.activity_id,
            status=record.state.value,
            cause_event_ids=record.draft.cause_event_ids,
            detail=(
                detail
                if detail is not None
                else record.last_error.code
                if record.last_error is not None
                else None
            ),
        )

    def reconcile_unfinished(self) -> Tuple[ReconciliationFact, ...]:
        """Close unfinished work as uncertain without replaying external effects."""
        entries = self._store.entries()
        terminal_runs = {
            entry.turn_id
            for entry in entries
            if entry.kind
            in {BrainJournalKind.RUN_TERMINATED, BrainJournalKind.RUN_RECONCILED}
            and entry.turn_id is not None
        }
        started_runs = {
            entry.turn_id: entry
            for entry in entries
            if entry.kind is BrainJournalKind.RUN_STARTED and entry.turn_id is not None
        }
        terminal_statuses = {
            status.value
            for status in ExecutionStatus
            if status not in {ExecutionStatus.ACCEPTED, ExecutionStatus.STARTED}
        }
        terminal_intents = {
            (entry.plan_id, entry.intent_id)
            for entry in entries
            if (
                entry.kind is BrainJournalKind.DIRECTIVE_RECONCILED
                or (
                    entry.kind is BrainJournalKind.EXECUTION_RECEIPT
                    and entry.status in terminal_statuses
                )
            )
            and entry.plan_id is not None
            and entry.intent_id is not None
        }
        accepted_intents = {
            (entry.plan_id, entry.intent_id): entry
            for entry in entries
            if entry.kind is BrainJournalKind.DIRECTIVE_ACCEPTED
            and entry.turn_id is not None
            and entry.plan_id is not None
            and entry.intent_id is not None
        }
        facts: list[ReconciliationFact] = []
        for turn_id, entry in started_runs.items():
            if turn_id in terminal_runs:
                continue
            fact = ReconciliationFact(
                subject="run",
                turn_id=turn_id,
                cause_event_ids=entry.cause_event_ids,
            )
            facts.append(fact)
            self._append(
                BrainJournalKind.RUN_RECONCILED,
                f"run:{turn_id}:reconciled",
                turn_id=turn_id,
                frame_id=entry.frame_id,
                status="interrupted_on_restart",
                cause_event_ids=entry.cause_event_ids,
            )
        for key, entry in accepted_intents.items():
            if key in terminal_intents:
                continue
            directive_turn_id = entry.turn_id
            if directive_turn_id is None:
                continue
            fact = ReconciliationFact(
                subject="directive",
                turn_id=directive_turn_id,
                plan_id=entry.plan_id,
                intent_id=entry.intent_id,
                cause_event_ids=entry.cause_event_ids,
            )
            facts.append(fact)
            self._append(
                BrainJournalKind.DIRECTIVE_RECONCILED,
                f"directive:{entry.plan_id}:{entry.intent_id}:reconciled",
                turn_id=entry.turn_id,
                frame_id=entry.frame_id,
                plan_id=entry.plan_id,
                intent_id=entry.intent_id,
                status="outcome_unknown_after_restart",
                cause_event_ids=entry.cause_event_ids,
            )
        return tuple(facts)

    def entries(self) -> Tuple[BrainJournalEntry, ...]:
        return self._store.entries()

    def _append(
        self,
        kind: BrainJournalKind,
        idempotency_key: str,
        *,
        turn_id: Optional[TurnId] = None,
        frame_id: Optional[EventId] = None,
        plan_id: Optional[PlanId] = None,
        intent_id: Optional[IntentId] = None,
        activity_id: Optional[ActivityId] = None,
        receipt_id: Optional[EventId] = None,
        status: Optional[str] = None,
        cause_event_ids: Tuple[EventId, ...] = (),
        detail: Optional[str] = None,
    ) -> None:
        digest = sha256(idempotency_key.encode("utf-8")).hexdigest()
        self._store.append(
            BrainJournalEntry(
                entry_id=EventId(f"brain-journal:{digest}"),
                elfie_id=self._elfie_id,
                kind=kind,
                occurred_at=self._clock(),
                idempotency_key=idempotency_key,
                turn_id=turn_id,
                frame_id=frame_id,
                plan_id=plan_id,
                intent_id=intent_id,
                activity_id=activity_id,
                receipt_id=receipt_id,
                status=status,
                cause_event_ids=cause_event_ids,
                detail=detail,
            )
        )


def reconciliation_fact_to_perception(
    fact: ReconciliationFact,
    *,
    elfie_id: ElfieId,
    occurred_at: UTCDateTime,
) -> PerceptionEvent:
    """Expose restart uncertainty as inert input, never as effect replay."""
    payload_json = json.dumps(fact.model_dump(mode="json"), ensure_ascii=False)
    fact_digest = sha256(payload_json.encode("utf-8")).hexdigest()
    return PerceptionEvent(
        meta=MessageMeta(
            event_id=EventId(f"brain-reconciliation:{fact_digest}"),
            elfie_id=elfie_id,
            source=ActorRef(
                actor_id=ActorId("brain-journal"),
                source_kind="brain_journal",
            ),
            occurred_at=occurred_at,
            received_at=occurred_at,
            trace_id=TraceId(f"reconciliation:{fact_digest}"),
            causation_id=(fact.cause_event_ids[0] if fact.cause_event_ids else None),
            correlation_id=CorrelationId(str(fact.plan_id or fact.turn_id)),
            priority=Priority.HIGH,
        ),
        payload=InternalPayload(
            type="internal",
            signal=InternalSignal.PROCESSING_FAILURE,
            detail=payload_json,
        ),
        salience=0.9,
    )


__all__ = (
    "BrainJournal",
    "BrainJournalEntry",
    "BrainJournalKind",
    "BrainJournalPort",
    "InMemoryBrainJournal",
    "ReconciliationFact",
    "reconciliation_fact_to_perception",
)
