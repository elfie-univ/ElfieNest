"""Deterministic tests for hybrid reasoning-turn triggering."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from elfie.brain.workspace.contracts import TriggerReason
from elfie.brain.workspace.trigger_policy import TurnTriggerPolicy
from elfie.brain.workspace.types import TriggerMetrics

NOW = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)


def _metrics(
    *,
    count: int = 0,
    oldest: datetime | None = None,
    newest: datetime | None = None,
    oldest_social: datetime | None = None,
    newest_social: datetime | None = None,
    critical_count: int = 0,
    salience: float = 0.0,
) -> TriggerMetrics:
    return TriggerMetrics(
        revision=1,
        latest_ingest_seq=count,
        reliable_event_count=count,
        state_key_count=0,
        media_sample_count=0,
        oldest_event_at=oldest,
        newest_event_at=newest,
        oldest_social_at=oldest_social,
        newest_social_at=newest_social,
        critical_event_count=critical_count,
        max_salience=salience,
        stopped=False,
    )


def test_conversation_waits_for_quiet_window_then_triggers_once() -> None:
    # Given: five complete messages arrived inside one 400ms burst.
    metrics = _metrics(
        count=5,
        oldest=NOW,
        newest=NOW + timedelta(milliseconds=300),
        oldest_social=NOW,
        newest_social=NOW + timedelta(milliseconds=300),
    )
    policy = TurnTriggerPolicy()

    # When: evaluated before and at the quiet-window boundary.
    early = policy.evaluate(metrics, now=NOW + timedelta(milliseconds=699))
    ready = policy.evaluate(metrics, now=NOW + timedelta(milliseconds=700))

    # Then: only the boundary evaluation seals a conversation turn.
    assert early.reason is None
    assert ready.reason is TriggerReason.CONVERSATION_QUIET
    assert ready.cutoff_seq == 5


def test_continuous_conversation_hits_two_second_hard_max() -> None:
    # Given: messages continue arriving, so no quiet interval exists.
    metrics = _metrics(
        count=9,
        oldest=NOW,
        newest=NOW + timedelta(milliseconds=1900),
        oldest_social=NOW,
        newest_social=NOW + timedelta(milliseconds=1900),
    )

    # When: the first message reaches the hard maximum age.
    decision = TurnTriggerPolicy().evaluate(metrics, now=NOW + timedelta(seconds=2))

    # Then: the frame seals despite the recent final message.
    assert decision.reason is TriggerReason.CONVERSATION_HARD_MAX


def test_urgent_and_autonomous_reasons_do_not_depend_on_clock_pulse_itself() -> None:
    # Given: an empty workspace, an autonomous deadline, and a critical event case.
    policy = TurnTriggerPolicy()

    # When: ordinary and explicit-autonomous evaluations run.
    empty = policy.evaluate(_metrics(), now=NOW)
    autonomous = policy.evaluate(_metrics(count=1), now=NOW, autonomous_due=True)
    urgent = policy.evaluate(
        _metrics(count=1, oldest=NOW, newest=NOW, critical_count=1),
        now=NOW,
    )

    # Then: an empty clock pulse is inert; explicit causes are immediate.
    assert empty.reason is None
    assert autonomous.reason is TriggerReason.AUTONOMOUS
    assert urgent.reason is TriggerReason.EMERGENCY
