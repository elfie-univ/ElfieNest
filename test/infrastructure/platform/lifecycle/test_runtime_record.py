from dataclasses import replace
from pathlib import Path

import pytest

from app.orchestration.lifecycle.runtime_snapshot import (
    BackendTier,
    ComponentSnapshot,
    ComponentState,
    OwnerLease,
    RuntimeComponent,
    RuntimePhase,
    RuntimeSnapshotV1,
    RuntimeTarget,
)
from app.orchestration.lifecycle.types import SnapshotRecoveryRequiredError
from infrastructure.platform.lifecycle.runtime_record import FileRuntimeRecordAdapter


def _snapshot() -> RuntimeSnapshotV1:
    return RuntimeSnapshotV1(
        instance_id="instance-1",
        generation=3,
        revision=1,
        tier=BackendTier.WORLD_READY,
        phase=RuntimePhase.WORLD_READY,
        desired_target=RuntimeTarget.NORMAL,
        reached_target=RuntimeTarget.WORLD,
        owner_lease=OwnerLease("cli", 3),
        components=(
            ComponentSnapshot(
                component=RuntimeComponent.GODOT_AUTHORITY,
                state=ComponentState.READY,
                detail="ready",
                pid=23,
                executable="/bin/godot",
                birth_identity="birth-23",
            ),
        ),
    )


def test_runtime_record_round_trip_and_retain_offline_snapshot(tmp_path: Path) -> None:
    adapter = FileRuntimeRecordAdapter(tmp_path)
    handoff = adapter.begin_writer_handoff(generation=3, owner_id="cli")
    snapshot = replace(_snapshot(), writer_credential_digest=handoff.digest)

    adapter.write(snapshot)

    assert adapter.read() == snapshot
    assert (tmp_path / "runtime" / "runtime.json").stat().st_mode & 0o777 == 0o600
    offline = replace(
        snapshot,
        revision=2,
        generation=3,
        tier=BackendTier.OFFLINE,
        phase=RuntimePhase.OFFLINE,
        owner_lease=None,
        reached_target=None,
        components=(),
    )
    adapter.write(offline)
    assert adapter.read() == offline


def test_runtime_record_initializes_only_an_empty_root(tmp_path: Path) -> None:
    adapter = FileRuntimeRecordAdapter(tmp_path)

    snapshot = adapter.initialize_if_fresh()

    assert snapshot.instance_id != "uninitialized"
    assert snapshot.tier is BackendTier.OFFLINE
    assert snapshot.phase is RuntimePhase.OFFLINE


def test_existing_root_without_snapshot_requires_explicit_recovery(
    tmp_path: Path,
) -> None:
    (tmp_path / "database.sqlite").write_text("existing", encoding="utf-8")
    adapter = FileRuntimeRecordAdapter(tmp_path)

    with pytest.raises(SnapshotRecoveryRequiredError):
        adapter.initialize_if_fresh()

    assert adapter.read().phase is RuntimePhase.RECOVERY_REQUIRED


def test_runtime_record_does_not_treat_stale_runtime_artifacts_as_fresh(
    tmp_path: Path,
) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "stale.log").write_text("leftover", encoding="utf-8")
    adapter = FileRuntimeRecordAdapter(tmp_path)

    with pytest.raises(SnapshotRecoveryRequiredError):
        adapter.initialize_if_fresh()


def test_runtime_record_initializes_after_lifecycle_prepares_existing_root(
    tmp_path: Path,
) -> None:
    # Given: the data preparation step has already validated the existing root.
    (tmp_path / "nest.db").write_bytes(b"prepared")
    adapter = FileRuntimeRecordAdapter(tmp_path)

    # When: Runtime receives the explicit prepared-root handoff.
    snapshot = adapter.initialize_if_fresh(allow_existing_root=True)

    # Then: the authoritative initial state is the existing OFFLINE state.
    assert snapshot.instance_id != "uninitialized"
    assert snapshot.tier is BackendTier.OFFLINE
    assert snapshot.phase is RuntimePhase.OFFLINE


def test_runtime_record_rejects_invalid_shape(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "runtime.json").write_text(
        '{"schema_version": 1, "instance_id": "x", "generation": -1, '
        '"revision": 0, "tier": "offline", "phase": "offline", '
        '"desired_target": "core", "components": []}',
        encoding="utf-8",
    )

    record = FileRuntimeRecordAdapter(tmp_path).read()

    assert record.phase is RuntimePhase.RECOVERY_REQUIRED
    assert record.owner_lease is None


def test_runtime_record_rejects_untyped_component_fields(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "runtime.json").write_text(
        '{"schema_version": 1, "instance_id": "x", "generation": 1, '
        '"revision": 0, "tier": "world_ready", "phase": "world_ready", '
        '"desired_target": "normal", "components": [{"component": "core", '
        '"state": "ready", "detail": [], "pid": "23"}]}',
        encoding="utf-8",
    )

    record = FileRuntimeRecordAdapter(tmp_path).read()

    assert record.phase is RuntimePhase.RECOVERY_REQUIRED
    assert record.components == ()


def test_runtime_record_requires_generation_writer_handoff(tmp_path: Path) -> None:
    parent = FileRuntimeRecordAdapter(tmp_path)
    initial = parent.initialize_if_fresh()
    handoff = parent.begin_writer_handoff(generation=1, owner_id="core")
    active = replace(
        initial,
        revision=1,
        generation=1,
        phase=RuntimePhase.CORE_STARTING,
        writer_credential_digest=handoff.digest,
    )
    parent.write(active)

    child = FileRuntimeRecordAdapter(tmp_path, writer_token=handoff.token)
    child.write(replace(active, revision=2, phase=RuntimePhase.CORE_READY))

    stale = FileRuntimeRecordAdapter(tmp_path, writer_token="stale-token")
    with pytest.raises(PermissionError):
        stale.write(replace(active, revision=3, phase=RuntimePhase.FAILED))


def test_revoked_writer_cannot_reactivate_an_offline_record(tmp_path: Path) -> None:
    parent = FileRuntimeRecordAdapter(tmp_path)
    initial = parent.initialize_if_fresh()
    handoff = parent.begin_writer_handoff(generation=1, owner_id="core")
    active = replace(
        initial,
        revision=1,
        generation=1,
        tier=BackendTier.CORE_READY,
        phase=RuntimePhase.CORE_READY,
        writer_credential_digest=handoff.digest,
    )
    parent.write(active)
    child = FileRuntimeRecordAdapter(tmp_path, writer_token=handoff.token)
    parent.write(
        replace(
            active,
            revision=2,
            tier=BackendTier.OFFLINE,
            phase=RuntimePhase.OFFLINE,
            writer_credential_digest=None,
        )
    )
    parent.revoke_writer_handoff()

    with pytest.raises(PermissionError):
        child.write(replace(active, revision=3, phase=RuntimePhase.CORE_READY))

    assert not (tmp_path / "runtime" / "writer.token").exists()
