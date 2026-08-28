from __future__ import annotations

import logging
import multiprocessing as mp
from datetime import datetime, timezone
from pathlib import Path

from app.features.configuration.providers import StoredModelAvailability
from infrastructure.models.validation.provider_availability import (
    AvailabilityStatus,
    EndpointAvailability,
)
from infrastructure.models.validation.provider_scheduler import (
    ProviderValidationScheduler,
)
from infrastructure.models.validation.serving_food import (
    CoreEndpointRoute,
    ServingFoodIndex,
)
from infrastructure.persistence.reports.report_repository import ReportRepository


def _availability(
    reference: str,
    *,
    status: AvailabilityStatus = "unknown",
    observed_at: str | None = None,
    expires_at: str | None = None,
    reason_code: str | None = None,
) -> StoredModelAvailability:
    connection_id, model_id = reference.split("/", 1)
    return StoredModelAvailability(
        reference=reference,
        connection_id=connection_id,
        model_id=model_id,
        status=status,
        reason_code=reason_code,
        provider_status="unknown",
        evidence_source=None,
        observed_at=observed_at,
        expires_at=expires_at,
        is_core=True,
        serving_food_ids=(),
        serving_roles=(),
        capabilities=(),
    )


class _Availability:
    def __init__(self) -> None:
        self.items = {"cloud/main": _availability("cloud/main")}
        self.reachability_calls: list[str] = []
        self.model_calls: list[str] = []

    def get(self, reference: str) -> StoredModelAvailability:
        return self.items[reference]

    def ensure(
        self,
        reference: str,
        *,
        max_age,
        allow_probe: bool,
    ) -> StoredModelAvailability:
        assert allow_probe
        self.model_calls.append(reference)
        current = self.items[reference]
        self.items[reference] = _availability(
            reference,
            status="available",
            observed_at="2026-08-16T00:00:00+00:00",
        )
        return current

    def ensure_reachability(
        self,
        connection_id: str,
        *,
        max_age,
        allow_probe: bool,
    ) -> EndpointAvailability:
        assert allow_probe
        self.reachability_calls.append(connection_id)
        return EndpointAvailability(
            subject_id=connection_id,
            status="available",
            reason_code=None,
            error_scope=None,
            observed_at=None,
            expires_at=None,
            evidence_source="reachability",
        )


class _Leases:
    def __init__(self) -> None:
        self.keys: list[str] = []
        self.acquisitions: list[tuple[str, int]] = []
        self.releases: list[str] = []

    def try_acquire_validation_lease(
        self,
        lease_key: str,
        owner_id: str,
        *,
        lease_seconds: int,
    ) -> bool:
        self.keys.append(lease_key)
        self.acquisitions.append((lease_key, lease_seconds))
        return True

    def release_validation_lease(self, lease_key: str, owner_id: str) -> bool:
        self.releases.append(lease_key)
        return True


def test_scheduler_keeps_a_stuck_thread_owned_and_records_stop_timeout(
    caplog,
) -> None:
    class StuckThread:
        def join(self, timeout: float) -> None:
            assert timeout == 2.0

        def is_alive(self) -> bool:
            return True

    scheduler = ProviderValidationScheduler(
        _Availability(),
        lambda: ServingFoodIndex(generation="g1", foods=(), core_endpoints=()),
        _Leases(),
    )
    stuck = StuckThread()
    scheduler._thread = stuck

    with caplog.at_level(
        logging.ERROR,
        logger="elfienest.diagnostics.provider_validation",
    ):
        scheduler.stop()

    assert scheduler._thread is stuck
    assert "did not stop within" in caplog.text


def test_scheduler_checks_all_connections_for_transport_but_only_core_models() -> None:
    availability = _Availability()
    leases = _Leases()
    scheduler = ProviderValidationScheduler(
        availability,
        lambda: ServingFoodIndex(
            generation="g1",
            foods=(),
            core_endpoints=(CoreEndpointRoute("cloud/main", (), ("primary",)),),
        ),
        leases,
        connection_ids=lambda: ("cloud", "other"),
        owner_id="worker-a",
    )

    result = scheduler.run_once(now=datetime(2026, 8, 16, tzinfo=timezone.utc))

    assert result.reachability_checked == ("cloud", "other")
    assert result.model_checked == ("cloud/main",)
    assert availability.reachability_calls == ["cloud", "other"]
    assert availability.model_calls == ["cloud/main"]
    assert "model:cloud/main:validation" in leases.keys


