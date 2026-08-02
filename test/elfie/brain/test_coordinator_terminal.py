"""Terminal stale and timeout scenarios for BrainCoordinator."""

from threading import Event, Thread

from elfie.brain.limbic_appraiser import BrainClockPulse
from elfie.brain.perception_types import TriggerReason
from elfie.brain.perceptual_workspace import PerceptualWorkspace
from elfie.brain.turn_outcome import TerminalStatus
from elfie.brain.workspace_types import ActiveClaimError
from elfie.message_types import Priority
from test.elfie.brain.test_coordinator import (
    ELFIE_ID,
    NOW,
    BlockingPlanRuntime,
    RecordingPlanSink,
    _coordinator,
    _physical,
)


def test_urgent_event_discards_late_plan_without_routing_it() -> None:
    workspace = PerceptualWorkspace(ELFIE_ID)
    runtime = BlockingPlanRuntime()
    sink = RecordingPlanSink()
    coordinator, _, _ = _coordinator(workspace, runtime, sink)
    coordinator.start()
    workspace.publish(_physical(1, 0, salience=0.95))
    coordinator.notify_perception()
    runtime.started.wait()

    workspace.publish(_physical(2, 50, salience=1.0, priority=Priority.CRITICAL))
    coordinator.notify_perception(urgent_reason="emergency_stop")
    sink.cancel_seen.wait()
    runtime.release.set()
    coordinator.wait_for_outcome()
    coordinator.synchronize()

    assert sink.plans == []
    assert len(sink.cancelled) == 1
    assert coordinator.outcomes()[0].status is TerminalStatus.STALE
    assert workspace.metrics().reliable_event_count == 1
    coordinator.stop()
    coordinator.join()


def test_clock_is_inert_until_autonomous_deadline_and_timeout_commits_noop() -> None:
    workspace = PerceptualWorkspace(ELFIE_ID)
    runtime = BlockingPlanRuntime()
    sink = RecordingPlanSink()
    deadline = NOW.timestamp() + 5.0
    coordinator, _, _ = _coordinator(
        workspace,
        runtime,
        sink,
        next_autonomous_at=deadline,
    )
    coordinator.start()

    coordinator.post_clock(BrainClockPulse(timestamp=NOW.timestamp() + 1.0))
    coordinator.synchronize()
    assert runtime.calls == []
    coordinator.post_clock(BrainClockPulse(timestamp=deadline))
    runtime.started.wait()
    coordinator.post_clock(BrainClockPulse(timestamp=deadline + 46.0))
    sink.accepted.wait()
    coordinator.synchronize()

    assert len(sink.plans) == 1
    assert tuple(intent.type for intent in sink.plans[0].intents) == ("noop",)
    assert coordinator.outcomes()[0].status is TerminalStatus.TIMED_OUT
    assert workspace.metrics().reliable_event_count == 0
    runtime.release.set()
    coordinator.synchronize()
    assert len(sink.plans) == 1
    coordinator.stop()
    coordinator.join()


def test_timeout_releases_the_logical_inflight_slot_for_the_next_frame() -> None:
    # Given: one blocked cortical turn reaches its coordinator-owned deadline.
    workspace = PerceptualWorkspace(ELFIE_ID)
    runtime = BlockingPlanRuntime()
    sink = RecordingPlanSink()
    coordinator, _, _ = _coordinator(workspace, runtime, sink)
    coordinator.start()
    workspace.publish(_physical(1, 0, salience=0.95))
    coordinator.notify_perception()
    assert runtime.started.wait(1)
    coordinator.post_clock(BrainClockPulse(timestamp=NOW.timestamp() + 46.0))
    coordinator.wait_for_outcome()
    coordinator.synchronize()

    # When: a second significant fact arrives after the first turn is terminal.
    workspace.publish(_physical(2, 45_000, salience=0.95))
    coordinator.notify_perception()
    coordinator.synchronize()

    # Then: Brain claims the next frame instead of staying blocked by stale state.
    try:
        workspace.seal(
            reason=TriggerReason.MANUAL,
            captured_at=NOW,
        )
    except ActiveClaimError:
        next_frame_claimed = True
    else:
        next_frame_claimed = False
    runtime.release.set()
    coordinator.stop()
    coordinator.join()
    assert next_frame_claimed is True


def test_timeout_isolates_hung_provider_and_join_returns_before_release() -> None:
    # Given: a provider call remains blocked after its logical hard timeout.
    workspace = PerceptualWorkspace(ELFIE_ID)
    runtime = BlockingPlanRuntime()
    sink = RecordingPlanSink()
    coordinator, _, _ = _coordinator(workspace, runtime, sink)
    coordinator.start()
    workspace.publish(_physical(1, 0, salience=0.95))
    coordinator.notify_perception()
    assert runtime.started.wait(1)
    coordinator.post_clock(BrainClockPulse(timestamp=NOW.timestamp() + 46.0))
    coordinator.wait_for_outcome()
    coordinator.synchronize()

    # When: another frame starts and shutdown is requested before provider release.
    workspace.publish(_physical(2, 45_000, salience=0.95))
    coordinator.notify_perception()
    coordinator.synchronize()
    coordinator.stop()
    joined = Event()
    join_thread = Thread(target=lambda: (coordinator.join(), joined.set()), daemon=True)
    join_thread.start()

    try:
        # Then: the replacement call starts and lifecycle join does not depend on it.
        assert runtime.second_started.wait(0.2)
        assert joined.wait(0.2)
    finally:
        runtime.release.set()
        join_thread.join(timeout=1)


def test_repeated_hung_providers_release_third_frame_with_capacity_failure() -> None:
    # Given: two consecutive provider calls remain alive after hard timeouts.
    workspace = PerceptualWorkspace(ELFIE_ID)
    runtime = BlockingPlanRuntime()
    sink = RecordingPlanSink()
    coordinator, _, _ = _coordinator(workspace, runtime, sink)
    coordinator.start()
    try:
        workspace.publish(_physical(1, 0, salience=0.95))
        coordinator.notify_perception()
        assert runtime.started.wait(1)
        coordinator.post_clock(BrainClockPulse(timestamp=NOW.timestamp() + 46.0))
        coordinator.wait_for_outcome_count(1)

        workspace.publish(_physical(2, 45_000, salience=0.95))
        coordinator.notify_perception()
        assert runtime.second_started.wait(1)
        coordinator.post_clock(BrainClockPulse(timestamp=NOW.timestamp() + 92.0))
        coordinator.wait_for_outcome_count(2)

        # When: a third significant frame reaches the exhausted worker.
        workspace.publish(_physical(3, 90_000, salience=0.95))
        coordinator.notify_perception()
        coordinator.wait_for_outcome_count(3)
        coordinator.synchronize()

        # Then: the frame is replayable and failure is explicit and bounded.
        outcomes = coordinator.outcomes()
        assert tuple(outcome.status for outcome in outcomes) == (
            TerminalStatus.TIMED_OUT,
            TerminalStatus.TIMED_OUT,
            TerminalStatus.FAILED,
        )
        assert outcomes[-1].error_code == "WorkerCapacityError"
        assert len(runtime.calls) == 2
        assert workspace.metrics().reliable_event_count == 1
    finally:
        coordinator.stop()
        coordinator.join()
        runtime.release.set()
