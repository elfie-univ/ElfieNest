from __future__ import annotations

from pathlib import Path

from app.orchestration.lifecycle.runtime_health import (
    ComponentHealth,
    RuntimeComponent,
    RuntimeHealth,
    RuntimeHealthState,
)
from app.orchestration.lifecycle.runtime_supervisor import RuntimeSupervisor
from app.orchestration.lifecycle.types import LaunchFailedError, ServiceLifecycleResult
from godot_runtime import launcher as authority_launcher


def _health(
    *,
    authority: RuntimeHealthState = RuntimeHealthState.READY,
    ollama: RuntimeHealthState = RuntimeHealthState.READY,
) -> RuntimeHealth:
    return RuntimeHealth(
        state=RuntimeHealthState.READY,
        generation=0,
        owner_lease=None,
        components=(
            ComponentHealth(RuntimeComponent.CORE, RuntimeHealthState.READY),
            ComponentHealth(RuntimeComponent.GATEWAY, RuntimeHealthState.READY),
            ComponentHealth(RuntimeComponent.GODOT_AUTHORITY, authority),
            ComponentHealth(RuntimeComponent.OLLAMA, ollama),
        ),
    )


def test_start_records_one_generation_and_degrades_only_for_ollama(
    tmp_path: Path,
) -> None:
    # Given: Core starts successfully while the optional configured Ollama is absent.
    starts: list[bool] = []
    supervisor = RuntimeSupervisor(
        elfie_home=tmp_path / "home",
        project_root=tmp_path / "project",
        health_probe=lambda: _health(ollama=RuntimeHealthState.FAILED),
        start_core=lambda healthy: (
            starts.append(healthy())
            or ServiceLifecycleResult(status="started", pid=7101)
        ),
        stop_core=lambda: ServiceLifecycleResult(status="stopped", pid=7101),
    )

    # When: one owner starts the complete Runtime.
    result = supervisor.start(owner_id="cli")

    # Then: the record binds the generation and owner atomically after full health.
    assert result.status == "started"
    assert starts == [True]
    health = supervisor.status()
    assert health.state is RuntimeHealthState.DEGRADED
    assert health.generation == 1
    assert health.owner_lease is not None
    assert health.owner_lease.owner_id == "cli"
    assert health.component(RuntimeComponent.OLLAMA).state is RuntimeHealthState.FAILED


def test_start_rejects_misleading_http_health_when_authority_is_failed(
    tmp_path: Path,
) -> None:
    # Given: the HTTP server responds but the authority handshake is not ready.
    starts: list[bool] = []
    supervisor = RuntimeSupervisor(
        elfie_home=tmp_path / "home",
        project_root=tmp_path / "project",
        health_probe=lambda: _health(authority=RuntimeHealthState.FAILED),
        start_core=lambda healthy: (
            starts.append(healthy())
            or ServiceLifecycleResult(status="failed", pid=7102)
        ),
        stop_core=lambda: ServiceLifecycleResult(status="already_stopped"),
    )

    # When: the supervisor evaluates full Runtime readiness.
    result = supervisor.start(owner_id="cli")

    # Then: authority failure is fatal instead of being accepted as HTTP 200 health.
    assert result.status == "failed"
    assert starts == [True]
    assert supervisor.status().state is RuntimeHealthState.FAILED


def test_stop_preserves_public_ollama_and_clears_owned_runtime_record(
    tmp_path: Path,
) -> None:
    # Given: a started Runtime has an externally owned Ollama component.
    stops: list[str] = []
    supervisor = RuntimeSupervisor(
        elfie_home=tmp_path / "home",
        project_root=tmp_path / "project",
        health_probe=_health,
        start_core=lambda healthy: ServiceLifecycleResult(status="started", pid=7103),
        stop_core=lambda: (
            stops.append("core") or ServiceLifecycleResult(status="stopped", pid=7103)
        ),
    )
    supervisor.start(owner_id="cli")

    # When: the owner stops the Runtime.
    result = supervisor.stop()

    # Then: only owned components are stopped and the public Ollama is never signalled.
    assert result.status == "stopped"
    assert stops == ["core"]
    assert supervisor.status().state is RuntimeHealthState.STOPPED