def test_scheduler_discards_a_stale_serving_food_generation() -> None:
    availability = _Availability()
    leases = _Leases()
    calls = 0

    def changing_index() -> ServingFoodIndex:
        nonlocal calls
        calls += 1
        return ServingFoodIndex(
            generation="g1" if calls == 1 else "g2",
            foods=(),
            core_endpoints=(CoreEndpointRoute("cloud/main", (), ("primary",)),),
        )

    scheduler = ProviderValidationScheduler(
        availability,
        changing_index,
        leases,
        connection_ids=lambda: ("cloud",),
        owner_id="worker-a",
    )

    result = scheduler.run_once(now=datetime(2026, 8, 16, tzinfo=timezone.utc))

    assert result.reachability_checked == ("cloud",)
    assert result.model_checked == ()
    assert availability.model_calls == []


def test_scheduler_can_leave_model_probes_to_core_validation_worker() -> None:
    availability = _Availability()
    leases = _Leases()
    scheduler = ProviderValidationScheduler(
        availability,
        lambda: ServingFoodIndex(
            generation="g1",
            foods=(),
            core_endpoints=(CoreEndpointRoute("cloud/main", (), ("primary",)),),
        ),
        leases,
        connection_ids=lambda: ("cloud",),
        owner_id="worker-a",
        check_core_models=False,
    )

    result = scheduler.run_once(now=datetime(2026, 8, 16, tzinfo=timezone.utc))

    assert result.reachability_checked == ("cloud",)
    assert result.model_checked == ()
    assert availability.reachability_calls == ["cloud"]
    assert availability.model_calls == []


def test_scheduler_refreshes_cached_ollama_status_behind_a_lease() -> None:
    availability = _Availability()
    leases = _Leases()
    refresh_calls: list[str] = []
    scheduler = ProviderValidationScheduler(
        availability,
        lambda: ServingFoodIndex(generation="g1", foods=(), core_endpoints=()),
        leases,
        connection_ids=lambda: (),
        owner_id="worker-a",
        check_core_models=False,
        local_status_refresh=lambda: refresh_calls.append("ollama"),
    )

    scheduler.run_once(now=datetime(2026, 8, 16, tzinfo=timezone.utc))

    assert refresh_calls == ["ollama"]
    assert "provider:ollama:status" in leases.keys
    assert ("provider:ollama:status", 300) in leases.acquisitions


def test_scheduler_keeps_ollama_refresh_lease_after_failure() -> None:
    leases = _Leases()

    def fail_refresh() -> None:
        raise RuntimeError("ollama unavailable")

    scheduler = ProviderValidationScheduler(
        _Availability(),
        lambda: ServingFoodIndex(generation="g1", foods=(), core_endpoints=()),
        leases,
        connection_ids=lambda: (),
        owner_id="worker-a",
        check_core_models=False,
        local_status_refresh=fail_refresh,
    )

    scheduler.run_once(now=datetime(2026, 8, 16, tzinfo=timezone.utc))

    assert ("provider:ollama:status", 300) in leases.acquisitions
    assert "provider:ollama:status" not in leases.releases


def test_scheduler_waits_for_retry_expiry_and_does_not_retry_account_blockers() -> None:
    availability = _Availability()
    now = datetime(2026, 8, 16, tzinfo=timezone.utc)
    availability.items["cloud/main"] = _availability(
        "cloud/main",
        status="degraded",
        observed_at="2026-08-16T00:00:00+00:00",
        expires_at="2026-08-16T00:10:00+00:00",
    )
    scheduler = ProviderValidationScheduler(
        availability,
        lambda: ServingFoodIndex(
            generation="g1",
            foods=(),
            core_endpoints=(CoreEndpointRoute("cloud/main", (), ("primary",)),),
        ),
        _Leases(),
        connection_ids=lambda: (),
        owner_id="worker-a",
    )

    first = scheduler.run_once(now=now)
    assert first.model_checked == ()
    after_retry = scheduler.run_once(
        now=datetime(2026, 8, 16, 0, 11, tzinfo=timezone.utc)
    )
    assert after_retry.model_checked == ("cloud/main",)

    availability.items["cloud/main"] = _availability(
        "cloud/main",
        status="unavailable",
        observed_at=now.isoformat(),
        reason_code="billing_blocked",
    )
    second = scheduler.run_once(now=now)
    assert second.model_checked == ()


def test_scheduler_runs_retention_behind_a_shared_lease() -> None:
    availability = _Availability()
    leases = _Leases()
    cutoffs: list[datetime] = []
    scheduler = ProviderValidationScheduler(
        availability,
        lambda: ServingFoodIndex(
            generation="g1",
            foods=(),
            core_endpoints=(),
        ),
        leases,
        connection_ids=lambda: (),
        owner_id="worker-a",
        maintenance=cutoffs.append,
    )

    scheduler.run_once(now=datetime(2026, 8, 16, tzinfo=timezone.utc))

    assert cutoffs == [datetime(2026, 7, 17, tzinfo=timezone.utc)]
    assert "reports:retention" in leases.keys


