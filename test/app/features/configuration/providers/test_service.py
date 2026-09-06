from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.features.accounts import AccountPrincipal, AccountRole
from app.features.configuration import (
    AddProviderModelCommand,
    ChangeProviderConnectionLifecycleCommand,
    CleanupObsoleteProviderModelsCommand,
    CompleteProviderOAuthLoginCommand,
    CreateProviderConnectionCommand,
    DeleteProviderConnectionCommand,
    EnsureDefaultLocalProviderConnectionCommand,
    InspectLocalProviderQuery,
    ListProviderConnectionsQuery,
    ProviderModelInput,
    ProviderModelReplacement,
    ProviderPortError,
    ProvidersConflict,
    ProvidersForbidden,
    ProvidersService,
    ProvidersValidationError,
    RefreshProviderModelsCommand,
    RemoveLocalProviderConnectionCommand,
    ReplaceProviderModelsCommand,
    StartProviderOAuthLoginCommand,
    StoredBenchmarkRun,
    StoredLocalModelCounts,
    StoredLocalProviderBinding,
    StoredLocalProviderCandidate,
    StoredLocalProviderModelStatus,
    StoredLocalProviderProbe,
    StoredLocalProviderStatus,
    StoredModelMatrix,
    StoredModelRefresh,
    StoredModelVerification,
    StoredProviderBrand,
    StoredProviderConnection,
    StoredProviderModel,
    StoredProviderOAuthLoginStart,
    StoredProviderOAuthLoginStatus,
    StoredProviderProduct,
    StoredProviderProjection,
    StoredValidationRun,
    StoredVerification,
    VerifyProviderConnectionCommand,
)


def _principal(role: AccountRole = "owner") -> AccountPrincipal:
    return AccountPrincipal(1, "owner", role, "/manage")


class FakeProviderPort:
    def __init__(self) -> None:
        self.product = StoredProviderProduct(
            catalog_id="openai_api",
            name="OpenAI",
            brand=StoredProviderBrand("openai", "OpenAI", "openai.svg"),
            connection_method="api_key",
            oauth_available=False,
            usage_scope="general",
            discovery_strategy="standard_models",
            api_mode="chat_completions",
            api_base="https://api.openai.com/v1",
            auth_type="bearer",
        )
        self.items: dict[str, StoredProviderConnection] = {}
        self.ensure_local_calls = 0
        self.local_model_ids: list[str] = []

    def list_products(self) -> tuple[StoredProviderProduct, ...]:
        return (self.product,)

    def get_product(self, catalog_id: str) -> StoredProviderProduct | None:
        return self.product if catalog_id == self.product.catalog_id else None

    def ensure_local_connection(self, product: StoredProviderProduct) -> None:
        _ = product
        self.ensure_local_calls += 1

    def list_connections(self) -> tuple[StoredProviderConnection, ...]:
        return tuple(self.items.values())

    def get_connection(self, connection_id: str) -> StoredProviderConnection | None:
        return self.items.get(connection_id)

    def create_connection(
        self,
        connection: StoredProviderConnection,
        api_key: str | None,
    ) -> StoredProviderConnection:
        created = replace(
            connection,
            connection_id="openai_api_0001",
            credential_ref=(
                "ELFIE_PROVIDER_OPENAI_API_0001_API_KEY"
                if api_key
                else connection.credential_ref
            ),
        )
        self.items[created.connection_id] = created
        return created

    def replace_connection(
        self,
        connection: StoredProviderConnection,
        api_key: str | None,
        *,
        update_credential: bool,
    ) -> StoredProviderConnection:
        _ = api_key, update_credential
        self.items[connection.connection_id] = connection
        return connection

    def delete_connection(self, connection_id: str) -> bool:
        return self.items.pop(connection_id, None) is not None

    def has_credential(self, credential_ref: str) -> bool:
        return bool(credential_ref)

    def load_local_binding(self) -> StoredLocalProviderBinding | None:
        return None

    def save_local_binding(
        self, binding: StoredLocalProviderBinding
    ) -> StoredLocalProviderBinding:
        return binding

    def list_local_model_ids(self) -> tuple[str, ...]:
        return tuple(self.local_model_ids)

    def save_local_model(self, model_id: str) -> str:
        if model_id not in self.local_model_ids:
            self.local_model_ids.append(model_id)
        return f"ollama_0001/{model_id}"

    def local_model_reference(self, model_id: str) -> str | None:
        return f"ollama_0001/{model_id}" if model_id in self.local_model_ids else None

    def replace_local_models(self, model_ids: tuple[str, ...]) -> None:
        self.local_model_ids = list(model_ids)


