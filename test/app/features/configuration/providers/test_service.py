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
    ListProviderConnectionsQuery,
    ProviderModelInput,
    ProviderPortError,
    ProvidersConflict,
    ProvidersForbidden,
    ProvidersService,
    StoredBenchmarkRun,
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

    def list_products(self) -> tuple[StoredProviderProduct, ...]:
        return (self.product,)

    def get_product(self, catalog_id: str) -> StoredProviderProduct | None:
        return self.product if catalog_id == self.product.catalog_id else None

    def ensure_local_connection(self, product: StoredProviderProduct) -> None:
        _ = product

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


def _service() -> tuple[ProvidersService, FakeProviderPort, FakeReferences]:
    port = FakeProviderPort()
    references = FakeReferences()
    return (
        ProvidersService(
            catalog=port,
            connections=port,
            references=references,
            technology=FakeTechnology(),
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


def test_member_cannot_read_provider_administration() -> None:
    service, _, _ = _service()

    with pytest.raises(ProvidersForbidden):
        service.list_connections(_principal("user"), ListProviderConnectionsQuery())


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
