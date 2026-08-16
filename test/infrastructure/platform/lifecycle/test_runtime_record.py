"""Focused tests for the durable Runtime generation record."""

from pathlib import Path

from app.orchestration.lifecycle.runtime_health import (
    ComponentHealth,
    OwnerLease,
    RuntimeComponent,
    RuntimeHealth,
    RuntimeHealthState,
)
from infrastructure.platform.lifecycle.runtime_record import FileRuntimeRecordAdapter


def test_runtime_record_round_trip_and_remove(tmp_path: Path) -> None:
    adapter = FileRuntimeRecordAdapter(tmp_path)
    health = RuntimeHealth(
        state=RuntimeHealthState.DEGRADED,
        generation=3,
        owner_lease=OwnerLease(owner_id="cli", generation=3),
        components=(
            ComponentHealth(
                component=RuntimeComponent.GODOT_AUTHORITY,
                state=RuntimeHealthState.READY,
                detail="ready",
                pid=23,
            ),
        ),
    )

    adapter.write(health)

    assert adapter.read() == health
    assert (tmp_path / "runtime" / "runtime.json").stat().st_mode & 0o777 == 0o600
    adapter.remove()
    assert adapter.read().state is RuntimeHealthState.STOPPED


def test_runtime_record_round_trips_a_transient_startup_owner(tmp_path: Path) -> None:
    adapter = FileRuntimeRecordAdapter(tmp_path)
    health = RuntimeHealth(
        state=RuntimeHealthState.STARTING,
        generation=4,
        owner_lease=None,
        components=(),
        startup_owner_id="desktop-starting",
    )

    adapter.write(health)

    assert adapter.read() == health


def test_runtime_record_rejects_invalid_shape(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "runtime.json").write_text(
        '{"generation": -1, "state": "ready", "components": []}',
        encoding="utf-8",
    )

    record = FileRuntimeRecordAdapter(tmp_path).read()

    assert record.state is RuntimeHealthState.FAILED
    assert record.owner_lease is None


def test_runtime_record_rejects_untyped_component_fields(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "runtime.json").write_text(
        '{"generation": 1, "owner_id": "cli", "state": "ready", '
        '"components": [{"component": "core", "state": "ready", '
        '"detail": [], "pid": "23"}]}',
        encoding="utf-8",
    )

    record = FileRuntimeRecordAdapter(tmp_path).read()

    assert record.state is RuntimeHealthState.FAILED
    assert record.components == ()
