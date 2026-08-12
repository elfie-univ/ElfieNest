from datetime import datetime, timedelta, timezone

import pytest

from elfie.brain.activity import (
    ActivityDraft,
    ActivityPreflightStatus,
    ActivityState,
    ActivityStep,
    ActivityStepKind,
)
from elfie.brain.perception_types import ExternalExecutionDomain, ResponseScope
from elfie.message_types import ActivityId, EventId
from infrastructure.persistence.activity import (
    ActivityStoreConflict,
    SQLiteActivityStoreAdapter,
)

UTC = timezone.utc
NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


def _draft(*, activity_id: str = "activity-1") -> ActivityDraft:
    return ActivityDraft(
        activity_id=ActivityId(activity_id),
        goal="提醒主人带钥匙",
        success_criteria="提醒消息获得通信回执",
        steps=(
            ActivityStep(
                step_id=EventId(f"{activity_id}:step-1"),
                ordinal=0,
                kind=ActivityStepKind.COMMUNICATION,
                operation="send_message",
                deadline=NOW + timedelta(hours=2),
                scope=ResponseScope(
                    external_domain=ExternalExecutionDomain.COMMUNICATION,
                    channel_id="elfie",
                    conversation_id="owner",
                ),
            ),
        ),
        cause_event_ids=(EventId(f"{activity_id}:cause-1"),),
        idempotency_key=f"{activity_id}:create",
        created_at=NOW,
        deadline=NOW + timedelta(hours=3),
        wake_at=NOW + timedelta(minutes=30),
    )


def test_preflight_has_no_side_effect_and_commit_is_idempotent() -> None:
    store = SQLiteActivityStoreAdapter.in_memory()
    try:
        draft = _draft()
        result = store.preflight(draft, now=NOW)

        assert result.status is ActivityPreflightStatus.VALIDATED
        assert store.list() == ()

        first = store.commit(draft, preflight=result)
        second = store.commit(draft, preflight=result)

        assert first == second
        assert first.state is ActivityState.WAITING
        assert store.get(draft.activity_id) == first
    finally:
        store.close()


def test_store_reopens_committed_activity_and_rejects_stale_transition() -> None:
    store = SQLiteActivityStoreAdapter.in_memory()
    try:
        draft = _draft()
        result = store.preflight(draft, now=NOW)
        record = store.commit(draft, preflight=result)

        event = store.transition(
            draft.activity_id,
            expected_revision=record.revision,
            target=ActivityState.RUNNING,
            now=NOW + timedelta(minutes=30),
        )
        assert event.revision == 1
        assert store.get(draft.activity_id).state is ActivityState.RUNNING

        with pytest.raises(ActivityStoreConflict, match="revision conflict"):
            store.transition(
                draft.activity_id,
                expected_revision=record.revision,
                target=ActivityState.CANCELLED,
                now=NOW + timedelta(minutes=31),
            )
    finally:
        store.close()


def test_expired_preflight_never_writes() -> None:
    store = SQLiteActivityStoreAdapter.in_memory()
    try:
        draft = _draft()
        result = store.preflight(draft, now=NOW + timedelta(days=1))
        assert result.status is ActivityPreflightStatus.REJECTED
        assert store.list() == ()
        with pytest.raises(ActivityStoreConflict, match="validated"):
            store.commit(draft, preflight=result)
    finally:
        store.close()