class FakeReferences:
    connection_references: tuple[str, ...] = ()
    model_references: tuple[str, ...] = ()

    def connections_referenced_by_food(self, connection_id: str) -> tuple[str, ...]:
        _ = connection_id
        return self.connection_references

    def models_referenced_by_food(
        self,
        connection_id: str,
        model_id: str,
    ) -> tuple[str, ...]:
        _ = connection_id, model_id
        return self.model_references


class FakeTechnology:
    obsolete_ids: tuple[str, ...] = ()

    def __init__(self) -> None:
        self.reachability_calls: list[str] = []
        self.probed_model_references: list[str] = []
        self.model_verifications: dict[str, StoredModelVerification] = {}
        self.projection_calls: list[tuple[str, ...]] = []
        self.connection_summary_calls = 0
        self.model_summary_calls: list[tuple[str, str]] = []
        self.refresh_result: StoredModelRefresh | None = None

    def prepare_manual_model(self, model: ProviderModelInput) -> StoredProviderModel:
        return StoredProviderModel(model.model_id, model.display_name or model.model_id)

    def summarize_connection(
        self,
        connection: StoredProviderConnection,
    ) -> StoredVerification:
        _ = connection
        self.connection_summary_calls += 1
        return StoredVerification()

    def project_connections(
        self,
        connections: tuple[StoredProviderConnection, ...],
    ) -> tuple[StoredProviderProjection, ...]:
        self.projection_calls.append(
            tuple(connection.connection_id for connection in connections)
        )
        return tuple(
            StoredProviderProjection(
                connection_id=connection.connection_id,
                verification=StoredVerification(),
                model_verifications={
                    model.model_id: self.model_verifications.get(
                        model.model_id, StoredModelVerification()
                    )
                    for model in connection.models
                },
            )
            for connection in connections
        )

    def summarize_model(
        self,
        connection_id: str,
        model_id: str,
    ) -> StoredModelVerification:
        self.model_summary_calls.append((connection_id, model_id))
        return self.model_verifications.get(model_id, StoredModelVerification())

    async def verify_connection(
        self,
        connection: StoredProviderConnection,
        *,
        force_full: bool,
    ) -> StoredVerification:
        _ = connection, force_full
        return StoredVerification(status="passed", validation_mode="full")

    async def probe_reachability(self, connection_id: str) -> None:
        self.reachability_calls.append(connection_id)

    async def probe_model(self, reference: str) -> None:
        self.probed_model_references.append(reference)
        self.model_verifications[reference.rsplit("/", 1)[-1]] = (
            StoredModelVerification(
                status="passed",
                validation_mode="full",
                availability_status="available",
            )
        )

    async def refresh_models(
        self,
        connection: StoredProviderConnection,
    ) -> StoredModelRefresh:
        if self.refresh_result is not None:
            return self.refresh_result
        return StoredModelRefresh(
            "updated", "2026-08-10T00:00:00+00:00", None, connection.models
        )

    def obsolete_model_ids(
        self,
        connection: StoredProviderConnection,
        *,
        referenced_model_ids: tuple[str, ...] = (),
    ) -> tuple[str, ...]:
        _ = connection
        return tuple(
            model_id
            for model_id in self.obsolete_ids
            if model_id not in referenced_model_ids
        )

    def model_matrix(self, *args, **kwargs) -> StoredModelMatrix:
        raise ProviderPortError("unused")

    async def benchmark_models(self, *args, **kwargs) -> StoredBenchmarkRun:
        raise ProviderPortError("unused")

    async def validate_all(self, *args, **kwargs) -> StoredValidationRun:
        raise ProviderPortError("unused")


class FakeLocalTechnology:
    def default_binding(self) -> StoredLocalProviderBinding:
        return StoredLocalProviderBinding(
            "http://127.0.0.1:11434", "linux", "existing-public", ""
        )

    def probe(self, binding: StoredLocalProviderBinding) -> StoredLocalProviderProbe:
        return StoredLocalProviderProbe("absent", binding.api_base)

    def available_memory_gb(self) -> int:
        return 0

    def candidate_models(self) -> tuple[StoredLocalProviderCandidate, ...]:
        return ()

    def list_models(self, binding: StoredLocalProviderBinding) -> tuple[str, ...]:
        _ = binding
        return ()

    def install_official(self) -> StoredLocalProviderBinding:
        return self.default_binding()

    def start(self, binding: StoredLocalProviderBinding) -> StoredLocalProviderBinding:
        return binding

    def pull_model(self, binding: StoredLocalProviderBinding, model_id: str) -> None:
        _ = binding, model_id


