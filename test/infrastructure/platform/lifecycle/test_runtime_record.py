import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from app.orchestration.lifecycle.ports import LifecycleLocalPaths
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
from infrastructure.platform.lifecycle import runtime_record
from infrastructure.platform.lifecycle.runtime_record import FileRuntimeRecordAdapter


def _paths(home: Path) -> LifecycleLocalPaths:
    home = home.resolve(strict=False)
    return LifecycleLocalPaths(
        home=home,
        logs=home / "logs",
        model_validations=home / "reports" / "model-validations",
        runtime_validations=home / "reports" / "runtime-validations",
        runtime_state=home / "runtime" / "runtime.json",
        runtime_locks=home / "runtime" / "locks",
        source_cli_state=home / "runtime" / "cli",
    )


def _adapter(home: Path, *, writer_token=None) -> FileRuntimeRecordAdapter:
    return FileRuntimeRecordAdapter(_paths(home), writer_token=writer_token)


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
    adapter = _adapter(tmp_path)
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

    history_path = tmp_path / "logs" / "lifecycle-history.jsonl"
    history = [
        json.loads(line)
        for line in history_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [item["phase"] for item in history] == ["world_ready", "offline"]
    assert [item["revision"] for item in history] == [1, 2]
    assert history[-1]["previous_phase"] == "world_ready"
    assert history[-1]["process_role"] == "cli"
    assert "detail" not in history[-1]
    assert history_path.stat().st_mode & 0o777 == 0o600


def test_runtime_record_skips_posix_fchmod_on_windows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: Windows does not provide the POSIX fchmod operation.
    def unsupported_fchmod(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Windows must not call POSIX-only fchmod")

    real_os = runtime_record.os

    class WindowsOsProxy:
        name = "nt"

        def __getattr__(self, attribute: str):
            return getattr(real_os, attribute)

        @staticmethod
        def fchmod(*_args: object, **_kwargs: object) -> None:
            unsupported_fchmod()

    monkeypatch.setattr(runtime_record, "os", WindowsOsProxy())

    # When: Runtime writes its first snapshot and writer credential.
    adapter = _adapter(tmp_path)
    handoff = adapter.begin_writer_handoff(generation=0, owner_id="cli")
    snapshot = replace(
        _snapshot(), generation=0, writer_credential_digest=handoff.digest
    )
    adapter.write(snapshot)

    # Then: the runtime snapshot is written without the POSIX-only call.
    assert adapter.read() == snapshot


def test_runtime_record_initializes_only_an_empty_root(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)

    snapshot = adapter.initialize_if_fresh()

    assert snapshot.instance_id != "uninitialized"
    assert snapshot.tier is BackendTier.OFFLINE
    assert snapshot.phase is RuntimePhase.OFFLINE


def test_existing_root_without_snapshot_requires_explicit_recovery(
    tmp_path: Path,
) -> None:
    (tmp_path / "database.sqlite").write_text("existing", encoding="utf-8")
    adapter = _adapter(tmp_path)

    with pytest.raises(SnapshotRecoveryRequiredError):
        adapter.initialize_if_fresh()

    assert adapter.read().phase is RuntimePhase.RECOVERY_REQUIRED


def test_runtime_record_does_not_treat_stale_runtime_artifacts_as_fresh(
    tmp_path: Path,
) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "stale.log").write_text("leftover", encoding="utf-8")
    adapter = _adapter(tmp_path)

    with pytest.raises(SnapshotRecoveryRequiredError):
        adapter.initialize_if_fresh()


def test_runtime_record_ignores_optional_source_cli_state_when_checking_freshness(
    tmp_path: Path,
) -> None:
    cli_dir = tmp_path / "runtime" / "cli"
    cli_dir.mkdir(parents=True)
    (cli_dir / "data-homes.json").write_text(
        '{"version": 1, "homes": []}\n', encoding="utf-8"
    )
    adapter = _adapter(tmp_path)

    snapshot = adapter.initialize_if_fresh()

    assert snapshot.tier is BackendTier.OFFLINE
    assert (tmp_path / "runtime" / "runtime.json").is_file()
    assert (cli_dir / "data-homes.json").is_file()


def test_runtime_record_does_not_depend_on_source_cli_state_after_initialization(
    tmp_path: Path,
) -> None:
    cli_dir = tmp_path / "runtime" / "cli"
    cli_dir.mkdir(parents=True)
    history = cli_dir / "history"
    history.write_text("status\n", encoding="utf-8")
    adapter = _adapter(tmp_path)
    snapshot = adapter.initialize_if_fresh()

    history.unlink()
    cli_dir.rmdir()

    assert adapter.read() == snapshot


def test_runtime_record_rejects_non_directory_source_cli_state(
    tmp_path: Path,
) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "cli").write_text("not a directory", encoding="utf-8")
    adapter = _adapter(tmp_path)

    with pytest.raises(SnapshotRecoveryRequiredError):
        adapter.initialize_if_fresh()


@pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privileges")
def test_runtime_record_rejects_symlinked_source_cli_state(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    outside = tmp_path / "outside"
    runtime_dir.mkdir()
    outside.mkdir()
    (runtime_dir / "cli").symlink_to(outside, target_is_directory=True)
    adapter = _adapter(tmp_path)

    with pytest.raises(SnapshotRecoveryRequiredError):
        adapter.initialize_if_fresh()


@pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privileges")
def test_runtime_record_rejects_symlinked_runtime_directory(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "runtime").symlink_to(outside, target_is_directory=True)
    adapter = _adapter(tmp_path)

    with pytest.raises(SnapshotRecoveryRequiredError):
        adapter.initialize_if_fresh()


def test_runtime_record_initializes_after_lifecycle_prepares_existing_root(
    tmp_path: Path,
) -> None:
    # Given: the data preparation step has already validated the existing root.
    (tmp_path / "nest.db").write_bytes(b"prepared")
    adapter = _adapter(tmp_path)

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

    record = _adapter(tmp_path).read()

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

    record = _adapter(tmp_path).read()

    assert record.phase is RuntimePhase.RECOVERY_REQUIRED
    assert record.components == ()


def test_runtime_record_requires_generation_writer_handoff(tmp_path: Path) -> None:
    parent = _adapter(tmp_path)
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

    child = _adapter(tmp_path, writer_token=handoff.token)
    child.write(replace(active, revision=2, phase=RuntimePhase.CORE_READY))

    stale = _adapter(tmp_path, writer_token="stale-token")
    with pytest.raises(PermissionError):
        stale.write(replace(active, revision=3, phase=RuntimePhase.FAILED))


def test_revoked_writer_cannot_reactivate_an_offline_record(tmp_path: Path) -> None:
    parent = _adapter(tmp_path)
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
    child = _adapter(tmp_path, writer_token=handoff.token)
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
