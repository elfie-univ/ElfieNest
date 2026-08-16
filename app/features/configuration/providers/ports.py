"""Technical Ports consumed by Provider administration."""

from __future__ import annotations

from datetime import timedelta
from typing import Awaitable, Callable, Protocol

from .models import ProviderModelInput
from .port_models import (
    StoredBenchmarkCombination,
    StoredBenchmarkRun,
    StoredLocalProviderBinding,
    StoredLocalProviderCandidate,
    StoredLocalProviderProbe,
    StoredModelAvailability,
    StoredModelMatrix,
    StoredModelRefresh,
    StoredModelVerification,
    StoredProviderConnection,
    StoredProviderModel,
    StoredProviderOAuthLoginStart,
    StoredProviderOAuthLoginStatus,
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


class ProviderOAuthPort(Protocol):
    async def start_login(self, catalog_id: str) -> StoredProviderOAuthLoginStart: ...

    async def poll_login(self, login_id: str) -> StoredProviderOAuthLoginStatus: ...


class ProviderLocalStatePort(Protocol):
    def load_local_binding(self) -> StoredLocalProviderBinding | None: ...

    def save_local_binding(
        self, binding: StoredLocalProviderBinding
    ) -> StoredLocalProviderBinding: ...

    def list_local_model_ids(self) -> tuple[str, ...]: ...

    def save_local_model(self, model_id: str) -> str: ...

    def local_model_reference(self, model_id: str) -> str | None: ...

    def replace_local_models(self, model_ids: tuple[str, ...]) -> None: ...


class ProviderLocalTechnologyPort(Protocol):
    def default_binding(self) -> StoredLocalProviderBinding: ...

    def probe(
        self, binding: StoredLocalProviderBinding
    ) -> StoredLocalProviderProbe: ...

    def available_memory_gb(self) -> int: ...

    def candidate_models(self) -> tuple[StoredLocalProviderCandidate, ...]: ...

    def list_models(self, binding: StoredLocalProviderBinding) -> tuple[str, ...]: ...

    def install_official(self) -> StoredLocalProviderBinding: ...

    def start(
        self, binding: StoredLocalProviderBinding
    ) -> StoredLocalProviderBinding: ...

    def pull_model(
        self, binding: StoredLocalProviderBinding, model_id: str
    ) -> None: ...


class BackgroundTaskScheduler(Protocol):
    def add_task(self, func: Callable[[], None]) -> None: ...


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

    async def probe_model(self, reference: str) -> None: ...

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


class ProviderAvailabilityPort(Protocol):
    """Passive exact Endpoint availability projection for App consumers."""

    def get(self, reference: str) -> StoredModelAvailability: ...

    def get_many(
        self, references: tuple[str, ...]
    ) -> tuple[StoredModelAvailability, ...]: ...

    def ensure(
        self,
        reference: str,
        *,
        max_age: timedelta = timedelta(hours=24),
        allow_probe: bool = False,
    ) -> StoredModelAvailability: ...


__all__ = (
    "CancellationCheck",
    "ProviderCatalogPort",
    "ProviderConnectionPort",
    "ProviderOAuthPort",
    "ProviderLocalStatePort",
    "ProviderLocalTechnologyPort",
    "BackgroundTaskScheduler",
    "ProviderPortError",
    "ProviderPortNotFound",
    "ProviderReferencePort",
    "ProviderTechnologyPort",
    "ProviderAvailabilityPort",
)