class FakeLocalStatusCache:
    def __init__(self, status: StoredLocalProviderStatus | None) -> None:
        self.status = status
        self.load_calls = 0
        self.saved: list[StoredLocalProviderStatus] = []
        self.refresh_claims: list[tuple[str, int]] = []
        self.refresh_releases: list[str] = []

    def load(self) -> StoredLocalProviderStatus | None:
        self.load_calls += 1
        return self.status

    def save(self, status: StoredLocalProviderStatus) -> None:
        self.saved.append(status)
        self.status = status

    def try_acquire_refresh_lease(self, owner_id: str, *, lease_seconds: int) -> bool:
        self.refresh_claims.append((owner_id, lease_seconds))
        return True

    def release_refresh_lease(self, owner_id: str) -> bool:
        self.refresh_releases.append(owner_id)
        return True


class QueueScheduler:
    def __init__(self) -> None:
        self.tasks: list[object] = []

    def add_task(self, func) -> None:
        self.tasks.append(func)


class FailingLocalTechnology(FakeLocalTechnology):
    def probe(self, binding: StoredLocalProviderBinding) -> StoredLocalProviderProbe:
        _ = binding
        raise AssertionError("cached local status must not probe Ollama")


class FakeInstalledLocalTechnology(FakeLocalTechnology):
    def probe(self, binding: StoredLocalProviderBinding) -> StoredLocalProviderProbe:
        return StoredLocalProviderProbe("healthy", binding.api_base, "0.1")

    def candidate_models(self) -> tuple[StoredLocalProviderCandidate, ...]:
        return (StoredLocalProviderCandidate("recommended", "Recommended", True),)

    def list_models(self, binding: StoredLocalProviderBinding) -> tuple[str, ...]:
        _ = binding
        return ("custom-installed",)


class FakeSupportedInstalledLocalTechnology(FakeInstalledLocalTechnology):
    def list_models(self, binding: StoredLocalProviderBinding) -> tuple[str, ...]:
        _ = binding
        return ("recommended", "custom-installed")


class FakeOAuth:
    def __init__(self) -> None:
        self.completed = False

    async def start_login(self, catalog_id: str) -> StoredProviderOAuthLoginStart:
        return StoredProviderOAuthLoginStart(
            catalog_id=catalog_id,
            login_id="login-1",
            authorization_url="https://auth.openai.com/codex/device",
            user_code="ABCD-1234",
            poll_interval_seconds=8,
            expires_at="2026-08-13T12:10:00+00:00",
        )

    async def poll_login(self, login_id: str) -> StoredProviderOAuthLoginStatus:
        assert login_id == "login-1"
        if not self.completed:
            return StoredProviderOAuthLoginStatus(
                catalog_id="openai_chatgpt",
                login_id=login_id,
                state="pending",
            )
        return StoredProviderOAuthLoginStatus(
            catalog_id="openai_chatgpt",
            login_id=login_id,
            state="completed",
            credential_ref="oauth.openai_chatgpt.login-1",
            account_id="acct-1",
            expires_at="2026-08-13T13:00:00+00:00",
        )


def _service() -> tuple[ProvidersService, FakeProviderPort, FakeReferences]:
    port = FakeProviderPort()
    references = FakeReferences()
    return (
        ProvidersService(
            catalog=port,
            connections=port,
            references=references,
            technology=FakeTechnology(),
            local_state=port,
            local_technology=FakeLocalTechnology(),
            oauth=FakeOAuth(),
        ),
        port,
        references,
    )


