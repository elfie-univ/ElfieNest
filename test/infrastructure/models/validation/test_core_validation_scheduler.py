from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from app.features.configuration.food import (
    StoredElfieFoodAssignment,
    StoredFoodPackage,
)
from infrastructure.models.validation.core_validation_scheduler import (
    CoreValidationScheduler,
    CoreValidationTask,
)
from infrastructure.models.validation.serving_food import (
    CoreEndpointRoute,
    ServingFoodIndex,
    build_serving_food_index,
)

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)


def _index(generation: str = "g1") -> ServingFoodIndex:
    return ServingFoodIndex(
        generation=generation,
        foods=(),
        core_endpoints=(
            CoreEndpointRoute(
                reference="cloud/main",
                food_ids=("food_common",),
                roles=("primary", "vision"),
            ),
        ),
    )


class _State:
    status = "unknown"
    observed_at = None


def test_scheduler_only_runs_current_core_channels_and_deduplicates(tmp_path) -> None:
    calls: list[tuple[str, str]] = []
    scheduler = CoreValidationScheduler(
        tmp_path / "lease.lock",
        lambda reference, channel: calls.append((reference, channel)) or "ok",
    )

    result = scheduler.run_due(_index(), lambda _reference, _channel: _State(), now=NOW)

    assert result.acquired is True
    assert {(item.reference, item.channel) for item in result.attempted} == {
        ("cloud/main", "text"),
        ("cloud/main", "vision"),
    }
    assert calls == [
        ("cloud/main", "text"),
        ("cloud/main", "vision"),
    ]


def test_scheduler_skips_fresh_available_core_state(tmp_path) -> None:
    class Fresh:
        status = "available"
        observed_at = (NOW - timedelta(hours=1)).isoformat()

    calls: list[tuple[str, str]] = []
    scheduler = CoreValidationScheduler(
        tmp_path / "lease.lock",
        lambda reference, channel: calls.append((reference, channel)),
    )

    result = scheduler.run_due(_index(), lambda _reference, _channel: Fresh(), now=NOW)

    assert result.attempted == ()
    assert calls == []


def test_scheduler_honors_channel_evidence_expiry_independently(tmp_path) -> None:
    class FreshText:
        status = "available"
        observed_at = (NOW - timedelta(hours=1)).isoformat()
        expires_at = (NOW + timedelta(hours=23)).isoformat()

    class FreshCapability:
        status = "unknown"
        observed_at = (NOW - timedelta(minutes=1)).isoformat()
        expires_at = (NOW + timedelta(minutes=4)).isoformat()

    calls: list[tuple[str, str]] = []
    scheduler = CoreValidationScheduler(
        tmp_path / "lease.lock",
        lambda reference, channel: calls.append((reference, channel)),
    )

    result = scheduler.run_due(
        _index(),
        lambda _reference, channel: (
            FreshText() if channel == "text" else FreshCapability()
        ),
        now=NOW,
    )

    assert result.attempted == ()
    assert calls == []


def test_scheduler_skips_deterministic_account_and_lifecycle_blockers(tmp_path) -> None:
    class Blocked:
        status = "unavailable"
        reason_code = "billing_blocked"
        observed_at = NOW.isoformat()

    calls: list[tuple[str, str]] = []
    scheduler = CoreValidationScheduler(
        tmp_path / "lease.lock",
        lambda reference, channel: calls.append((reference, channel)),
    )

    result = scheduler.run_due(
        _index(), lambda _reference, _channel: Blocked(), now=NOW
    )

    assert result.attempted == ()
    assert calls == []


def test_scheduler_uses_cross_process_lease_and_does_not_overlap(tmp_path) -> None:
    entered = threading.Event()
    release = threading.Event()
    first_result = []
    lease_path = tmp_path / "lease.lock"

    def validate(_reference: str, _channel: str) -> str:
        entered.set()
        release.wait(timeout=2)
        return "ok"

    first = CoreValidationScheduler(lease_path, validate)
    second = CoreValidationScheduler(lease_path, lambda *_args: "second")
    worker = threading.Thread(
        target=lambda: first_result.append(
            first.run_due(_index(), lambda *_args: _State(), now=NOW)
        )
    )
    worker.start()
    assert entered.wait(timeout=2)

    second_result = second.run_due(_index(), lambda *_args: _State(), now=NOW)
    release.set()
    worker.join(timeout=2)

    assert second_result.acquired is False
    assert first_result[0].acquired is True


