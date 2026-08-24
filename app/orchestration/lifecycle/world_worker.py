"""Core-resident World convergence for the Runtime lifecycle."""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager, nullcontext
from dataclasses import replace
from typing import Callable, Iterator, Optional

from app.orchestration.lifecycle.ports import (
    AuthorityHostPort,
    AuthorityProcess,
    LifecycleLease,
    RuntimeRecordPort,
)
from app.orchestration.lifecycle.runtime_snapshot import (
    BackendTier,
    ComponentSnapshot,
    ComponentState,
    FailureSnapshot,
    RuntimeComponent,
    RuntimePhase,
    RuntimeSnapshotV1,
    RuntimeTarget,
    TimingSnapshot,
)

WorldReadyProbe = Callable[[], bool]
CommandLeaseFactory = Callable[[], LifecycleLease]
WORLD_RETRY_DELAY_SECONDS = 10.0
WORLD_START_MAX_ATTEMPTS = 3
WORLD_DISCONNECT_GRACE_SECONDS = 10.0
diagnostic_logger = logging.getLogger("elfienest.diagnostics.lifecycle")


class RuntimeWorldWorker:
    """Converge Godot after Core readiness without blocking the entrypoint.

    The worker lives inside the long-running Core process.  It is therefore
    allowed to own the Godot child for the same generation, while the
    launching CLI/Desktop process can return as soon as ``CORE_READY`` is
    durable.
    """

    def __init__(
        self,
        *,
        runtime_record: RuntimeRecordPort,
        authority_host: AuthorityHostPort,
        world_ready_probe: WorldReadyProbe,
        authority_timeout_seconds: float = 120.0,
        poll_interval_seconds: float = 0.1,
        retry_delay_seconds: float = WORLD_RETRY_DELAY_SECONDS,
        max_attempts: int = WORLD_START_MAX_ATTEMPTS,
        world_disconnect_grace_seconds: float = WORLD_DISCONNECT_GRACE_SECONDS,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        command_lease_factory: Optional[CommandLeaseFactory] = None,
    ) -> None:
        self._runtime_record = runtime_record
        self._authority_host = authority_host
        self._world_ready_probe = world_ready_probe
        self._authority_timeout_seconds = authority_timeout_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._retry_delay_seconds = max(0.0, retry_delay_seconds)
        self._max_attempts = max(1, max_attempts)
        self._world_disconnect_grace_seconds = max(0.0, world_disconnect_grace_seconds)
        self._monotonic = monotonic
        self._sleeper = sleeper
        self._command_lease_factory = command_lease_factory
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._authority_process: Optional[AuthorityProcess] = None
        self._authority_lock = threading.Lock()

    def start(self) -> None:
        """Start one daemon worker; repeated calls are idempotent."""
        thread = self._thread
        if thread is not None and thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="ElfieNest-World-Convergence",
            daemon=True,
        )
        self._thread.start()

    def stop(self, *, timeout_seconds: float = 2.0) -> Optional[str]:
        """Request cancellation and publish whether the World child was released."""
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(0.0, timeout_seconds))
        worker_error = (
            "World convergence worker did not stop within its shutdown budget"
            if thread is not None and thread.is_alive()
            else None
        )
        authority_error = self._stop_authority()
        detail = worker_error or authority_error
        self._publish_stop_result(detail)
        return detail

    def _run(self) -> None:
        attempts = 0
        while not self._stop_event.is_set():
            snapshot = self._runtime_record.read()
            if snapshot.phase is RuntimePhase.RECOVERY_REQUIRED:
                return
            if snapshot.phase in {
                RuntimePhase.QUIESCING,
                RuntimePhase.WORLD_STOPPING,
                RuntimePhase.CORE_STOPPING,
                RuntimePhase.OFFLINE,
            }:
                self._stop_authority()
                return
            if (
                snapshot.tier is BackendTier.CORE_READY
                and snapshot.owner_lease is not None
                and snapshot.desired_target.rank >= RuntimeTarget.WORLD.rank
            ):
                self._converge(snapshot)
            latest = self._runtime_record.read()
            if latest.tier is BackendTier.WORLD_READY:
                self._watch_world(latest)
                latest = self._runtime_record.read()
                if latest.tier is BackendTier.WORLD_READY:
                    return
            if latest.phase is RuntimePhase.RECOVERY_REQUIRED:
                return
            if latest.desired_target.rank < RuntimeTarget.WORLD.rank:
                self._stop_authority()
                return
            if latest.tier is BackendTier.CORE_READY:
                attempts += 1
                if attempts >= self._max_attempts:
                    return
                if self._stop_event.wait(self._retry_delay_seconds):
                    return
                continue
            self._sleeper(self._poll_interval_seconds)

    def _watch_world(self, claimed: RuntimeSnapshotV1) -> None:
        """Keep a live World tier honest and demote it after authority loss."""
        owner_lease = claimed.owner_lease
        if owner_lease is None:
            return
        unhealthy_since: Optional[float] = None
        while not self._stop_event.is_set():
            current = self._runtime_record.read()
            if not self._world_claim_is_current(
                current, owner_lease.owner_id, owner_lease.generation
            ):
                self._stop_authority()
                return
            process = self._authority_process
            process_poll = getattr(process, "poll", None)
            exit_code = process_poll() if callable(process_poll) else None
            if exit_code is not None:
                detail = _authority_exit_detail(
                    "Godot authority Runtime exited after World readiness",
                    exit_code,
                )
                diagnostic_logger.error(
                    detail,
                    extra={
                        "diagnostic_event": "authority_exited",
                        "generation": owner_lease.generation,
                        "exit_code": exit_code,
                    },
                )
                self._record_failure(
                    owner_lease.owner_id,
                    owner_lease.generation,
                    "AUTHORITY_EXITED",
                    detail,
                )
                return
            try:
                ready = self._world_ready_probe()
            except (OSError, RuntimeError, ValueError) as error:
                if unhealthy_since is None:
                    diagnostic_logger.warning(
                        "World readiness probe failed",
                        exc_info=True,
                        extra={
                            "diagnostic_event": "world_readiness_probe_failed",
                            "generation": owner_lease.generation,
                            "error_type": type(error).__name__,
                        },
                    )
                ready = False
            if not ready:
                now = self._monotonic()
                if unhealthy_since is None:
                    unhealthy_since = now
                if now - unhealthy_since >= self._world_disconnect_grace_seconds:
                    self._record_failure(
                        owner_lease.owner_id,
                        owner_lease.generation,
                        "WORLD_DISCONNECTED",
                        "Godot authority Runtime no longer satisfies World readiness",
                    )
                    return
            else:
                unhealthy_since = None
            self._sleeper(self._poll_interval_seconds)

    def _converge(self, claimed: RuntimeSnapshotV1) -> None:
        owner_lease = claimed.owner_lease
        if owner_lease is None:
            return
        owner_id = owner_lease.owner_id
        generation = owner_lease.generation
        world_started_at = self._monotonic()
        diagnostic_logger.info(
            "World convergence starting",
            extra={
                "diagnostic_event": "world_convergence_starting",
                "generation": generation,
            },
        )
        with self._command_lock():
            current = self._runtime_record.read()
            if not self._claim_is_current(current, owner_id, generation):
                return
            current = replace(
                current,
                revision=current.revision + 1,
                phase=RuntimePhase.WORLD_STARTING,
                subphase="authority_starting",
                reached_target=RuntimeTarget.CORE,
                failures=(),
                components=self._set_authority_component(
                    current.components,
                    ComponentState.STARTING,
                ),
            )
            self._runtime_record.write(current)

        try:
            authority = self._authority_host.start()
        except Exception as error:  # noqa: BLE001 - convert adapter failure to typed state
            self._record_failure(
                owner_id,
                generation,
                "AUTHORITY_START_FAILED",
                str(error),
                world_started_at=world_started_at,
            )
            return
        if authority is None:
            self._record_failure(
                owner_id,
                generation,
                "AUTHORITY_START_FAILED",
                "Godot authority Runtime did not return a process handle",
                world_started_at=world_started_at,
            )
            return
        with self._authority_lock:
            self._authority_process = authority

        with self._command_lock():
            current = self._runtime_record.read()
            if not self._claim_is_current(current, owner_id, generation):
                self._stop_authority()
                return
            self._runtime_record.write(
                replace(
                    current,
                    revision=current.revision + 1,
                    components=self._set_authority_component(
                        current.components,
                        ComponentState.STARTING,
                        pid=authority.pid,
                    ),
                )
            )

        deadline = self._monotonic() + self._authority_timeout_seconds
        readiness_probe_failures = 0
        while not self._stop_event.is_set():
            current = self._runtime_record.read()
            if not self._claim_is_current(current, owner_id, generation):
                self._stop_authority()
                return
            process_poll = getattr(authority, "poll", None)
            exit_code = process_poll() if callable(process_poll) else None
            if exit_code is not None:
                detail = _authority_exit_detail(
                    "Godot authority Runtime exited before World readiness",
                    exit_code,
                )
                diagnostic_logger.error(
                    detail,
                    extra={
                        "diagnostic_event": "authority_exited",
                        "generation": generation,
                        "exit_code": exit_code,
                    },
                )
                self._record_failure(
                    owner_id,
                    generation,
                    "AUTHORITY_EXITED",
                    detail,
                    world_started_at=world_started_at,
                )
                return
            try:
                ready = self._world_ready_probe()
            except (OSError, RuntimeError, ValueError) as error:
                readiness_probe_failures += 1
                if readiness_probe_failures & (readiness_probe_failures - 1) == 0:
                    diagnostic_logger.warning(
                        "World readiness probe failed during convergence",
                        exc_info=True,
                        extra={
                            "diagnostic_event": "world_readiness_probe_failed",
                            "generation": generation,
                            "error_type": type(error).__name__,
                            "attempt": readiness_probe_failures,
                        },
                    )
                ready = False
            if ready:
                self._promote_world_ready(
                    owner_id,
                    generation,
                    authority.pid,
                    world_started_at=world_started_at,
                )
                return
            if self._monotonic() >= deadline:
                self._record_failure(
                    owner_id,
                    generation,
                    "WORLD_READY_TIMEOUT",
                    "Godot authority Runtime did not satisfy the World readiness contract before timeout",
                    world_started_at=world_started_at,
                )
                return
            self._sleeper(self._poll_interval_seconds)

    def _promote_world_ready(
        self,
        owner_id: str,
        generation: int,
        pid: int,
        *,
        world_started_at: Optional[float] = None,
    ) -> None:
        with self._command_lock():
            current = self._runtime_record.read()
            if not self._claim_is_current(current, owner_id, generation):
                self._stop_authority()
                return
            self._runtime_record.write(
                replace(
                    current,
                    revision=current.revision + 1,
                    tier=BackendTier.WORLD_READY,
                    phase=RuntimePhase.WORLD_READY,
                    subphase="",
                    reached_target=RuntimeTarget.WORLD,
                    components=self._set_authority_component(
                        current.components,
                        ComponentState.READY,
                        pid=pid,
                    ),
                    timings=_append_timing(
                        current.timings,
                        "world",
                        self._elapsed_since(world_started_at),
                    ),
                )
            )
        diagnostic_logger.info(
            "World convergence reached readiness",
            extra={
                "diagnostic_event": "world_convergence_ready",
                "generation": generation,
            },
        )

    def _record_failure(
        self,
        owner_id: str,
        generation: int,
        code: str,
        detail: str,
        *,
        world_started_at: Optional[float] = None,
    ) -> None:
        diagnostic_logger.error(
            detail,
            extra={
                "diagnostic_event": "world_convergence_failed",
                "generation": generation,
                "reason": code,
            },
        )
        self._stop_authority()
        with self._command_lock():
            current = self._runtime_record.read()
            if not (
                self._claim_is_current(current, owner_id, generation)
                or self._world_claim_is_current(current, owner_id, generation)
            ):
                return
            self._runtime_record.write(
                replace(
                    current,
                    revision=current.revision + 1,
                    tier=BackendTier.CORE_READY,
                    phase=RuntimePhase.FAILED,
                    subphase="world_failed",
                    reached_target=RuntimeTarget.CORE,
                    components=self._set_authority_component(
                        current.components,
                        ComponentState.FAILED,
                        detail=detail,
                        clear_pid=True,
                    ),
                    failures=(FailureSnapshot(code, detail, "world"),),
                    timings=_append_timing(
                        current.timings,
                        "world",
                        self._elapsed_since(world_started_at),
                    ),
                )
            )

    def _stop_authority(self) -> Optional[str]:
        with self._authority_lock:
            authority = self._authority_process
            self._authority_process = None
        if authority is not None:
            try:
                self._authority_host.stop(authority)
            except (OSError, RuntimeError, ValueError) as error:
                # The Core is still usable; the next exact-identity recovery
                # pass can reconcile a child that ignored this stop request.
                return str(error)
        return None

    def _publish_stop_result(self, detail: Optional[str]) -> None:
        """Persist World cleanup evidence before the Core process exits."""
        with self._command_lock():
            current = self._runtime_record.read()
            if current.phase is RuntimePhase.RECOVERY_REQUIRED:
                return
            if detail:
                self._runtime_record.write(
                    replace(
                        current,
                        revision=current.revision + 1,
                        tier=BackendTier.OFFLINE,
                        phase=RuntimePhase.FAILED,
                        subphase="world_stop_failed",
                        reached_target=None,
                        components=self._set_authority_component(
                            current.components,
                            ComponentState.FAILED,
                            detail=detail,
                        ),
                        failures=(
                            FailureSnapshot(
                                "WORLD_STOP_INCOMPLETE",
                                detail,
                                "world_stop",
                            ),
                        ),
                    )
                )
                return
            self._runtime_record.write(
                replace(
                    current,
                    revision=current.revision + 1,
                    tier=(
                        BackendTier.CORE_READY
                        if current.tier is BackendTier.WORLD_READY
                        else current.tier
                    ),
                    phase=(
                        RuntimePhase.CORE_READY
                        if current.phase
                        in {
                            RuntimePhase.WORLD_STARTING,
                            RuntimePhase.WORLD_READY,
                            RuntimePhase.WORLD_STOPPING,
                        }
                        else current.phase
                    ),
                    subphase=(
                        ""
                        if current.phase
                        in {
                            RuntimePhase.WORLD_STARTING,
                            RuntimePhase.WORLD_READY,
                            RuntimePhase.WORLD_STOPPING,
                        }
                        else current.subphase
                    ),
                    reached_target=(
                        RuntimeTarget.CORE
                        if current.tier is BackendTier.WORLD_READY
                        else current.reached_target
                    ),
                    components=self._set_authority_component(
                        current.components,
                        ComponentState.ABSENT,
                        clear_pid=True,
                    ),
                    failures=(),
                )
            )

    @staticmethod
    def _claim_is_current(
        snapshot: RuntimeSnapshotV1,
        owner_id: str,
        generation: int,
    ) -> bool:
        return (
            snapshot.owner_lease is not None
            and snapshot.owner_lease.owner_id == owner_id
            and snapshot.owner_lease.generation == generation
            and snapshot.tier is BackendTier.CORE_READY
            and snapshot.phase
            in {
                RuntimePhase.CORE_READY,
                RuntimePhase.WORLD_STARTING,
                RuntimePhase.FAILED,
            }
            and snapshot.desired_target.rank >= RuntimeTarget.WORLD.rank
        )

    @staticmethod
    def _world_claim_is_current(
        snapshot: RuntimeSnapshotV1,
        owner_id: str,
        generation: int,
    ) -> bool:
        return (
            snapshot.owner_lease is not None
            and snapshot.owner_lease.owner_id == owner_id
            and snapshot.owner_lease.generation == generation
            and snapshot.tier is BackendTier.WORLD_READY
            and snapshot.phase is RuntimePhase.WORLD_READY
            and snapshot.desired_target.rank >= RuntimeTarget.WORLD.rank
        )

    @staticmethod
    def _set_authority_component(
        components: tuple[ComponentSnapshot, ...],
        state: ComponentState,
        *,
        pid: Optional[int] = None,
        detail: str = "",
        clear_pid: bool = False,
    ) -> tuple[ComponentSnapshot, ...]:
        updated = tuple(
            replace(
                item,
                state=state,
                pid=pid if pid is not None else None if clear_pid else item.pid,
                detail=detail,
            )
            if item.component is RuntimeComponent.GODOT_AUTHORITY
            else item
            for item in components
        )
        if any(item.component is RuntimeComponent.GODOT_AUTHORITY for item in updated):
            return updated
        return updated + (
            ComponentSnapshot(
                RuntimeComponent.GODOT_AUTHORITY,
                state,
                detail=detail,
                pid=pid,
            ),
        )

    @contextmanager
    def _command_lock(self) -> Iterator[None]:
        if self._command_lease_factory is None:
            with nullcontext():
                yield
            return
        lease = self._command_lease_factory()
        try:
            yield
        finally:
            lease.release()

    def _elapsed_since(self, started_at: Optional[float]) -> Optional[float]:
        if started_at is None:
            return None
        return max(0.0, self._monotonic() - started_at)


def _append_timing(
    timings: tuple[TimingSnapshot, ...], phase: str, elapsed_seconds: Optional[float]
) -> tuple[TimingSnapshot, ...]:
    if elapsed_seconds is None:
        return timings
    completed = TimingSnapshot(
        phase=phase,
        duration_ms=max(0, int(elapsed_seconds * 1000)),
    )
    return tuple(item for item in timings if item.phase != phase) + (completed,)


def _authority_exit_detail(prefix: str, exit_code: int) -> str:
    if exit_code < 0:
        return f"{prefix} (exit_code={exit_code}, signal={-exit_code})"
    return f"{prefix} (exit_code={exit_code})"


__all__ = ("RuntimeWorldWorker",)