def test_chatgpt_oauth_creates_a_separate_authenticated_connection() -> None:
    service, port, _ = _service()
    port.product = StoredProviderProduct(
        catalog_id="openai_chatgpt",
        name="OpenAI (ChatGPT)",
        brand=StoredProviderBrand("openai", "OpenAI", "openai.svg"),
        connection_method="oauth",
        oauth_available=True,
        usage_scope="general",
        discovery_strategy="catalog_only",
        api_mode="codex_responses",
        api_base="https://chatgpt.com/backend-api/codex",
        auth_type="bearer",
    )
    oauth = service._oauth
    assert isinstance(oauth, FakeOAuth)

    started = asyncio.run(
        service.start_oauth_login(
            _principal(), StartProviderOAuthLoginCommand("openai_chatgpt")
        )
    )
    pending = asyncio.run(
        service.complete_oauth_login(
            _principal(),
            CompleteProviderOAuthLoginCommand(
                "openai_chatgpt", started.login_id, "My ChatGPT"
            ),
        )
    )
    oauth.completed = True
    completed = asyncio.run(
        service.complete_oauth_login(
            _principal(),
            CompleteProviderOAuthLoginCommand(
                "openai_chatgpt", started.login_id, "My ChatGPT"
            ),
        )
    )

    assert pending.state == "pending"
    assert pending.connection is None
    assert completed.state == "completed"
    assert completed.connection is not None
    assert completed.connection.catalog_id == "openai_chatgpt"
    assert completed.connection.has_api_key is False
    assert completed.connection.has_credential is True
    stored = port.items[completed.connection.connection_id]
    assert stored.credential_ref == "oauth.openai_chatgpt.login-1"


def test_chatgpt_oauth_connection_cannot_bypass_authorization() -> None:
    service, port, _ = _service()
    port.product = replace(
        port.product,
        catalog_id="openai_chatgpt",
        connection_method="oauth",
        oauth_available=True,
        api_mode="codex_responses",
    )

    with pytest.raises(ProvidersValidationError):
        asyncio.run(
            service.create_connection(
                _principal(),
                CreateProviderConnectionCommand(catalog_id="openai_chatgpt"),
            )
        )


def test_create_uses_catalog_defaults_and_exposes_only_credential_presence() -> None:
    service, port, _ = _service()

    result = asyncio.run(
        service.create_connection(
            _principal(),
            CreateProviderConnectionCommand(
                catalog_id="openai_api",
                api_key="test-secret",
                models=(ProviderModelInput("gpt-test"),),
            ),
        ),
    )

    assert result.connection_id == "openai_api_0001"
    assert result.api_base == "https://api.openai.com/v1"
    assert result.has_api_key is True
    assert "test-secret" not in repr(result)
    assert port.items[result.connection_id].credential_ref.startswith("ELFIE_PROVIDER_")
    technology = service._technology
    assert isinstance(technology, FakeTechnology)
    assert technology.reachability_calls == [result.connection_id]


def test_deferred_setup_save_skips_implicit_provider_probes() -> None:
    service, port, _ = _service()

    result = asyncio.run(
        service.create_connection(
            _principal(),
            CreateProviderConnectionCommand(
                catalog_id="openai_api",
                api_key="test-secret",
                models=(ProviderModelInput("gpt-test"),),
                refresh_models=False,
                defer_validation=True,
            ),
        )
    )

    technology = service._technology
    assert isinstance(technology, FakeTechnology)
    assert result.connection_id in port.items
    assert technology.reachability_calls == []
    assert technology.probed_model_references == []


def test_manual_verification_records_zero_generation_reachability() -> None:
    service, port, _ = _service()
    port.items["openai_api_0001"] = StoredProviderConnection(
        connection_id="openai_api_0001",
        catalog_id="openai_api",
        alias="OpenAI",
        api_base="https://api.openai.com/v1",
        api_mode="chat_completions",
        auth_type="bearer",
        credential_ref="OPENAI_KEY",
        models=(StoredProviderModel("gpt-test", "gpt-test"),),
    )

    asyncio.run(
        service.verify_connection(
            _principal(),
            VerifyProviderConnectionCommand("openai_api_0001", force_full=True),
        )
    )

    technology = service._technology
    assert isinstance(technology, FakeTechnology)
    assert technology.reachability_calls == ["openai_api_0001"]


