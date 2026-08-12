from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from app.features.accounts import AccountPrincipal, AccountRole
from app.features.configuration import (
    AddProviderModelCommand,
    ChangeProviderConnectionLifecycleCommand,
    CreateProviderConnectionCommand,
    DeleteProviderConnectionCommand,
    EnsureDefaultLocalProviderConnectionCommand,
    ListProviderConnectionsQuery,
    ProviderModelInput,
    ProviderPortError,
    ProvidersConflict,
    ProvidersForbidden,
    ProvidersService,
    RemoveLocalProviderConnectionCommand,
    StoredBenchmarkRun,
    StoredLocalProviderBinding,
    StoredLocalProviderCandidate,
    StoredLocalProviderProbe,
    StoredModelMatrix,
    StoredModelRefresh,
    StoredModelVerification,
    StoredProviderBrand,
    StoredProviderConnection,
    StoredProviderModel,
    StoredProviderProduct,
    StoredValidationRun,
    StoredVerification,
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
                "ELFIE_PROVIDER_OPENAI_API_0001_API_KEY" if api_key else ""
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
        return ()

    def save_local_model(self, model_id: str) -> str:
        return f"ollama_0001/{model_id}"

    def local_model_reference(self, model_id: str) -> str | None:
        _ = model_id
        return None

    def replace_local_models(self, model_ids: tuple[str, ...]) -> None:
        _ = model_ids


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
    def prepare_manual_model(self, model: ProviderModelInput) -> StoredProviderModel:
        return StoredProviderModel(model.model_id, model.display_name or model.model_id)

    def summarize_connection(
        self,
        connection: StoredProviderConnection,
    ) -> StoredVerification:
        _ = connection
        return StoredVerification()

    def summarize_model(
        self,
        connection_id: str,
        model_id: str,
    ) -> StoredModelVerification:
        _ = connection_id, model_id
        return StoredModelVerification()

    async def verify_connection(
        self,
        connection: StoredProviderConnection,
        *,
        force_full: bool,
    ) -> StoredVerification:
        _ = connection, force_full
        return StoredVerification(status="passed", validation_mode="full")

    async def refresh_models(
        self,
        connection: StoredProviderConnection,
    ) -> StoredModelRefresh:
        return StoredModelRefresh(
            "updated", "2026-08-10T00:00:00+00:00", None, connection.models
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
        ),
        port,
        references,
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


def test_default_local_connection_is_an_explicit_provider_use_case() -> None:
    service, port, _ = _service()
    port.product = replace(port.product, catalog_id="ollama", name="Ollama")

    result = service.ensure_default_local_connection(
        EnsureDefaultLocalProviderConnectionCommand()
    )

    assert result.catalog_id == "ollama"
    assert result.ensured is True
    assert port.ensure_local_calls == 1


def test_member_cannot_read_provider_administration() -> None:
    service, _, _ = _service()

    with pytest.raises(ProvidersForbidden):
        service.list_connections(_principal("user"), ListProviderConnectionsQuery())


def test_list_connections_is_read_only() -> None:
    service, port, _ = _service()

    assert service.list_connections(_principal(), ListProviderConnectionsQuery()) == ()
    assert port.ensure_local_calls == 0


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
