"""Provider connection, secret, discovery and report Adapters."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Literal, Mapping, Optional, cast

from app.features.configuration import (
    ApiMode,
    AuthType,
    CancellationCheck,
    LatencyClass,
    ModelSource,
    ProviderModelInput,
    ProviderPortError,
    StoredBenchmarkCombination,
    StoredBenchmarkResult,
    StoredBenchmarkRun,
    StoredLocalProviderBinding,
    StoredMatrixCell,
    StoredMatrixConnection,
    StoredMatrixModel,
    StoredMatrixSnapshot,
    StoredModelMatrix,
    StoredModelRefresh,
    StoredModelVerification,
    StoredProviderBrand,
    StoredProviderConnection,
    StoredProviderModel,
    StoredProviderProduct,
    StoredValidationItem,
    StoredValidationRun,
    StoredVerification,
    ValidationMode,
)
from app.features.configuration.providers import (
    ValidationStatus as ProviderValidationStatus,
)
from infrastructure.models.oauth_credentials import OAuthCredentialPort
from infrastructure.models.provider_records import (
    ProviderConnection,
    ProviderModelRecord,
)
from infrastructure.models.providers.catalog import ProviderCatalog
from infrastructure.models.providers.discovery import (
    bundled_catalog_models,
    merge_refreshed_models,
    remote_catalog_models,
)
from infrastructure.models.providers.model_identity import match_model_identity
from infrastructure.models.providers.remote_catalog import (
    RemoteCatalogUnavailable,
    fetch_remote_models,
)
from infrastructure.models.storage_ports import (
    ModelEvidencePort,
    ProviderStorageError,
    ProviderStoragePort,
    ReportStoragePort,
)
from infrastructure.models.validation.provider_model_benchmark import (
    bounded_benchmark,
    validate_combinations,
)
from infrastructure.models.validation.provider_model_matrix import build_model_matrix
from infrastructure.models.validation.provider_validation import (
    DiscoveredModel,
    discover_provider_models,
)
from infrastructure.models.validation.provider_validation_execution import (
    model_execution_projection,
)
from infrastructure.models.validation.provider_validation_service import (
    summarize_connection_validation,
    validate_connection,
)
from infrastructure.persistence.provider_catalog import load_provider_catalog

from .provider_errors import sanitize_error

_DISCOVERY_TIMEOUT_SECONDS = 7.0
_DISCOVERY_SLOTS = threading.BoundedSemaphore(3)
_BENCHMARK_CONCURRENCY = 2


class ProviderModelsAdapter:
    """Implement all Providers-owned technical Ports over existing v2 facts."""

    def __init__(
        self,
        storage: ProviderStoragePort,
        reports: ReportStoragePort,
        evidence: ModelEvidencePort,
        oauth_credentials: OAuthCredentialPort | None = None,
        catalog: ProviderCatalog | None = None,
    ) -> None:
        self._store = storage
        self._reports = reports
        self._evidence = evidence
        self._oauth_credentials = oauth_credentials
        self._catalog = catalog or load_provider_catalog()

    def list_products(self) -> tuple[StoredProviderProduct, ...]:
        try:
            return tuple(
                self._product(catalog_id) for catalog_id in self._catalog.products
            )
        except (KeyError, ValueError) as error:
            raise ProviderPortError("Provider catalog is invalid") from error

    def get_product(self, catalog_id: str) -> StoredProviderProduct | None:
        if catalog_id not in self._catalog.products:
            return None
        try:
            return self._product(catalog_id)
        except (KeyError, ValueError) as error:
            raise ProviderPortError("Provider catalog is invalid") from error

    def ensure_local_connection(self, product: StoredProviderProduct) -> None:
        try:
            if any(
                item.catalog_id == product.catalog_id
                for item in self._store.load_connections().values()
            ):
                return
            self._store.create(
                catalog_id=product.catalog_id,
                alias=product.name,
                api_base=product.api_base,
                api_mode=product.api_mode,
                auth_type=product.auth_type,
            )
        except (ProviderStorageError, ValueError, OSError) as error:
            raise ProviderPortError(
                "Unable to create local Provider connection"
            ) from error

    def list_connections(self) -> tuple[StoredProviderConnection, ...]:
        try:
            return tuple(
                self._connection(item)
                for item in self._store.load_connections().values()
            )
        except (ProviderStorageError, ValueError, OSError) as error:
            raise ProviderPortError("Unable to read Provider connections") from error

    def get_connection(self, connection_id: str) -> StoredProviderConnection | None:
        try:
            item = self._store.load_connections().get(connection_id)
            return None if item is None else self._connection(item)
        except (ProviderStorageError, ValueError, OSError) as error:
            raise ProviderPortError("Unable to read Provider connection") from error

    def create_connection(
        self,
        connection: StoredProviderConnection,
        api_key: str | None,
    ) -> StoredProviderConnection:
        try:
            created = self._store.create(
                catalog_id=connection.catalog_id,
                alias=connection.alias,
                api_base=connection.api_base,
                api_mode=connection.api_mode,
                auth_type=connection.auth_type,
                credential_ref=connection.credential_ref,
                models=tuple(self._provider_model(item) for item in connection.models),
            )
            created = self._store.create_with_secret(created, api_key)
            return self._connection(created)
        except (ProviderStorageError, ValueError, OSError) as error:
            raise ProviderPortError("Unable to create Provider connection") from error

    def replace_connection(
        self,
        connection: StoredProviderConnection,
        api_key: str | None,
        *,
        update_credential: bool,
    ) -> StoredProviderConnection:
        provider_connection = self._provider_connection(connection)
        try:
            if update_credential:
                provider_connection = self._store.replace_with_secret(
                    provider_connection, api_key
                )
            else:
                self._store.replace(provider_connection)
            return self._connection(provider_connection)
        except (ProviderStorageError, ValueError, OSError) as error:
            raise ProviderPortError("Unable to replace Provider connection") from error

    def delete_connection(self, connection_id: str) -> bool:
        try:
            connection = self._store.load_connections().get(connection_id)
            deleted = self._store.delete_with_secret(connection_id)
            if (
                deleted
                and connection is not None
                and connection.credential_ref.startswith("oauth.")
                and self._oauth_credentials is not None
            ):
                self._oauth_credentials.delete(connection.credential_ref)
            return deleted
        except (ProviderStorageError, ValueError, OSError) as error:
            raise ProviderPortError("Unable to delete Provider connection") from error

    def has_credential(self, credential_ref: str) -> bool:
        if not credential_ref:
            return False
        try:
            if credential_ref.startswith("oauth."):
                return (
                    self._oauth_credentials is not None
                    and self._oauth_credentials.has(credential_ref)
                )
            return self._store.has_secret(credential_ref)
        except (ProviderStorageError, OSError) as error:
            raise ProviderPortError("Unable to resolve Provider credential") from error

    def load_local_binding(self) -> StoredLocalProviderBinding | None:
        try:
            connection = self._local_connection()
            if (
                connection is None
                or not connection.installation
                or not connection.api_base
            ):
                return None
            raw = connection.installation
            platform = str(raw.get("platform", ""))
            if platform not in {"darwin", "linux", "win32"}:
                return None
            return StoredLocalProviderBinding(
                api_base=connection.api_base,
                platform=cast(Literal["darwin", "linux", "win32"], platform),
                install_kind=str(raw.get("install_kind", "existing-public")),
                launch_target=str(raw.get("launch_target", "")),
                version=str(raw.get("version", "")),
                installer_source_url=str(raw.get("installer_source_url", "")),
                installer_sha256=str(raw.get("installer_sha256", "")),
            )
        except (ProviderStorageError, ValueError, OSError) as error:
            raise ProviderPortError("Unable to read local Provider binding") from error

    def save_local_binding(
        self,
        binding: StoredLocalProviderBinding,
    ) -> StoredLocalProviderBinding:
        installation = {
            "platform": binding.platform,
            "install_kind": binding.install_kind,
            "launch_target": binding.launch_target,
            "version": binding.version,
            "installer_source_url": binding.installer_source_url,
            "installer_sha256": binding.installer_sha256,
        }
        try:
            connection = self._local_connection()
            if connection is None:
                self._store.create(
                    catalog_id="ollama",
                    alias="Ollama",
                    api_base=binding.api_base,
                    api_mode="ollama",
                    auth_type="none",
                    installation=installation,
                )
            else:
                self._store.replace(
                    replace(
                        connection,
                        api_base=binding.api_base,
                        api_mode="ollama",
                        auth_type="none",
                        installation=installation,
                        enabled=True,
                        archived=False,
                    )
                )
        except (ProviderStorageError, ValueError, OSError) as error:
            raise ProviderPortError("Unable to save local Provider binding") from error
        return binding

    def list_local_model_ids(self) -> tuple[str, ...]:
        try:
            connection = self._local_connection()
            return (
                tuple(item.endpoint_model_id for item in connection.models)
                if connection is not None
                else ()
            )
        except (ProviderStorageError, ValueError, OSError) as error:
            raise ProviderPortError("Unable to read local Provider models") from error

    def save_local_model(self, model_id: str) -> str:
        try:
            connection = self._local_connection()
            if connection is None:
                raise ProviderPortError("Local Provider connection is missing")
            models = {item.endpoint_model_id: item for item in connection.models}
            models[model_id] = ProviderModelRecord(
                endpoint_model_id=model_id,
                display_name=model_id,
                source="official",
            )
            self._store.replace(replace(connection, models=tuple(models.values())))
            return f"{connection.connection_id}/{model_id}"
        except ProviderPortError:
            raise
        except (ProviderStorageError, ValueError, OSError) as error:
            raise ProviderPortError("Unable to save local Provider model") from error

    def local_model_reference(self, model_id: str) -> str | None:
        try:
            connection = self._local_connection()
            if connection is None or not any(
                item.endpoint_model_id == model_id for item in connection.models
            ):
                return None
            return f"{connection.connection_id}/{model_id}"
        except (ProviderStorageError, ValueError, OSError) as error:
            raise ProviderPortError("Unable to read local Provider model") from error

    def replace_local_models(self, model_ids: tuple[str, ...]) -> None:
        try:
            connection = self._local_connection()
            if connection is None:
                raise ProviderPortError("Local Provider connection is missing")
            previous = {item.endpoint_model_id: item for item in connection.models}
            models = tuple(
                replace(previous[model_id], source="official", available=True)
                if model_id in previous
                else ProviderModelRecord(
                    endpoint_model_id=model_id,
                    display_name=model_id,
                    source="official",
                )
                for model_id in model_ids
            )
            self._store.replace(replace(connection, models=models))
        except ProviderPortError:
            raise
        except (ProviderStorageError, ValueError, OSError) as error:
            raise ProviderPortError(
                "Unable to replace local Provider models"
            ) from error

    def _local_connection(self) -> ProviderConnection | None:
        return next(
            (
                item
                for item in self._store.load_connections().values()
                if item.catalog_id == "ollama"
            ),
            None,
        )

    def prepare_manual_model(self, model: ProviderModelInput) -> StoredProviderModel:
        match = match_model_identity(model.model_id, model.display_name)
        return StoredProviderModel(
            model_id=model.model_id,
            display_name=model.display_name or model.model_id,
            canonical_model_id=model.canonical_model_id
            or (match.canonical_model_id if match else None),
            source="manual",
            context_window_tokens=model.context_window_tokens
            or (match.context_window_tokens if match else None),
            max_output_tokens=model.max_output_tokens
            or (match.max_output_tokens if match else None),
            supports_tools=(
                model.supports_tools
                if model.supports_tools is not None
                else match.supports_tools
                if match
                else None
            ),
            supports_vision=(
                model.supports_vision
                if model.supports_vision is not None
                else match.supports_vision
                if match
                else None
            ),
            supports_reasoning=(
                model.supports_reasoning
                if model.supports_reasoning is not None
                else match.supports_reasoning
                if match
                else None
            ),
        )

    def summarize_connection(
        self,
        connection: StoredProviderConnection,
    ) -> StoredVerification:
        try:
            return self._verification(
                summarize_connection_validation(
                    self._provider_connection(connection),
                    reports=self._reports,
                    secret_resolver=self._resolve_credential,
                )
            )
        except (ValueError, OSError) as error:
            raise ProviderPortError("Unable to read Provider validation") from error

    def summarize_model(
        self,
        connection_id: str,
        model_id: str,
    ) -> StoredModelVerification:
        try:
            return self._model_verification(
                self._reports.read_latest_model_validation(
                    connection_id,
                    model_id,
                    validation_mode="full",
                )
            )
        except (ValueError, OSError) as error:
            raise ProviderPortError("Unable to read model validation") from error

    async def verify_connection(
        self,
        connection: StoredProviderConnection,
        *,
        force_full: bool,
    ) -> StoredVerification:
        try:
            result = await validate_connection(
                self._provider_connection(connection),
                model_execution_projection=self._model_execution_projection,
                reports=self._reports,
                secret_resolver=self._resolve_credential,
                force_full=force_full,
            )
            return self._verification(result)
        except (ValueError, OSError) as error:
            raise ProviderPortError("Unable to validate Provider connection") from error

    async def refresh_models(
        self,
        connection: StoredProviderConnection,
    ) -> StoredModelRefresh:
        provider_connection = self._provider_connection(connection)
        profile = self._catalog.products.get(connection.catalog_id)
        if profile is None:
            raise ProviderPortError("Provider product catalog entry is missing")
        checked_at = datetime.now(timezone.utc).isoformat()
        if profile.discovery_strategy == "catalog_only":
            bundled_models = bundled_catalog_models(profile.bundled_models)
            merged = merge_refreshed_models(provider_connection.models, bundled_models)
            return StoredModelRefresh(
                status="bundled_catalog",
                checked_at=checked_at,
                message=(
                    "火山引擎 Coding Plan 使用配置文件中的官方 Model Name 清单，"
                    "未使用 /models（通用模型列表与套餐不匹配）"
                ),
                models=tuple(self._model(item) for item in merged),
            )
        try:
            discovered = await asyncio.wait_for(
                asyncio.to_thread(self._discover_with_slot, provider_connection),
                timeout=_DISCOVERY_TIMEOUT_SECONDS,
            )
        except Exception as error:
            catalog_models: tuple[ProviderModelRecord, ...] = ()
            if connection.catalog_id != "custom_openai":
                try:
                    catalog_models = remote_catalog_models(
                        connection.catalog_id,
                        fetcher=fetch_remote_models,
                    )
                except RemoteCatalogUnavailable:
                    catalog_models = ()
                if not catalog_models:
                    catalog_models = bundled_catalog_models(profile.bundled_models)
            if catalog_models:
                merged = merge_refreshed_models(
                    provider_connection.models, catalog_models
                )
                return StoredModelRefresh(
                    status=catalog_models[0].source,
                    checked_at=checked_at,
                    message="模型接口不可用，已使用内置产品清单",
                    models=tuple(self._model(item) for item in merged),
                )
            message = sanitize_error(
                str(error),
                secrets=(self._resolve_credential(provider_connection.credential_ref),),
            )
            return StoredModelRefresh(
                status="failed",
                checked_at=checked_at,
                message=f"模型获取失败，请手工添加模型：{message}",
                models=connection.models,
            )
        models = tuple(
            self._provider_model(
                self.prepare_manual_model(
                    ProviderModelInput(
                        model_id=item.name,
                        display_name=item.display_name or item.name,
                    )
                ),
                source="official",
            )
            for item in discovered
        )
        if not models:
            return StoredModelRefresh(
                status="failed",
                checked_at=checked_at,
                message="模型接口未返回结果，请手工添加模型",
                models=connection.models,
            )
        merged = merge_refreshed_models(provider_connection.models, models)
        return StoredModelRefresh(
            status="updated",
            checked_at=checked_at,
            message=None,
            models=tuple(self._model(item) for item in merged),
        )

    def model_matrix(
        self,
        connections: tuple[StoredProviderConnection, ...],
        *,
        as_of: str | None,
        run_id: str | None,
    ) -> StoredModelMatrix:
        repository = self._reports
        observations = (
            repository.observations_for_run(run_id)
            if run_id
            else repository.as_of(as_of)
            if as_of
            else repository.current()
        )
        snapshot: dict[str, Any] = {
            "mode": "run" if run_id else "as_of" if as_of else "current",
            "run_id": run_id,
            "as_of": as_of,
        }
        if run_id:
            run = repository.get_run(run_id)
            snapshot.update(
                status=run.status,
                started_at=run.started_at,
                finished_at=run.finished_at,
            )
        payload = build_model_matrix(
            {
                item.connection_id: self._provider_connection(item)
                for item in connections
            },
            observations=observations,
            model_evidence={
                item.reference: item for item in self._evidence.list_model_evidence()
            },
            provider_validation_reader=self._reports.read_latest_provider_validation,
            snapshot=snapshot,
        )
        return self._matrix(payload)

    async def benchmark_models(
        self,
        connections: tuple[StoredProviderConnection, ...],
        combinations: tuple[StoredBenchmarkCombination, ...],
    ) -> StoredBenchmarkRun:
        by_id = {
            item.connection_id: self._provider_connection(item) for item in connections
        }
        validate_combinations(list(combinations), by_id)
        semaphore = asyncio.Semaphore(_BENCHMARK_CONCURRENCY)
        raw_results = await asyncio.gather(
            *(
                bounded_benchmark(
                    item,
                    by_id[item.connection_id],
                    semaphore,
                    model_execution_projection=self._model_execution_projection,
                )
                for item in combinations
            )
        )
        checked_at = datetime.now(timezone.utc).isoformat()
        repository = self._reports
        run_id = repository.start_run(
            scope="model-selection",
            trigger="benchmark",
            started_at=checked_at,
        )
        results: list[StoredBenchmarkResult] = []
        for combination, raw in zip(combinations, raw_results):
            connection = by_id[combination.connection_id]
            status = "passed" if raw.get("status") == "passed" else "failed"
            latency = raw.get("latency_ms")
            latency_ms = float(latency) if isinstance(latency, (int, float)) else None
            latency_class = self._latency_class(raw.get("latency_class"))
            error = sanitize_error(
                cast(Optional[str], raw.get("error")),
                secrets=(self._resolve_credential(connection.credential_ref),),
            )
            self._reports.write_model_validation_report(
                combination.connection_id,
                combination.model_id,
                status=status,
                checked_at=checked_at,
                latency_ms=latency_ms,
                latency_class=latency_class,
                error=error,
                trigger="benchmark",
                run_id=run_id,
            )
            results.append(
                StoredBenchmarkResult(
                    connection_id=combination.connection_id,
                    model_id=combination.model_id,
                    status=cast(Any, status),
                    checked_at=checked_at,
                    latency_ms=latency_ms,
                    latency_class=latency_class,
                    error=error,
                )
            )
        repository.finish_run(run_id, status="complete", finished_at=checked_at)
        return StoredBenchmarkRun(
            run_id=run_id,
            status="complete",
            results=tuple(results),
        )

    async def validate_all(
        self,
        connections: tuple[StoredProviderConnection, ...],
        cancelled: CancellationCheck,
    ) -> StoredValidationRun:
        repository = self._reports
        started_at = datetime.now(timezone.utc).isoformat()
        run_id = repository.start_run(
            scope="all-enabled-connections-and-models",
            trigger="validate_all",
            started_at=started_at,
        )
        results: list[StoredValidationItem] = []
        status = "complete"
        try:
            for stored in connections:
                if await cancelled():
                    status = "partial"
                    break
                verification = await validate_connection(
                    self._provider_connection(stored),
                    model_execution_projection=self._model_execution_projection,
                    reports=self._reports,
                    secret_resolver=self._resolve_credential,
                    run_id=run_id,
                    trigger="batch",
                    force_full=True,
                )
                results.append(
                    StoredValidationItem(
                        subject=f"provider:{stored.connection_id}",
                        status=str(verification.get("status") or "failed"),
                        checked_at=self._optional_string(
                            verification.get("checked_at")
                        ),
                    )
                )
                raw_models = verification.get("model_results", ())
                if isinstance(raw_models, list):
                    for raw in raw_models:
                        if not isinstance(raw, Mapping):
                            continue
                        model_id = str(raw.get("model_id") or "")
                        results.append(
                            StoredValidationItem(
                                subject=f"model:{stored.connection_id}/{model_id}",
                                status=str(raw.get("status") or "failed"),
                                checked_at=self._optional_string(raw.get("checked_at")),
                            )
                        )
        except asyncio.CancelledError:
            status = "partial"
            raise
        except Exception as error:
            status = "partial" if results else "failed"
            raise ProviderPortError("Provider validation failed") from error
        finally:
            repository.finish_run(
                run_id,
                status=status,
                finished_at=datetime.now(timezone.utc).isoformat(),
            )
        return StoredValidationRun(run_id, status, tuple(results))

    def _discover_with_slot(
        self, connection: ProviderConnection
    ) -> list[DiscoveredModel]:
        if not _DISCOVERY_SLOTS.acquire(blocking=False):
            raise RuntimeError("模型发现任务过多，请稍后重试")
        try:
            execution_id, config = self._model_execution_projection(connection)
            return discover_provider_models(
                execution_id,
                config,
                timeout=5.0,
                allow_configured_fallback=False,
            )
        finally:
            _DISCOVERY_SLOTS.release()

    def _model_execution_projection(
        self, connection: ProviderConnection
    ) -> tuple[str, Any]:
        execution_id, config = model_execution_projection(
            connection,
            catalog=self._catalog,
            secret_resolver=self._resolve_credential,
        )
        if connection.credential_ref.startswith("oauth."):
            token = (
                None
                if self._oauth_credentials is None
                else self._oauth_credentials.load(connection.credential_ref)
            )
            config.oauth_credentials = self._oauth_credentials
            config.providers[execution_id]["credential_ref"] = connection.credential_ref
            config.providers[execution_id]["account_id"] = (
                None if token is None else token.account_id
            )
        return execution_id, config

    def _resolve_credential(self, credential_ref: str) -> str:
        if credential_ref.startswith("oauth.") and self._oauth_credentials is not None:
            token = self._oauth_credentials.load(credential_ref)
            return "" if token is None else token.access_token
        return self._store.resolve_secret(credential_ref)

    def _product(self, catalog_id: str) -> StoredProviderProduct:
        profile = self._catalog.products[catalog_id]
        brand = self._catalog.brands[profile.brand_id]
        return StoredProviderProduct(
            catalog_id=catalog_id,
            name=profile.name,
            brand=StoredProviderBrand(
                brand_id=profile.brand_id,
                name=brand.name,
                logo_asset=brand.logo_asset,
            ),
            connection_method=profile.connection_method,
            oauth_available=profile.oauth_available,
            usage_scope=profile.usage_scope,
            discovery_strategy=profile.discovery_strategy,
            api_mode=cast(ApiMode, profile.api_mode),
            api_base=profile.api_base,
            auth_type=cast(AuthType, profile.auth_type),
        )

    @classmethod
    def _connection(cls, item: ProviderConnection) -> StoredProviderConnection:
        return StoredProviderConnection(
            connection_id=item.connection_id,
            catalog_id=item.catalog_id,
            alias=item.alias,
            api_base=item.api_base,
            api_mode=cast(ApiMode, item.api_mode),
            auth_type=cast(AuthType, item.auth_type),
            credential_ref=item.credential_ref,
            models=tuple(cls._model(model) for model in item.models),
            enabled=item.enabled,
            archived=item.archived,
        )

    @classmethod
    def _provider_connection(cls, item: StoredProviderConnection) -> ProviderConnection:
        return ProviderConnection(
            connection_id=item.connection_id,
            catalog_id=item.catalog_id,
            alias=item.alias,
            api_base=item.api_base,
            api_mode=item.api_mode,
            auth_type=item.auth_type,
            credential_ref=item.credential_ref,
            models=tuple(cls._provider_model(model) for model in item.models),
            enabled=item.enabled,
            archived=item.archived,
        )

    @staticmethod
    def _model(item: ProviderModelRecord) -> StoredProviderModel:
        return StoredProviderModel(
            model_id=item.endpoint_model_id,
            display_name=item.display_name,
            canonical_model_id=item.canonical_model_id,
            source=item.source,
            context_window_tokens=item.context_window_tokens,
            max_output_tokens=item.max_output_tokens,
            supports_tools=item.supports_tools,
            supports_vision=item.supports_vision,
            supports_reasoning=item.supports_reasoning,
            hidden=item.hidden,
            retired=item.retired,
            available=item.available,
        )

    @staticmethod
    def _provider_model(
        item: StoredProviderModel,
        *,
        source: ModelSource | None = None,
    ) -> ProviderModelRecord:
        return ProviderModelRecord(
            endpoint_model_id=item.model_id,
            display_name=item.display_name,
            canonical_model_id=item.canonical_model_id,
            source=source or item.source,
            context_window_tokens=item.context_window_tokens,
            max_output_tokens=item.max_output_tokens,
            supports_tools=item.supports_tools,
            supports_vision=item.supports_vision,
            supports_reasoning=item.supports_reasoning,
            hidden=item.hidden,
            retired=item.retired,
            available=item.available,
        )

    @classmethod
    def _verification(cls, raw: Mapping[str, Any]) -> StoredVerification:
        return StoredVerification(
            status=cls._validation_status(raw.get("status")),
            checked_at=cls._optional_string(raw.get("checked_at")),
            latency_ms=cls._optional_float(raw.get("latency_ms")),
            error=cls._optional_string(raw.get("error")),
            validation_mode=cls._validation_mode(raw.get("validation_mode")),
            cache_hit=raw.get("cache_hit") is True,
            needs_full_validation=raw.get("needs_full_validation") is True,
            needs_heartbeat=raw.get("needs_heartbeat") is True,
            full_run_id=cls._optional_string(raw.get("full_run_id")),
            full_checked_at=cls._optional_string(raw.get("full_checked_at")),
            heartbeat_checked_at=cls._optional_string(raw.get("heartbeat_checked_at")),
            heartbeat_status=cast(
                Any,
                raw.get("heartbeat_status")
                if raw.get("heartbeat_status") in {"passed", "failed"}
                else None,
            ),
            representative_model_id=cls._optional_string(
                raw.get("representative_model_id")
            ),
            reason=cls._optional_string(raw.get("reason")),
        )

    @classmethod
    def _model_verification(cls, raw: Mapping[str, Any]) -> StoredModelVerification:
        mode = raw.get("validation_mode")
        return StoredModelVerification(
            status=cls._validation_status(raw.get("status")),
            checked_at=cls._optional_string(raw.get("checked_at")),
            latency_ms=cls._optional_float(raw.get("latency_ms")),
            error=cls._optional_string(raw.get("error")),
            validation_mode=(None if mode is None else cls._validation_mode(mode)),
            full_run_id=cls._optional_string(raw.get("full_run_id")),
        )

    @classmethod
    def _matrix(cls, payload: Mapping[str, Any]) -> StoredModelMatrix:
        raw_snapshot = cls._mapping(payload.get("snapshot"))
        raw_connections = cls._sequence(payload.get("connections"))
        raw_models = cls._sequence(payload.get("models"))
        return StoredModelMatrix(
            snapshot=StoredMatrixSnapshot(
                mode=str(raw_snapshot.get("mode") or "current"),
                run_id=cls._optional_string(raw_snapshot.get("run_id")),
                as_of=cls._optional_string(raw_snapshot.get("as_of")),
                status=cls._optional_string(raw_snapshot.get("status")),
                started_at=cls._optional_string(raw_snapshot.get("started_at")),
                finished_at=cls._optional_string(raw_snapshot.get("finished_at")),
            ),
            connections=tuple(
                StoredMatrixConnection(
                    connection_id=str(item.get("connection_id") or ""),
                    name=str(item.get("name") or ""),
                    verification=cls._verification(
                        cls._mapping(item.get("verification"))
                    ),
                )
                for item in raw_connections
            ),
            models=tuple(
                StoredMatrixModel(
                    model_key=str(item.get("model_key") or ""),
                    display_name=str(item.get("display_name") or ""),
                    capabilities=tuple(
                        str(value) for value in cls._values(item.get("capabilities"))
                    ),
                    connections=tuple(
                        cls._matrix_cell(cell)
                        for cell in cls._sequence(item.get("connections"))
                    ),
                )
                for item in raw_models
            ),
        )

    @classmethod
    def _matrix_cell(cls, raw: Mapping[str, Any]) -> StoredMatrixCell:
        benchmark = raw.get("benchmark_status")
        return StoredMatrixCell(
            connection_id=str(raw.get("connection_id") or ""),
            model_id=cls._optional_string(raw.get("model_id")),
            available=raw.get("available") is True,
            verification_status=cls._validation_status(raw.get("verification_status")),
            benchmark_status=cast(
                Any,
                benchmark if benchmark in {"passed", "failed"} else None,
            ),
            latency_ms=cls._optional_float(raw.get("latency_ms")),
            latency_class=cls._latency_class(raw.get("latency_class")),
            price_estimate=cls._optional_float(raw.get("price_estimate")),
        )

    @staticmethod
    def _mapping(value: object) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            raise ProviderPortError("Invalid Provider projection object")
        return cast(Mapping[str, Any], value)

    @classmethod
    def _sequence(cls, value: object) -> tuple[Mapping[str, Any], ...]:
        if not isinstance(value, (list, tuple)):
            raise ProviderPortError("Invalid Provider projection list")
        return tuple(cls._mapping(item) for item in value)

    @staticmethod
    def _values(value: object) -> tuple[object, ...]:
        if not isinstance(value, (list, tuple)):
            raise ProviderPortError("Invalid Provider projection values")
        return tuple(value)

    @staticmethod
    def _optional_string(value: object) -> str | None:
        return value if isinstance(value, str) else None

    @staticmethod
    def _optional_float(value: object) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(value)

    @staticmethod
    def _validation_status(value: object) -> ProviderValidationStatus:
        return cast(
            ProviderValidationStatus,
            value if value in {"never", "passed", "failed"} else "never",
        )

    @staticmethod
    def _validation_mode(value: object) -> ValidationMode:
        return cast(
            ValidationMode,
            value
            if value in {"none", "full", "cached", "heartbeat", "benchmark"}
            else "none",
        )

    @staticmethod
    def _latency_class(value: object) -> Optional[LatencyClass]:
        return cast(
            Optional[LatencyClass],
            value if value in {"fast", "normal", "slow"} else None,
        )


__all__ = ("ProviderModelsAdapter",)
