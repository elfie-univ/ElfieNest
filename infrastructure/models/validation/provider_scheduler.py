"""Low-cost periodic validation for production-serving Provider endpoints."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol

from app.features.configuration.providers import CapabilityName, StoredModelAvailability
from infrastructure.models.validation.provider_availability import (
    NON_RETRYABLE_REASONS,
    ReachabilityAvailability,
)
from infrastructure.models.validation.serving_food import ServingFoodIndex

CORE_MODEL_FRESHNESS = timedelta(hours=24)
REACHABILITY_INTERVAL = timedelta(minutes=5)
RETENTION_INTERVAL = timedelta(days=1)
RAW_RETENTION = timedelta(days=30)
LEASE_SECONDS = 120


class ProviderHealthQuery(Protocol):
    def get(self, reference: str) -> StoredModelAvailability: ...

    def ensure(
        self,
        reference: str,
        *,
        max_age: timedelta,
        allow_probe: bool,
        capability: CapabilityName | None = None,
    ) -> StoredModelAvailability: ...

    def ensure_reachability(
        self,
        connection_id: str,
        *,
        max_age: timedelta,
        allow_probe: bool,
    ) -> ReachabilityAvailability: ...


class ValidationLeaseStore(Protocol):
    def try_acquire_validation_lease(
        self,
        lease_key: str,
        owner_id: str,
        *,
        lease_seconds: int,
    ) -> bool: ...

    def release_validation_lease(self, lease_key: str, owner_id: str) -> bool: ...


@dataclass(frozen=True)
class SchedulerRunResult:
    reachability_checked: tuple[str, ...]
    model_checked: tuple[str, ...]


class ProviderValidationScheduler:
    """Run only the checks that can affect current production serving."""

    def __init__(
        self,
        availability: ProviderHealthQuery,
        serving_index: Callable[[], ServingFoodIndex],
        leases: ValidationLeaseStore,
        *,
        connection_ids: Callable[[], tuple[str, ...]] | None = None,
        owner_id: str | None = None,
        interval: timedelta = REACHABILITY_INTERVAL,
        lease_seconds: int = LEASE_SECONDS,
        maintenance: Callable[[datetime], object] | None = None,
        retention_interval: timedelta = RETENTION_INTERVAL,
        raw_retention: timedelta = RAW_RETENTION,
        check_core_models: bool = True,
    ) -> None:
        self._availability = availability
        self._serving_index = serving_index
        self._leases = leases
        self._connection_ids = connection_ids
        self._owner_id = owner_id or f"provider-validator-{uuid.uuid4().hex}"
        self._interval = interval
        self._lease_seconds = lease_seconds
        self._maintenance = maintenance
        self._retention_interval = retention_interval
        self._raw_retention = raw_retention
        # The legacy scheduler owns Provider-wide reachability.  When the
        # process also runs CoreValidationWorker, that worker owns all
        # model/channel probes so the two loops cannot spend tokens on the
        # same serving endpoint.
        self._check_core_models = check_core_models
        self._last_maintenance_at: datetime | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lifecycle_lock = threading.Lock()

    def run_once(self, *, now: datetime | None = None) -> SchedulerRunResult:
        current = _utc(now or datetime.now(timezone.utc))
        checked_reachability: list[str] = []
        connection_ids = self._scheduled_connection_ids()
        for connection_id in connection_ids:
            lease_key = f"provider:{connection_id}:reachability"
            if not self._try_acquire(lease_key):
                continue
            try:
                self._availability.ensure_reachability(
                    connection_id,
                    max_age=REACHABILITY_INTERVAL,
                    allow_probe=True,
                )
                checked_reachability.append(connection_id)
            except Exception:
                # The observation boundary owns failure recording. One broken
                # Provider must not stop checks for the other connections.
                pass
            finally:
                self._release(lease_key)

        checked_models: list[str] = []
        if self._check_core_models:
            scheduled_index = self._serving_index()
            for reference in scheduled_index.core_references:
                # The index is derived from Food assignments and enabled
                # endpoint records.  If it changes while this run is in
                # flight, discard the remaining snapshot rather than probing
                # a route that is no longer core.  The next tick will schedule
                # the new generation.
                if self._serving_index().generation != scheduled_index.generation:
                    break
                try:
                    current_availability = self._availability.get(reference)
                    if not _needs_core_probe(current_availability, current):
                        continue
                    lease_key = f"model:{reference}:validation"
                    if not self._try_acquire(lease_key):
                        continue
                    try:
                        self._availability.ensure(
                            reference,
                            max_age=CORE_MODEL_FRESHNESS,
                            allow_probe=True,
                        )
                        checked_models.append(reference)
                    finally:
                        self._release(lease_key)
                except Exception:
                    pass
        self._run_maintenance(current)
        return SchedulerRunResult(
            reachability_checked=tuple(checked_reachability),
            model_checked=tuple(checked_models),
        )

    def start(self) -> None:
        with self._lifecycle_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="provider-validation-scheduler",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lifecycle_lock:
            thread = self._thread
            self._stop.set()
        if thread is not None:
            thread.join(timeout=2.0)
        with self._lifecycle_lock:
            self._thread = None

    def _run(self) -> None:
        while not self._stop.wait(self._interval.total_seconds()):
            try:
                self.run_once()
            except Exception:
                # A transient storage/projection error must not kill the
                # long-lived scheduler thread.
                continue

    def _try_acquire(self, lease_key: str) -> bool:
        try:
            return self._leases.try_acquire_validation_lease(
                lease_key,
                self._owner_id,
                lease_seconds=self._lease_seconds,
            )
        except Exception:
            return False

    def _release(self, lease_key: str) -> None:
        try:
            self._leases.release_validation_lease(lease_key, self._owner_id)
        except Exception:
            pass

    def _scheduled_connection_ids(self) -> tuple[str, ...]:
        if self._connection_ids is not None:
            return tuple(dict.fromkeys(self._connection_ids()))
        return tuple(
            dict.fromkeys(
                reference.split("/", 1)[0]
                for reference in self._serving_index().core_references
            )
        )

    def _run_maintenance(self, now: datetime) -> None:
        if self._maintenance is None:
            return
        if (
            self._last_maintenance_at is not None
            and now - self._last_maintenance_at < self._retention_interval
        ):
            return
        lease_key = "reports:retention"
        if not self._try_acquire(lease_key):
            return
        try:
            self._maintenance(now - self._raw_retention)
            self._last_maintenance_at = now
        except Exception:
            # Retention must never prevent availability checks.  A later tick
            # retries it after another worker releases the lease.
            pass
        finally:
            self._release(lease_key)


def _needs_core_probe(
    availability: StoredModelAvailability,
    now: datetime,
) -> bool:
    observed = _parse_timestamp(availability.observed_at)
    expires_at = _parse_timestamp(availability.expires_at)
    if expires_at is not None and now < expires_at:
        return False
    # Account and lifecycle blockers are not healed by spending another model
    # token with the same configuration.  A credential/configuration change
    # removes the old fingerprinted evidence; an explicit Owner validation can
    # still bypass this passive scheduler.
    if availability.reason_code in NON_RETRYABLE_REASONS:
        return False
    if expires_at is not None:
        return True
    return (
        observed is None
        or now - observed > CORE_MODEL_FRESHNESS
        or availability.status == "unknown"
    )


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = (
    "CORE_MODEL_FRESHNESS",
    "LEASE_SECONDS",
    "ProviderValidationScheduler",
    "REACHABILITY_INTERVAL",
    "RAW_RETENTION",
    "RETENTION_INTERVAL",
    "SchedulerRunResult",
)
