from datetime import datetime, timedelta, timezone

from elfie.brain.motivation import MotivationSystem
from elfie.message_types import EventId

NOW = datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc)


def test_recovery_drive_emits_one_candidate_and_suppresses_repeats() -> None:
    system = MotivationSystem(
        initial_at=NOW,
        cooldown_seconds=30.0,
        satisfaction_seconds=60.0,
    )

    candidate = system.evaluate(
        energy=10.0,
        fatigue=20.0,
        sleeping=False,
        now=NOW,
        blocked=False,
    )

    assert candidate is not None
    assert candidate.drive_id == "recovery"
    assert candidate.pressure == 0.5
    assert (
        system.evaluate(
            energy=10.0,
            fatigue=20.0,
            sleeping=False,
            now=NOW + timedelta(seconds=1),
            blocked=False,
        )
        is None
    )

    assert system.mark_handled(
        candidate.candidate_id,
        now=NOW + timedelta(seconds=1),
        success=True,
    )
    assert (
        system.evaluate(
            energy=10.0,
            fatigue=20.0,
            sleeping=False,
            now=NOW + timedelta(seconds=31),
            blocked=False,
        )
        is None
    )


def test_recovery_drive_waits_behind_pending_work_and_restores_suppression() -> None:
    system = MotivationSystem(initial_at=NOW, cooldown_seconds=30.0)

    assert (
        system.evaluate(
            energy=5.0,
            fatigue=10.0,
            sleeping=False,
            now=NOW,
            blocked=True,
        )
        is None
    )
    candidate = system.evaluate(
        energy=5.0,
        fatigue=10.0,
        sleeping=False,
        now=NOW + timedelta(seconds=1),
        blocked=False,
    )
    assert candidate is not None

    checkpoint = system.checkpoint()
    restored = MotivationSystem(initial_at=NOW)
    restored.restore(checkpoint)
    assert restored.snapshot(NOW + timedelta(seconds=2)).last_trigger_id == EventId(
        candidate.candidate_id
    )
    assert (
        restored.evaluate(
            energy=5.0,
            fatigue=10.0,
            sleeping=False,
            now=NOW + timedelta(seconds=2),
            blocked=False,
        )
        is None
    )