def test_generation_change_cancels_queued_work(tmp_path) -> None:
    current = [_index("g1")]
    calls: list[tuple[str, str]] = []

    def validate(reference: str, channel: str) -> str:
        calls.append((reference, channel))
        current[0] = _index("g2")
        return "ok"

    scheduler = CoreValidationScheduler(
        tmp_path / "lease.lock",
        validate,
        current_index=lambda: current[0],
    )
    result = scheduler.run_due(_index("g1"), lambda *_args: _State(), now=NOW)

    assert len(result.attempted) == 1
    assert len(result.cancelled) == 1
    assert result.cancelled[0].channel == "vision"
    assert calls == [("cloud/main", "text")]


def test_food_edit_invalidates_in_flight_generation_and_next_generation_runs(
    tmp_path,
) -> None:
    def food_index(primary: str) -> ServingFoodIndex:
        return build_serving_food_index(
            (
                StoredFoodPackage(
                    food_id="food-serving",
                    display_name="Food serving",
                    primary_model=primary,
                    vision_model="cloud/vision",
                    required_roles=frozenset({"vision"}),
                ),
            ),
            (StoredElfieFoodAssignment("elfie-1", 7, "food-serving"),),
            default_food_id="food-serving",
            emergency_food_id="food-serving",
            now=NOW,
        )

    current = [food_index("cloud/main")]
    started = threading.Event()
    edited = threading.Event()
    calls: list[tuple[str, str]] = []

    def validate(reference: str, channel: str) -> str:
        calls.append((reference, channel))
        if len(calls) == 1:
            started.set()
            assert edited.wait(timeout=2)
        return "ok"

    def edit_food() -> None:
        assert started.wait(timeout=2)
        current[0] = food_index("cloud/edited")
        edited.set()

    editor = threading.Thread(target=edit_food)
    editor.start()
    scheduler = CoreValidationScheduler(
        tmp_path / "lease.lock",
        validate,
        current_index=lambda: current[0],
    )

    first = scheduler.run_due(
        current[0], lambda _reference, _channel: _State(), now=NOW
    )
    editor.join(timeout=2)

    assert first.attempted == (
        CoreValidationTask("cloud/main", "text", first.generation),
    )
    assert first.cancelled == (
        CoreValidationTask("cloud/vision", "text", first.generation),
        CoreValidationTask("cloud/vision", "vision", first.generation),
    )
    assert calls == [("cloud/main", "text")]
    assert current[0].generation != first.generation

    second = scheduler.run_due(
        current[0], lambda _reference, _channel: _State(), now=NOW
    )

    assert {(task.reference, task.channel) for task in second.attempted} == {
        ("cloud/edited", "text"),
        ("cloud/vision", "text"),
        ("cloud/vision", "vision"),
    }
    assert all(task.generation == current[0].generation for task in second.attempted)


def test_scheduler_keeps_other_core_channels_after_one_probe_errors(tmp_path) -> None:
    calls: list[tuple[str, str]] = []

    def validate(reference: str, channel: str) -> str:
        calls.append((reference, channel))
        if channel == "text":
            raise RuntimeError("provider temporarily unavailable")
        return "ok"

    scheduler = CoreValidationScheduler(
        tmp_path / "lease.lock",
        validate,
    )

    result = scheduler.run_due(_index(), lambda *_args: _State(), now=NOW)

    assert result.acquired is True
    assert calls == [
        ("cloud/main", "text"),
        ("cloud/main", "vision"),
    ]
    assert len(result.attempted) == 2
    assert isinstance(result.results[result.attempted[0]], RuntimeError)