def test_existing_runtime_without_a_legacy_record_is_adopted_as_generation_one(
    tmp_path: Path,
) -> None:
    # Given: Core predates the component-record migration but verifies as ready.
    supervisor = RuntimeSupervisor(
        elfie_home=tmp_path / "home",
        project_root=tmp_path / "project",
        health_probe=_health,
        start_core=lambda healthy: ServiceLifecycleResult(
            status="already_running", pid=7104
        ),
        stop_core=lambda: ServiceLifecycleResult(status="already_stopped"),
    )

    # When: the unified supervisor attaches to it.
    result = supervisor.start(owner_id="cli")

    # Then: it establishes a valid first ownership generation rather than zero.
    assert result.status == "already_running"
    assert supervisor.status().generation == 1


def test_start_launches_authority_after_core_and_waits_for_full_health(
    tmp_path: Path,
) -> None:
    # Given: Core/Gateway become ready before the authority handshake does.
    observations = iter(
        (
            _health(authority=RuntimeHealthState.FAILED),
            _health(authority=RuntimeHealthState.FAILED),
            _health(authority=RuntimeHealthState.READY),
            _health(authority=RuntimeHealthState.READY),
            _health(authority=RuntimeHealthState.READY),
        )
    )
    calls: list[str] = []
    authority = type("AuthorityProcess", (), {"pid": 7105})()
    supervisor = RuntimeSupervisor(
        elfie_home=tmp_path / "home",
        project_root=tmp_path / "project",
        health_probe=lambda: next(observations),
        start_core=lambda healthy: (
            calls.append("core")
            or (healthy() and ServiceLifecycleResult(status="started", pid=7104))
        ),
        stop_core=lambda: ServiceLifecycleResult(status="stopped", pid=7104),
        start_authority=lambda: calls.append("authority") or authority,
        stop_authority=lambda process: calls.append(f"stop:{process.pid}"),
    )

    # When: unified start is requested.
    result = supervisor.start(owner_id="cli")

    # Then: authority launch follows Core readiness and the full contract gates success.
    assert result.status == "started"
    assert calls == ["core", "authority"]
    assert supervisor.status().component(RuntimeComponent.GODOT_AUTHORITY).pid == 7105


def test_authority_launch_failure_stops_the_started_core(tmp_path: Path) -> None:
    # Given: Core/Gateway are ready but no exported authority Runtime can launch.
    calls: list[str] = []
    supervisor = RuntimeSupervisor(
        elfie_home=tmp_path / "home",
        project_root=tmp_path / "project",
        health_probe=lambda: _health(authority=RuntimeHealthState.FAILED),
        start_core=lambda healthy: (
            calls.append("core")
            or (healthy() and ServiceLifecycleResult(status="started", pid=7106))
        ),
        stop_core=lambda: (
            calls.append("stop-core")
            or ServiceLifecycleResult(status="stopped", pid=7106)
        ),
        start_authority=lambda: None,
        stop_authority=lambda process: calls.append("stop-authority"),
    )

    # When: authority launch fails after Core startup.
    result = supervisor.start(owner_id="cli")

    # Then: Core is cleaned up and the operation reports a typed launch failure.
    assert result.status == "failed"
    assert isinstance(result.error, LaunchFailedError)
    assert calls == ["core", "stop-core"]


def test_typed_authority_launch_failure_is_preserved_by_supervisor(
    tmp_path: Path,
) -> None:
    # Given: host selection identifies the exact missing authority artifact.
    calls: list[str] = []

    def fail_authority():
        raise authority_launcher.AuthorityLaunchError(
            kind=authority_launcher.AuthorityLaunchFailureKind.MISSING_ARTIFACT,
            detail="missing Linux Dedicated authority",
            target=tmp_path / "ElfieNestRuntime",
        )

    supervisor = RuntimeSupervisor(
        elfie_home=tmp_path / "home",
        project_root=tmp_path / "project",
        health_probe=lambda: _health(authority=RuntimeHealthState.FAILED),
        start_core=lambda healthy: (
            calls.append("core")
            or (healthy() and ServiceLifecycleResult(status="started", pid=7108))
        ),
        stop_core=lambda: (
            calls.append("stop-core")
            or ServiceLifecycleResult(status="stopped", pid=7108)
        ),
        start_authority=fail_authority,
    )

    # When: the unified supervisor starts its authority.
    result = supervisor.start(owner_id="cli")

    # Then: cleanup runs and the typed diagnostic reaches the lifecycle result.
    assert result.status == "failed"
    assert isinstance(result.error, LaunchFailedError)
    assert "missing Linux Dedicated authority" in str(result.error)
    assert calls == ["core", "stop-core"]


