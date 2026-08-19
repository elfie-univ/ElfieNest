from pathlib import Path

from app.interfaces.cli.target_context import CliSession, resolve_cli_target
from app.orchestration.lifecycle.runtime_snapshot import (
    BackendTier,
    RuntimePhase,
    RuntimeSnapshotV1,
    RuntimeTarget,
)
from app.orchestration.lifecycle.target_resolution import EntrypointMode
from infrastructure.platform.source_cli_state import SourceCliState


class _Lifecycle:
    def __init__(self, snapshots: dict[Path, RuntimeSnapshotV1]) -> None:
        self.snapshots = snapshots

    def source_cli_state(self, source_root: Path) -> SourceCliState:
        return SourceCliState(source_root)

    def inspect_data_home(self, explicit_home, **_kwargs):
        from infrastructure.persistence.nest_db.store import inspect_data_home

        return inspect_data_home(Path(explicit_home))

    def runtime_snapshot(self, home):
        return self.snapshots.get(
            Path(home).resolve(),
            RuntimeSnapshotV1(),
        )

    def existing_service_command(self, home, _project_root):
        if Path(home).resolve() in self.snapshots:
            return (1234, ("python", "scripts/serve.py"))
        return None


def _running(instance: str) -> RuntimeSnapshotV1:
    return RuntimeSnapshotV1(
        instance_id=instance,
        tier=BackendTier.CORE_READY,
        phase=RuntimePhase.CORE_READY,
        desired_target=RuntimeTarget.CORE,
    )


def test_source_context_switches_from_explicit_a_to_explicit_b(tmp_path: Path) -> None:
    source = tmp_path / "checkout"
    source.mkdir()
    task_a = tmp_path / "A"
    task_b = tmp_path / "B"
    lifecycle = _Lifecycle(
        {task_a.resolve(): _running("a"), task_b.resolve(): _running("b")}
    )
    session = CliSession()

    first = resolve_cli_target(
        lifecycle,
        command="start",
        mode=EntrypointMode.SOURCE,
        source_root=source,
        invoking_cwd=tmp_path,
        explicit_home=str(task_a),
        session=session,
    )
    second = resolve_cli_target(
        lifecycle,
        command="restart",
        mode=EntrypointMode.SOURCE,
        source_root=source,
        invoking_cwd=tmp_path,
        explicit_home=str(task_b),
        session=session,
    )

    assert first.home == task_a.resolve()
    assert second.home == task_b.resolve()
    assert session.data_home == task_b.resolve()
    assert (
        source / ".elfienest.local" / "runtime" / "cli" / "data-homes.json"
    ).is_file()
    assert not (task_a / "runtime" / "cli").exists()
    assert not (task_b / "runtime" / "cli").exists()


def test_stop_candidate_catalog_survives_idle_default(tmp_path: Path) -> None:
    source = tmp_path / "checkout"
    source.mkdir()
    task = tmp_path / "running-task"
    state = SourceCliState(source)
    state.record_candidate(task)
    lifecycle = _Lifecycle({task.resolve(): _running("task")})
    session = CliSession()

    target = resolve_cli_target(
        lifecycle,
        command="stop",
        mode=EntrypointMode.SOURCE,
        source_root=source,
        invoking_cwd=tmp_path,
        session=session,
        prompt=lambda candidates: candidates[0].home,
    )

    assert target.home == task.resolve()
    assert session.data_home == task.resolve()
