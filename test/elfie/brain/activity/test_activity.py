from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from elfie.brain.activity.preflight import ActivityPreflightService
from elfie.brain.activity.system import (
    ActivityDraft,
    ActivityRecord,
    ActivityState,
    ActivityStep,
    ActivityStepKind,
    ActivityTransitionError,
    ExecutionScope,
    InMemoryActivityStore,
    transition_activity,
)
from elfie.brain.reasoning.context_types import (
    ConnectedChannelDescriptor,
    EffectiveCapabilities,
)
from elfie.brain.workspace.contracts import ExternalExecutionDomain
from elfie.message_types import ActivityId, ActorId, EventId

UTC = timezone.utc
NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


def _draft(*, wake_at: datetime | None = None) -> ActivityDraft:
    return ActivityDraft(
        activity_id=ActivityId("activity-1"),
        goal="提醒主人带钥匙",
        success_criteria="提醒消息获得通信回执",
        steps=(
            ActivityStep(
                step_id=EventId("step-1"),
                ordinal=0,
                kind=ActivityStepKind.COMMUNICATION,
                operation="send_message",
                deadline=NOW + timedelta(hours=2),
                scope=ExecutionScope(
                    external_domain=ExternalExecutionDomain.COMMUNICATION,
                    target_actor_id=ActorId("owner"),
                    channel_id="elfie",
                    conversation_id="owner",
                    capability_revision=0,
                    allowed_operations=("send_message",),
                    expires_at=NOW + timedelta(hours=2),
                ),
            ),
        ),
        cause_event_ids=(EventId("cause-1"),),
        idempotency_key="activity-1:create",
        created_at=NOW,
        deadline=NOW + timedelta(hours=3),
        wake_at=wake_at,
    )


def _record() -> ActivityRecord:
    draft = _draft(wake_at=NOW + timedelta(minutes=30))
    return ActivityRecord(
        activity_id=draft.activity_id,
        revision=0,
        state=ActivityState.VALIDATED,
        draft=draft,
        created_at=NOW,
        updated_at=NOW,
        next_wakeup_at=draft.wake_at,
    )


def test_activity_draft_requires_external_scope_for_communication_step() -> None:
    with pytest.raises(ValidationError, match="communication Activity steps"):
        ActivityDraft(
            activity_id=ActivityId("activity-1"),
            goal="提醒主人",
            success_criteria="回执完成",
            steps=(
                ActivityStep(
                    step_id=EventId("step-1"),
                    ordinal=0,
                    kind=ActivityStepKind.COMMUNICATION,
                    operation="send_message",
                    deadline=NOW + timedelta(hours=1),
                    scope=ExecutionScope(
                        external_domain=None,
                        capability_revision=0,
                        allowed_operations=("send_message",),
                        expires_at=NOW + timedelta(hours=1),
                    ),
                ),
            ),
            cause_event_ids=(EventId("cause-1"),),
            idempotency_key="activity-1:create",
            created_at=NOW,
            deadline=NOW + timedelta(hours=2),
        )


def test_activity_draft_rejects_step_outside_activity_window() -> None:
    scope = ExecutionScope(
        external_domain=ExternalExecutionDomain.COMMUNICATION,
        target_actor_id=ActorId("owner"),
        channel_id="elfie",
        conversation_id="owner",
        capability_revision=0,
        allowed_operations=("send_message",),
        expires_at=NOW + timedelta(hours=3),
    )
    with pytest.raises(ValidationError, match="step deadlines"):
        ActivityDraft(
            activity_id=ActivityId("activity-1"),
            goal="提醒主人",
            success_criteria="回执完成",
            steps=(
                ActivityStep(
                    step_id=EventId("step-1"),
                    ordinal=0,
                    kind=ActivityStepKind.COMMUNICATION,
                    operation="send_message",
                    deadline=NOW + timedelta(hours=3),
                    scope=scope,
                ),
            ),
            cause_event_ids=(EventId("cause-1"),),
            idempotency_key="activity-1:create",
            created_at=NOW,
            deadline=NOW + timedelta(hours=2),
        )


def test_validated_activity_can_wait_then_run_with_versioned_event() -> None:
    record = _record()

    waiting, waiting_event = transition_activity(
        record,
        ActivityState.WAITING,
        now=NOW + timedelta(minutes=1),
        next_wakeup_at=NOW + timedelta(minutes=30),
    )
    running, running_event = transition_activity(
        waiting,
        ActivityState.RUNNING,
        now=NOW + timedelta(minutes=30),
    )

    assert waiting.revision == 1
    assert waiting_event.state is ActivityState.WAITING
    assert running.revision == 2
    assert running_event.revision == 2
    assert running.next_wakeup_at is None


def test_activity_transition_rejects_illegal_terminal_reopen_and_backward_time() -> (
    None
):
    completed, _ = transition_activity(
        _record(),
        ActivityState.RUNNING,
        now=NOW + timedelta(minutes=1),
    )
    completed, _ = transition_activity(
        completed,
        ActivityState.COMPLETED,
        now=NOW + timedelta(minutes=2),
    )

    with pytest.raises(ActivityTransitionError, match="illegal Activity transition"):
        transition_activity(
            completed, ActivityState.RUNNING, now=NOW + timedelta(minutes=3)
        )
    with pytest.raises(ActivityTransitionError, match="cannot move backwards"):
        transition_activity(
            _record(), ActivityState.RUNNING, now=NOW - timedelta(minutes=1)
        )


def _preflight(*, target_resolved: bool = True) -> ActivityPreflightService:
    capabilities = EffectiveCapabilities(
        revision=0,
        captured_at=NOW,
        current_body=None,
        connected_channels=(
            ConnectedChannelDescriptor(
                channel_id="elfie",
                account_id="owner-account",
                capability_revision=1,
                content_kinds=("text",),
                authorized_conversation_ids=("owner",),
            ),
        ),
    )
    return ActivityPreflightService(
        store=InMemoryActivityStore(),
        clock=lambda: NOW,
        capabilities=lambda: capabilities,
        available_budget=lambda: 10.0,
        target_resolver=lambda *_args: target_resolved,
    )


def test_activity_preflight_resolves_target_before_commit() -> None:
    service = _preflight()
    draft = _draft(wake_at=NOW + timedelta(minutes=30))

    result = service.preflight(draft)
    committed = service.commit(draft, result)

    assert result.status.value == "validated"
    assert committed.state is ActivityState.WAITING


def test_activity_preflight_requires_same_turn_clarification_for_unknown_target() -> (
    None
):
    result = _preflight(target_resolved=False).preflight(_draft())

    assert result.status.value == "needs_clarification"
    assert result.reasons[0].code == "activity_target_unresolved"


def test_activity_commit_rejects_copied_or_forged_preflight_evidence() -> None:
    service = _preflight()
    draft = _draft()
    issued = service.preflight(draft)
    copied = issued.model_copy()

    with pytest.raises(ValueError, match="was not issued"):
        service.commit(draft, copied)