def test_authority_readiness_timeout_stops_authority_before_core(
    tmp_path: Path,
) -> None:
    # Given: authority starts but never completes its declared handshake.
    from test.app.orchestration.lifecycle.service_fakes import FakeClock

    clock = FakeClock()
    calls: list[str] = []
    authority = type("AuthorityProcess", (), {"pid": 7107})()
    supervisor = RuntimeSupervisor(
        elfie_home=tmp_path / "home",
        project_root=tmp_path / "project",
        health_probe=lambda: _health(authority=RuntimeHealthState.FAILED),
        start_core=lambda healthy: (
            calls.append("core")
            or (healthy() and ServiceLifecycleResult(status="started", pid=7106))
        ),
        stop_core=lambda: (
            calls.append("stop-core")
            or ServiceLifecycleResult(status="stopped", pid=7106)
        ),
        start_authority=lambda: calls.append("authority") or authority,
        stop_authority=lambda process: calls.append(f"stop-authority:{process.pid}"),
        authority_timeout_seconds=0.2,
        monotonic=clock.monotonic,
        sleeper=clock.sleep,
    )

    # When: full health does not become ready before the bounded timeout.
    result = supervisor.start(owner_id="cli")

    # Then: the owned authority is stopped before its Core parent is cleaned up.
    assert result.status == "failed"
    assert isinstance(result.error, LaunchFailedError)
    assert calls == ["core", "authority", "stop-authority:7107", "stop-core"]


def test_new_supervisor_invocation_stops_only_the_recorded_authority_pid(
    tmp_path: Path,
) -> None:
    # Given: a previous CLI invocation persisted its owned authority PID.
    home = tmp_path / "home"
    authority = type("AuthorityProcess", (), {"pid": 7109})()
    starter = RuntimeSupervisor(
        elfie_home=home,
        project_root=tmp_path / "project",
        health_probe=_health,
        start_core=lambda healthy: ServiceLifecycleResult(status="started", pid=7108),
        stop_core=lambda: ServiceLifecycleResult(status="stopped", pid=7108),
        start_authority=lambda: authority,
        stop_authority=lambda _process: None,
    )
    starter.start(owner_id="cli")
    stopped: list[int | str] = []
    stopper = RuntimeSupervisor(
        elfie_home=home,
        project_root=tmp_path / "project",
        health_probe=_health,
        start_core=lambda healthy: ServiceLifecycleResult(
            status="already_running", pid=7108
        ),
        stop_core=lambda: (
            stopped.append("core") or ServiceLifecycleResult(status="stopped", pid=7108)
        ),
        stop_authority=lambda process: stopped.append(process.pid),
    )

    # When: a later CLI invocation stops the same generation.
    result = stopper.stop()

    # Then: it targets exactly the persisted authority PID before Core.
    assert result.status == "stopped"
    assert stopped == [7109, "core"]


def test_repeated_start_preserves_the_ready_generation_and_authority_pid(
    tmp_path: Path,
) -> None:
    # Given: one CLI invocation already owns a fully ready Runtime generation.
    home = tmp_path / "home"
    authority = type("AuthorityProcess", (), {"pid": 7110})()
    first = RuntimeSupervisor(
        elfie_home=home,
        project_root=tmp_path / "project",
        health_probe=_health,
        start_core=lambda healthy: ServiceLifecycleResult(status="started", pid=7111),
        stop_core=lambda: ServiceLifecycleResult(status="stopped", pid=7111),
        start_authority=lambda: authority,
        stop_authority=lambda _process: None,
    )
    first.start(owner_id="cli")
    second_authority_starts: list[str] = []
    repeated = RuntimeSupervisor(
        elfie_home=home,
        project_root=tmp_path / "project",
        health_probe=_health,
        start_core=lambda healthy: ServiceLifecycleResult(
            status="already_running", pid=7111
        ),
        stop_core=lambda: ServiceLifecycleResult(status="stopped", pid=7111),
        start_authority=lambda: second_authority_starts.append("authority") or None,
        stop_authority=lambda _process: None,
    )

    # When: start is requested again from a new CLI process.
    result = repeated.start(owner_id="cli")

    # Then: it keeps the existing generation and never launches a second authority.
    assert result.status == "already_running"
    assert second_authority_starts == []
    receipt = repeated._read_record()
    assert receipt.generation == 1
    assert receipt.component(RuntimeComponent.GODOT_AUTHORITY).pid == 7110
