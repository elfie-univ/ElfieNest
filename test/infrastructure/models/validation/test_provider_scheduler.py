from __future__ import annotations

from datetime import datetime, timezone

from app.features.configuration.providers import StoredModelAvailability
from infrastructure.models.validation.provider_scheduler import (
    ProviderValidationScheduler,
)
from infrastructure.models.validation.serving_food import (
    CoreEndpointRoute,
    ServingFoodIndex,
)


def _availability(
    reference: str,
    *,
    status: str = "unknown",
    observed_at: str | None = None,
) -> StoredModelAvailability:
    connection_id, model_id = reference.split("/", 1)
    return StoredModelAvailability(
        reference=reference,
        connection_id=connection_id,
        model_id=model_id,
        status=status,
        reason_code=None,
        provider_status="unknown",
        evidence_source=None,
        observed_at=observed_at,
        expires_at=None,
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
    ) -> object:
        assert allow_probe
        self.reachability_calls.append(connection_id)
        return object()


class _Leases:
    def __init__(self) -> None:
        self.keys: list[str] = []

    def try_acquire_validation_lease(
        self,
        lease_key: str,
        owner_id: str,
        *,
        lease_seconds: int,
    ) -> bool:
        self.keys.append(lease_key)
        return True

    def release_validation_lease(self, lease_key: str, owner_id: str) -> bool:
        return True


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


def test_scheduler_runs_retention_behind_a_shared_lease() -> None:
    availability = _Availability()
    leases = _Leases()
    cutoffs = []
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