class _ProcessAvailability:
    def __init__(self, started, release) -> None:
        self._started = started
        self._release = release
        self.calls = 0

    def get(self, reference: str) -> StoredModelAvailability:
        return _availability(reference)

    def ensure(
        self,
        reference: str,
        *,
        max_age,
        allow_probe: bool,
    ) -> StoredModelAvailability:
        assert allow_probe
        self.calls += 1
        self._started.set()
        if not self._release.wait(timeout=5):
            raise RuntimeError("test release event timed out")
        return _availability(
            reference,
            status="available",
            observed_at="2026-08-16T00:00:00+00:00",
        )

    def ensure_reachability(
        self,
        connection_id: str,
        *,
        max_age,
        allow_probe: bool,
    ) -> EndpointAvailability:
        raise AssertionError("the process lease scenario should not probe reachability")


def _process_scheduler_worker(
    db_path: str,
    owner_id: str,
    mode: str,
    started,
    release,
    results,
) -> None:
    repository = ReportRepository(Path(db_path))
    maintenance_calls = 0
    if mode == "model":
        availability = _ProcessAvailability(started, release)
        scheduler = ProviderValidationScheduler(
            availability,
            lambda: ServingFoodIndex(
                generation="g1",
                foods=(),
                core_endpoints=(CoreEndpointRoute("cloud/main", (), ("primary",)),),
            ),
            repository,
            connection_ids=lambda: (),
            owner_id=owner_id,
        )
    else:

        def maintenance(cutoff: datetime) -> None:
            nonlocal maintenance_calls
            maintenance_calls += 1
            started.set()
            if not release.wait(timeout=5):
                raise RuntimeError("test release event timed out")
            repository.compact_observations(cutoff.isoformat())

        scheduler = ProviderValidationScheduler(
            _Availability(),
            lambda: ServingFoodIndex(
                generation="g1",
                foods=(),
                core_endpoints=(),
            ),
            repository,
            connection_ids=lambda: (),
            owner_id=owner_id,
            maintenance=maintenance,
        )

    result = scheduler.run_once(now=datetime(2026, 8, 16, tzinfo=timezone.utc))
    results.put(
        {
            "owner_id": owner_id,
            "mode": mode,
            "model_checked": result.model_checked,
            "maintenance_calls": maintenance_calls,
            "probe_calls": getattr(locals().get("availability"), "calls", 0),
        }
    )


def _assert_only_one_process_runs_lease(tmp_path: Path, mode: str) -> None:
    # The repository's pytest collection imports this module as a transient
    # ``validation.*`` module, which is not importable by multiprocessing's
    # spawn re-import on macOS.  fork still gives us two independent OS
    # workers and exercises the SQLite cross-process lease itself.
    context = mp.get_context("fork")
    database_path = tmp_path / f"{mode}-workers.sqlite"
    ReportRepository(database_path)
    first_started = context.Event()
    second_started = context.Event()
    release = context.Event()
    results = context.Queue()
    first = context.Process(
        target=_process_scheduler_worker,
        args=(
            str(database_path),
            "worker-a",
            mode,
            first_started,
            release,
            results,
        ),
    )
    second = context.Process(
        target=_process_scheduler_worker,
        args=(
            str(database_path),
            "worker-b",
            mode,
            second_started,
            release,
            results,
        ),
    )
    try:
        first.start()
        assert first_started.wait(timeout=5)
        second.start()
        second.join(timeout=5)
        assert second.exitcode == 0
        assert second_started.is_set() is False
    finally:
        release.set()
        first.join(timeout=5)
        if first.is_alive():
            first.terminate()
            first.join(timeout=2)
        if second.is_alive():
            second.terminate()
            second.join(timeout=2)

    records = [results.get(timeout=5) for _ in range(2)]
    by_owner = {record["owner_id"]: record for record in records}
    assert by_owner["worker-a"]["mode"] == mode
    assert by_owner["worker-b"]["mode"] == mode
    if mode == "model":
        assert by_owner["worker-a"]["model_checked"] == ("cloud/main",)
        assert by_owner["worker-b"]["model_checked"] == ()
        assert by_owner["worker-a"]["probe_calls"] == 1
        assert by_owner["worker-b"]["probe_calls"] == 0
    else:
        assert by_owner["worker-a"]["maintenance_calls"] == 1
        assert by_owner["worker-b"]["maintenance_calls"] == 0


def test_two_real_workers_share_one_model_validation_lease(tmp_path: Path) -> None:
    _assert_only_one_process_runs_lease(tmp_path, "model")


def test_two_real_workers_share_one_retention_lease(tmp_path: Path) -> None:
    _assert_only_one_process_runs_lease(tmp_path, "retention")