def test_failed_empty_model_refresh_preserves_inventory_and_emits_diagnostics(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service, port, _ = _service()
    connection = StoredProviderConnection(
        connection_id="openai_api_0001",
        catalog_id="openai_api",
        alias="OpenAI",
        api_base="https://api.openai.com/v1",
        api_mode="chat_completions",
        auth_type="bearer",
        credential_ref="OPENAI_KEY",
        models=(StoredProviderModel("gpt-test", "GPT Test"),),
    )
    port.items[connection.connection_id] = connection
    technology = service._technology
    assert isinstance(technology, FakeTechnology)
    technology.refresh_result = StoredModelRefresh(
        "failed",
        "2026-08-10T00:00:00+00:00",
        "model endpoint unavailable",
        (),
    )
    caplog.set_level(logging.INFO, logger="elfienest.diagnostics.provider_management")

    result = asyncio.run(
        service.refresh_models(
            _principal(),
            RefreshProviderModelsCommand(connection.connection_id),
        )
    )

    assert result.status == "failed"
    assert port.items[connection.connection_id].models == connection.models
    events = [
        record
        for record in caplog.records
        if getattr(record, "diagnostic_event", None) == "provider_management"
    ]
    assert any(
        record.operation == "refresh_models" and record.phase == "preserve_inventory"
        for record in events
    )
    assert any(
        record.operation == "refresh_models"
        and record.phase == "complete"
        and record.status == "failed"
        and record.duration_ms >= 0
        for record in events
    )
    assert all("OPENAI_KEY" not in record.getMessage() for record in events)


def test_default_local_connection_is_an_explicit_provider_use_case() -> None:
    service, port, _ = _service()
    port.product = replace(port.product, catalog_id="ollama", name="Ollama")

    result = service.ensure_default_local_connection(
        EnsureDefaultLocalProviderConnectionCommand()
    )

    assert result.catalog_id == "ollama"
    assert result.ensured is True
    assert port.ensure_local_calls == 1


def test_local_inspection_keeps_installed_models_outside_recommendation_catalog() -> (
    None
):
    service, port, _ = _service()
    service._local_technology = FakeInstalledLocalTechnology()

    result = service.inspect_local_provider(_principal(), InspectLocalProviderQuery())

    assert [item.model_id for item in result.models] == [
        "recommended",
        "custom-installed",
    ]
    assert result.models[1].installed is True
    assert result.installed_model_count == 1
    assert port.local_model_ids == ["custom-installed"]


def test_local_inspection_reads_cached_status_without_live_probe() -> None:
    service, _, _ = _service()
    cached = StoredLocalProviderStatus(
        state="healthy",
        endpoint="http://127.0.0.1:11434",
        version="0.1",
        memory_gb=8,
        recommended_model="recommended",
        installed_model_count=1,
        models=(
            StoredLocalProviderModelStatus(
                model_id="recommended",
                display_name="Recommended",
                installed=True,
                recommended=True,
                availability_status="available",
                available=True,
            ),
        ),
        model_counts=StoredLocalModelCounts(1, 1, 0, 0, 0),
        checked_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
    )
    cache = FakeLocalStatusCache(cached)
    service._local_status_cache = cache
    service._local_technology = FailingLocalTechnology()

    result = service.inspect_local_provider(_principal(), InspectLocalProviderQuery())

    assert result.state == "healthy"
    assert result.checked_at == cached.checked_at
    assert result.installed_model_count == 1
    assert cache.load_calls == 1


def test_stale_local_status_is_returned_and_refresh_is_scheduled_once() -> None:
    service, _, _ = _service()
    cached = StoredLocalProviderStatus(
        state="healthy",
        endpoint="http://127.0.0.1:11434",
        version="0.1",
        memory_gb=8,
        recommended_model=None,
        installed_model_count=0,
        models=(),
        model_counts=StoredLocalModelCounts(0, 0, 0, 0, 0),
        checked_at=(datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat(),
    )
    cache = FakeLocalStatusCache(cached)
    scheduler = QueueScheduler()
    service._local_status_cache = cache
    service._local_technology = FailingLocalTechnology()

    result = service.inspect_local_provider(
        _principal(),
        InspectLocalProviderQuery(),
        scheduler,
    )

    assert result.state == "healthy"
    assert len(scheduler.tasks) == 1
    assert cache.refresh_claims[0][1] == 300


def test_missing_local_status_is_unknown_and_refresh_is_scheduled() -> None:
    service, _, _ = _service()
    cache = FakeLocalStatusCache(None)
    scheduler = QueueScheduler()
    service._local_status_cache = cache

    result = service.inspect_local_provider(
        _principal(),
        InspectLocalProviderQuery(),
        scheduler,
    )

    assert result.state == "unknown"
    assert len(scheduler.tasks) == 1


def test_local_verification_only_probes_supported_installed_models() -> None:
    service, _, _ = _service()
    service._local_technology = FakeSupportedInstalledLocalTechnology()

    result = asyncio.run(service.verify_local_models(_principal()))

    technology = service._technology
    assert isinstance(technology, FakeTechnology)
    assert technology.probed_model_references == ["ollama_0001/recommended"]
    assert result.model_counts.available == 1


def test_background_local_validation_uses_the_same_supported_model_probe() -> None:
    service, _, _ = _service()
    service._local_technology = FakeSupportedInstalledLocalTechnology()
    cache = FakeLocalStatusCache(None)
    service._local_status_cache = cache

    result = service.refresh_local_provider_validation()

    technology = service._technology
    assert isinstance(technology, FakeTechnology)
    assert technology.probed_model_references == ["ollama_0001/recommended"]
    assert result.model_counts.available == 1
    assert [status.model_counts.available for status in cache.saved] == [1]


def test_member_cannot_read_provider_administration() -> None:
    service, _, _ = _service()

    with pytest.raises(ProvidersForbidden):
        service.list_connections(_principal("user"), ListProviderConnectionsQuery())


def test_list_connections_is_read_only() -> None:
    service, port, _ = _service()

    assert service.list_connections(_principal(), ListProviderConnectionsQuery()) == ()
    assert port.ensure_local_calls == 0


def test_list_connections_projects_the_whole_inventory_once() -> None:
    service, port, _ = _service()
    port.items = {
        connection_id: StoredProviderConnection(
            connection_id=connection_id,
            catalog_id="openai_api",
            alias=connection_id,
            api_base="https://api.openai.com/v1",
            api_mode="chat_completions",
            auth_type="bearer",
            credential_ref="",
            models=(StoredProviderModel("model-a", "Model A"),),
        )
        for connection_id in ("openai_api_0001", "openai_api_0002")
    }

    result = service.list_connections(_principal(), ListProviderConnectionsQuery())

    technology = service._technology
    assert isinstance(technology, FakeTechnology)
    assert len(result) == 2
    assert technology.projection_calls == [("openai_api_0001", "openai_api_0002")]
    assert technology.connection_summary_calls == 0
    assert technology.model_summary_calls == []


def test_provider_projection_separates_inventory_from_model_evidence() -> None:
    service, port, _ = _service()
    connection = StoredProviderConnection(
        connection_id="openai_api_0001",
        catalog_id="openai_api",
        alias="OpenAI",
        api_base="https://api.openai.com/v1",
        api_mode="chat_completions",
        auth_type="bearer",
        credential_ref="OPENAI_KEY",
        models=(
            StoredProviderModel("available", "Available"),
            StoredProviderModel("pending", "Pending"),
            StoredProviderModel("unavailable", "Unavailable"),
            StoredProviderModel("hidden", "Hidden", hidden=True),
            StoredProviderModel(
                "missing",
                "Missing",
                discovery_state="source_missing",
            ),
        ),
    )
    port.items[connection.connection_id] = connection
    technology = service._technology
    assert isinstance(technology, FakeTechnology)
    technology.model_verifications = {
        "available": StoredModelVerification(
            status="passed",
            availability_status="available",
            is_core=True,
        ),
        "unavailable": StoredModelVerification(
            status="failed",
            availability_status="unavailable",
        ),
        "hidden": StoredModelVerification(
            status="passed",
            availability_status="available",
        ),
    }

    result = service.list_connections(_principal(), ListProviderConnectionsQuery())[0]
    assert result.model_counts.total == 4
    assert result.model_counts.enabled == 3
    assert result.model_counts.in_use == 1
    assert result.model_counts.available == 1
    assert result.model_counts.pending == 1
    assert result.model_counts.unavailable == 1
    projected = {item.model_id: item for item in result.models}
    assert projected["available"].available is True
    assert projected["pending"].available is False
    assert projected["unavailable"].available is False


def test_delete_preserves_food_reference_protection() -> None:
    service, port, references = _service()
    created = asyncio.run(
        service.create_connection(
            _principal(),
            CreateProviderConnectionCommand(catalog_id="openai_api"),
        )
    )
    service.change_lifecycle(
        _principal(),
        ChangeProviderConnectionLifecycleCommand(created.connection_id, "archive"),
    )
    references.connection_references = ("default-food",)

    with pytest.raises(ProvidersConflict):
        service.delete_connection(
            _principal(),
            DeleteProviderConnectionCommand(created.connection_id),
        )

    assert created.connection_id in port.items


def test_delete_allows_unused_unarchived_connection() -> None:
    service, port, _ = _service()
    created = asyncio.run(
        service.create_connection(
            _principal(),
            CreateProviderConnectionCommand(catalog_id="openai_api"),
        )
    )

    service.delete_connection(
        _principal(),
        DeleteProviderConnectionCommand(created.connection_id),
    )

    assert created.connection_id not in port.items


def test_manual_model_management_reuses_connection_fact() -> None:
    service, _, _ = _service()
    created = asyncio.run(
        service.create_connection(
            _principal(),
            CreateProviderConnectionCommand(catalog_id="openai_api"),
        )
    )

    model = service.add_model(
        _principal(),
        AddProviderModelCommand(
            created.connection_id,
            ProviderModelInput("gpt-test", display_name="Test"),
        ),
    )
    listed = service.list_connections(_principal(), ListProviderConnectionsQuery())

    assert model.model_id == "gpt-test"
    assert listed[0].models[0].display_name == "Test"


def test_cleanup_obsolete_models_rechecks_food_references_before_replacement() -> None:
    service, port, references = _service()
    connection = StoredProviderConnection(
        connection_id="openai_api_0001",
        catalog_id="openai_api",
        alias="OpenAI",
        api_base="https://api.openai.com/v1",
        api_mode="chat_completions",
        auth_type="bearer",
        credential_ref="",
        models=(
            StoredProviderModel(
                "obsolete",
                "Obsolete",
                source="bundled_catalog",
                discovery_state="source_missing",
            ),
            StoredProviderModel("keep", "Keep", source="manual"),
        ),
    )
    port.items[connection.connection_id] = connection
    technology = service._technology
    assert isinstance(technology, FakeTechnology)
    technology.obsolete_ids = ("obsolete",)

    result = service.cleanup_obsolete_models(
        _principal(),
        CleanupObsoleteProviderModelsCommand(connection.connection_id),
    )

    assert result.model_ids == ("obsolete",)
    assert [item.model_id for item in port.items[connection.connection_id].models] == [
        "keep"
    ]
    references.model_references = ("food-reference",)
    port.items[connection.connection_id] = connection
    result = service.cleanup_obsolete_models(
        _principal(),
        CleanupObsoleteProviderModelsCommand(connection.connection_id),
    )
    assert result.model_ids == ()


def test_model_replacement_preserves_omitted_endpoint_profile_and_capability() -> None:
    service, port, _ = _service()
    created = asyncio.run(
        service.create_connection(
            _principal(),
            CreateProviderConnectionCommand(catalog_id="openai_api"),
        )
    )
    current = port.items[created.connection_id]
    configured = replace(
        current.models[0]
        if current.models
        else StoredProviderModel("gpt-test", "GPT Test"),
        model_id="gpt-test",
        display_name="GPT Test",
        supports_structured_output=True,
        request_profile_id="openai.chat_completions",
        request_profile_version=1,
        capability_evidence={"structured_output": "verified"},
    )
    port.items[created.connection_id] = replace(current, models=(configured,))

    service.replace_models(
        _principal(),
        ReplaceProviderModelsCommand(
            created.connection_id,
            (
                ProviderModelReplacement(
                    model_id="gpt-test",
                    display_name="GPT Test Updated",
                    original_model_id="gpt-test",
                    hidden=False,
                    fields=frozenset({"id", "original_id", "display_name", "hidden"}),
                ),
            ),
        ),
    )

    restored = port.items[created.connection_id].models[0]
    assert restored.display_name == "GPT Test Updated"
    assert restored.supports_structured_output is True
    assert restored.request_profile_id == "openai.chat_completions"
    assert restored.request_profile_version == 1
    assert restored.capability_evidence["structured_output"] == "verified"


def test_local_cli_removal_deletes_default_ollama_connection() -> None:
    service, port, _ = _service()
    port.product = replace(
        port.product,
        catalog_id="ollama",
        name="Ollama",
        connection_method="local",
        usage_scope="local",
        discovery_strategy="ollama",
        api_mode="ollama",
        api_base="http://localhost:11434",
        auth_type="none",
    )
    created = asyncio.run(
        service.create_connection(
            _principal(),
            CreateProviderConnectionCommand(catalog_id="ollama"),
        )
    )

    result = service.remove_local_connection(
        _principal(),
        RemoveLocalProviderConnectionCommand(created.connection_id),
    )

    assert result.connection_id == created.connection_id
    assert port.items == {}
