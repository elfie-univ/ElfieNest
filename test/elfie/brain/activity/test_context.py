"""Tests for the bounded Activity projection used by Brain context assembly."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from elfie.brain.activity.context import ActivityContextReader
from elfie.brain.activity.system import (
    ActivityDraft,
    ActivityState,
    ActivityStep,
    ActivityStepKind,
    ExecutionScope,
    InMemoryActivityStore,
)
from elfie.brain.consolidation.system import CognitiveConsolidationSystem
from elfie.brain.memory.memory_system import MemorySystem
from elfie.brain.motivation.system import MotivationSystem
from elfie.brain.orientation.system import OrientationSystem
from elfie.brain.reasoning.context_source import BrainContextProvider
from elfie.brain.reasoning.context_types import (
    EffectiveCapabilities,
)
from elfie.brain.reasoning.conversation_context import ConversationContextStore
from elfie.brain.reasoning.memory_context import MemoryContextReader
from elfie.brain.selfhood.system import SelfhoodSystem
from elfie.message_types import ActivityId, EventId
from infrastructure.persistence.memory import SQLiteMemoryStoreAdapter

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


def _draft(activity_id: str, *, created_at: datetime) -> ActivityDraft:
    return ActivityDraft(
        activity_id=ActivityId(activity_id),
        goal=f"完成 {activity_id}",
        success_criteria="内部步骤完成",
        steps=(
            ActivityStep(
                step_id=EventId(f"{activity_id}:step"),
                ordinal=0,
                kind=ActivityStepKind.INTERNAL,
                operation="record_progress",
                deadline=created_at + timedelta(hours=2),
                scope=ExecutionScope(
                    external_domain=None,
                    capability_revision=0,
                    allowed_operations=("record_progress",),
                    expires_at=created_at + timedelta(hours=2),
                ),
            ),
        ),
        cause_event_ids=(EventId(f"{activity_id}:cause"),),
        idempotency_key=f"{activity_id}:create",
        created_at=created_at,
        deadline=created_at + timedelta(hours=3),
        wake_at=created_at + timedelta(minutes=30),
    )


def _context_state(
    store: InMemoryActivityStore | None,
    *,
    capacity: int = 16,
) -> BrainContextProvider:
    memory = MemorySystem(
        SQLiteMemoryStoreAdapter.in_memory(),
        elfie_id="elfie-1",
        initial_at=NOW,
    )
    return BrainContextProvider(
        memory=MemoryContextReader(memory),
        conversations=ConversationContextStore(),
        activities=ActivityContextReader(store, capacity=capacity),
        capability_reader=lambda captured_at, _authorized: EffectiveCapabilities(
            revision=0,
            captured_at=captured_at,
            current_body=None,
            connected_channels=(),
        ),
        clock=lambda: NOW,
        orientation=OrientationSystem(initial_at=NOW),
        selfhood=SelfhoodSystem(initial_at=NOW),
        motivation=MotivationSystem(initial_at=NOW),
        consolidation=CognitiveConsolidationSystem(
            pending_episode_ids=memory.pending_consolidation_ids,
            consolidate=lambda limit: memory.run_consolidation(max_episodes=limit),
            initial_at=NOW,
        ),
    )


def test_activity_snapshot_reads_committed_state_without_writing_the_store() -> None:
    # Given: one committed Activity owned by the injected Store.
    store = InMemoryActivityStore()
    draft = _draft("activity-1", created_at=NOW)
    preflight = store.preflight(draft, now=NOW)
    record = store.commit(draft, preflight=preflight)
    state = _context_state(store)

    # When: Brain captures the Activity projection at the Turn cutoff.
    snapshot = state.activities(NOW)

    # Then: it exposes a bounded, versioned read and leaves the owner unchanged.
    assert snapshot.revision == record.revision
    assert snapshot.captured_at == NOW
    assert snapshot.freshness == "current"
    assert snapshot.items[0].activity_id == ActivityId("activity-1")
    assert snapshot.items[0].goal == "完成 activity-1"
    assert snapshot.items[0].state.value == "waiting"
    assert store.get(ActivityId("activity-1")) == record


def test_activity_snapshot_is_bounded_and_marks_truncation() -> None:
    # Given: more committed Activities than the context budget allows.
    store = InMemoryActivityStore()
    for activity_id in ("activity-1", "activity-2"):
        draft = _draft(activity_id, created_at=NOW)
        store.commit(draft, preflight=store.preflight(draft, now=NOW))
    state = _context_state(store, capacity=1)

    # When: Brain captures the bounded projection.
    snapshot = state.activities(NOW)

    # Then: the model-facing context cannot grow with the durable store.
    assert len(snapshot.items) == 1
    assert snapshot.truncated is True
    assert snapshot.unknown_fields == ()


def test_activity_snapshot_does_not_leak_state_newer_than_cutoff() -> None:
    # Given: an Activity that changes after the Turn cutoff.
    store = InMemoryActivityStore()
    draft = _draft("activity-1", created_at=NOW)
    record = store.commit(draft, preflight=store.preflight(draft, now=NOW))
    store.transition(
        record.activity_id,
        expected_revision=record.revision,
        target=ActivityState.RUNNING,
        now=NOW + timedelta(minutes=1),
    )
    state = _context_state(store)

    # When: Brain assembles the earlier Turn cutoff.
    snapshot = state.activities(NOW)

    # Then: it refuses the newer row and labels the source as stale.
    assert snapshot.items == ()
    assert snapshot.freshness == "stale"
    assert snapshot.unknown_fields == ("newer_activity_state",)


def test_missing_activity_owner_is_explicitly_unknown() -> None:
    # Given: an isolated Brain context without an Activity Store wiring.
    state = _context_state(None)

    # When: the caller asks for the projection.
    # Then: the normal production wiring is required to claim current Activity facts.
    snapshot = state.activities(NOW)
    assert snapshot.freshness == "unknown"
    assert snapshot.unknown_fields == ("activities",)
