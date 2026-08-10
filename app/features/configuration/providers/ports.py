"""Technical Ports consumed by Provider administration."""

from __future__ import annotations

from typing import Awaitable, Callable, Protocol

from .models import ProviderModelInput
from .port_models import (
    StoredBenchmarkCombination,
    StoredBenchmarkRun,
    StoredModelMatrix,
    StoredModelRefresh,
    StoredModelVerification,
    StoredProviderConnection,
    StoredProviderModel,
    StoredProviderProduct,
    StoredValidationRun,
    StoredVerification,
)


class ProviderPortError(RuntimeError):
    """A Provider technical boundary could not complete an operation."""


class ProviderPortNotFound(ProviderPortError):
    """A requested connection or model is absent from the technical store."""


class ProviderCatalogPort(Protocol):
    def list_products(self) -> tuple[StoredProviderProduct, ...]: ...

    def get_product(self, catalog_id: str) -> StoredProviderProduct | None: ...


class ProviderConnectionPort(Protocol):
    def ensure_local_connection(self, product: StoredProviderProduct) -> None: ...

    def list_connections(self) -> tuple[StoredProviderConnection, ...]: ...

    def get_connection(self, connection_id: str) -> StoredProviderConnection | None: ...

    def create_connection(
        self,
        connection: StoredProviderConnection,
        api_key: str | None,
    ) -> StoredProviderConnection: ...

    def replace_connection(
        self,
        connection: StoredProviderConnection,
        api_key: str | None,
        *,
        update_credential: bool,
    ) -> StoredProviderConnection: ...

    def delete_connection(self, connection_id: str) -> bool: ...

    def has_credential(self, credential_ref: str) -> bool: ...


class ProviderReferencePort(Protocol):
    def connections_referenced_by_food(self, connection_id: str) -> tuple[str, ...]: ...

    def models_referenced_by_food(
        self,
        connection_id: str,
        model_id: str,
    ) -> tuple[str, ...]: ...


CancellationCheck = Callable[[], Awaitable[bool]]


class ProviderTechnologyPort(Protocol):
    def prepare_manual_model(
        self, model: ProviderModelInput
    ) -> StoredProviderModel: ...

    def summarize_connection(
        self,
        connection: StoredProviderConnection,
    ) -> StoredVerification: ...

    def summarize_model(
        self,
        connection_id: str,
        model_id: str,
    ) -> StoredModelVerification: ...

    async def verify_connection(
        self,
        connection: StoredProviderConnection,
        *,
        force_full: bool,
    ) -> StoredVerification: ...

    async def refresh_models(
        self,
        connection: StoredProviderConnection,
    ) -> StoredModelRefresh: ...

    def model_matrix(
        self,
        connections: tuple[StoredProviderConnection, ...],
        *,
        as_of: str | None,
        run_id: str | None,
    ) -> StoredModelMatrix: ...

    async def benchmark_models(
        self,
        connections: tuple[StoredProviderConnection, ...],
        combinations: tuple[StoredBenchmarkCombination, ...],
    ) -> StoredBenchmarkRun: ...

    async def validate_all(
        self,
        connections: tuple[StoredProviderConnection, ...],
        cancelled: CancellationCheck,
    ) -> StoredValidationRun: ...


__all__ = (
    "CancellationCheck",
    "ProviderCatalogPort",
    "ProviderConnectionPort",
    "ProviderPortError",
    "ProviderPortNotFound",
    "ProviderReferencePort",
    "ProviderTechnologyPort",
)
