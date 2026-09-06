"""Authorized Provider connection and model-resource use-cases."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import TypeVar
from uuid import uuid4

from app.features.accounts import AccountPrincipal, is_manager

from .errors import (
    ProviderConnectionNotFound,
    ProviderModelNotFound,
    ProviderProductNotFound,
    ProvidersConflict,
    ProvidersForbidden,
    ProvidersUnavailable,
    ProvidersValidationError,
)
from .jobs import LocalProviderJobManager
from .models import (
    AddProviderModelCommand,
    BenchmarkProviderModelsCommand,
    ChangeProviderConnectionLifecycleCommand,
    CleanupObsoleteProviderModelsCommand,
    CompleteProviderOAuthLoginCommand,
    CreateProviderConnectionCommand,
    DefaultLocalProviderConnectionResult,
    DeleteProviderConnectionCommand,
    DeleteProviderModelCommand,
    EnsureDefaultLocalProviderConnectionCommand,
    GetProviderModelMatrixQuery,
    InspectLocalProviderQuery,
    InstallLocalProviderCommand,
    ListObsoleteProviderModelsQuery,
    ListProviderConnectionsQuery,
    ListProviderProductsQuery,
    LocalModelCounts,
    LocalProviderModelResult,
    LocalProviderStatusResult,
    ProbeProviderModelCapabilitiesCommand,
    ProviderBenchmarkResult,
    ProviderBenchmarkRunResult,
    ProviderBrandResult,
    ProviderCapabilityProbeResult,
    ProviderConnectionDeletedResult,
    ProviderConnectionResult,
    ProviderConnectionVerificationResult,
    ProviderMatrixCellResult,
    ProviderMatrixConnectionResult,
    ProviderMatrixModelResult,
    ProviderMatrixSnapshotResult,
    ProviderModelCounts,
    ProviderModelDeletedResult,
    ProviderModelInput,
    ProviderModelMatrixResult,
    ProviderModelRefreshResult,
    ProviderModelReplacement,
    ProviderModelResult,
    ProviderModelsCleanupResult,
    ProviderOAuthLoginStartResult,
    ProviderOAuthLoginStatusResult,
    ProviderObsoleteModelResult,
    ProviderProductResult,
    ProviderValidationItemResult,
    ProviderValidationRunResult,
    ProviderVerificationResult,
    PullLocalProviderModelsCommand,
    RefreshProviderModelsCommand,
    RemoveLocalProviderConnectionCommand,
    ReplaceProviderModelsCommand,
    StartLocalProviderCommand,
    StartProviderOAuthLoginCommand,
    UpdateProviderConnectionCommand,
    UpdateProviderModelCommand,
    ValidateAllProviderModelsCommand,
    VerifyProviderConnectionCommand,
)
from .port_models import (
    CapabilityEvidence,
    StoredBenchmarkCombination,
    StoredLocalModelCounts,
    StoredLocalProviderBinding,
    StoredLocalProviderCandidate,
    StoredLocalProviderModelStatus,
    StoredLocalProviderStatus,
    StoredModelRefresh,
    StoredModelVerification,
    StoredProviderConnection,
    StoredProviderModel,
    StoredProviderProduct,
    StoredProviderProjection,
    StoredVerification,
)
from .ports import (
    BackgroundTaskScheduler,
    CancellationCheck,
    ProviderCatalogPort,
    ProviderConnectionPort,
    ProviderLocalStatePort,
    ProviderLocalStatusCachePort,
    ProviderLocalTechnologyPort,
    ProviderOAuthPort,
    ProviderPortError,
    ProviderReferencePort,
    ProviderTechnologyPort,
)

_T = TypeVar("_T")

LOCAL_STATUS_FRESHNESS = timedelta(minutes=10)
LOCAL_STATUS_REFRESH_COOLDOWN = timedelta(minutes=5)

diagnostic_logger = logging.getLogger("elfienest.diagnostics.provider_management")


def _log_provider_event(
    operation: str,
    phase: str,
    status: str,
    *,
    connection_id: str | None = None,
    catalog_id: str | None = None,
    model_count: int | None = None,
    result_count: int | None = None,
    duration_ms: float | None = None,
    force_full: bool | None = None,
    reason: str | None = None,
    error: BaseException | None = None,
) -> None:
    fields: dict[str, object] = {
        "diagnostic_event": "provider_management",
        "component": "provider_management",
        "operation": operation,
        "phase": phase,
        "status": status,
    }
    if connection_id is not None:
        fields["connection_id"] = connection_id
    if catalog_id is not None:
        fields["catalog_id"] = catalog_id
    if model_count is not None:
        fields["model_count"] = model_count
    if result_count is not None:
        fields["result_count"] = result_count
    if duration_ms is not None:
        fields["duration_ms"] = round(duration_ms, 1)
    if force_full is not None:
        fields["force_full"] = force_full
    if reason:
        fields["reason"] = reason[:512]
    if error is not None:
        fields["error_type"] = type(error).__name__
    diagnostic_logger.log(
        logging.WARNING if error is not None else logging.INFO,
        "Provider management operation",
        extra=fields,
    )


def _elapsed_ms(started_at: float) -> float:
    return (time.monotonic() - started_at) * 1000


class ProvidersService:
    def __init__(
        self,
        *,
        catalog: ProviderCatalogPort,
        connections: ProviderConnectionPort,
        references: ProviderReferencePort,
        technology: ProviderTechnologyPort,
        local_state: ProviderLocalStatePort,
        local_technology: ProviderLocalTechnologyPort,
        local_status_cache: ProviderLocalStatusCachePort | None = None,
        oauth: ProviderOAuthPort | None = None,
    ) -> None:
        self._catalog = catalog
        self._connections = connections
        self._references = references
        self._technology = technology
        self._local_state = local_state
        self._local_technology = local_technology
        self._local_status_cache = local_status_cache
        self._oauth = oauth
        self._local_jobs = LocalProviderJobManager()

    async def start_oauth_login(
        self,
        principal: AccountPrincipal,
        command: StartProviderOAuthLoginCommand,
    ) -> ProviderOAuthLoginStartResult:
        self._require_manager(principal)
        product = self._product(command.catalog_id)
        if product.connection_method != "oauth" or not product.oauth_available:
            raise ProvidersValidationError("Provider does not support OAuth login")
        if self._oauth is None:
            raise ProvidersUnavailable("Provider OAuth login unavailable")
        try:
            started = await self._oauth.start_login(command.catalog_id)
        except ProviderPortError as error:
            raise ProvidersUnavailable("Provider OAuth login unavailable") from error
        return ProviderOAuthLoginStartResult(**vars(started))

    async def complete_oauth_login(
        self,
        principal: AccountPrincipal,
        command: CompleteProviderOAuthLoginCommand,
    ) -> ProviderOAuthLoginStatusResult:
        self._require_manager(principal)
        product = self._product(command.catalog_id)
        if product.connection_method != "oauth" or not product.oauth_available:
            raise ProvidersValidationError("Provider does not support OAuth login")
        if self._oauth is None:
            raise ProvidersUnavailable("Provider OAuth login unavailable")
        try:
            status = await self._oauth.poll_login(command.login_id)
            if status.catalog_id != command.catalog_id:
                raise ProvidersValidationError("OAuth login does not match Provider")
            if status.state == "pending":
                return ProviderOAuthLoginStatusResult(
                    status.catalog_id,
                    status.login_id,
                    status.state,
                    status.account_id,
                    status.expires_at,
                    None,
                )
            existing = next(
                (
                    item
                    for item in self._connections.list_connections()
                    if item.credential_ref == status.credential_ref
                ),
                None,
            )
            connection = existing or self._connections.create_connection(
                StoredProviderConnection(
                    connection_id="",
                    catalog_id=product.catalog_id,
                    alias=(command.alias or "").strip() or product.name,
                    api_base=product.api_base,
                    api_mode=product.api_mode,
                    auth_type=product.auth_type,
                    credential_ref=status.credential_ref,
                    models=(),
                ),
                None,
            )
            if not connection.models:
                await self._refresh(connection)
                connection = self._require_connection(connection.connection_id)
            return ProviderOAuthLoginStatusResult(
                status.catalog_id,
                status.login_id,
                status.state,
                status.account_id,
                status.expires_at,
                self._connection_result(connection),
            )
        except ProvidersValidationError:
            raise
        except ProviderPortError as error:
            raise ProvidersUnavailable("Provider OAuth login unavailable") from error

    def ensure_default_local_connection(
        self,
        command: EnsureDefaultLocalProviderConnectionCommand,
    ) -> DefaultLocalProviderConnectionResult:
        """Ensure the catalog-defined local Provider connection once at startup."""
        _ = command
        try:
            product = self._catalog.get_product("ollama")
            if product is None:
                return DefaultLocalProviderConnectionResult("ollama", False)
            self._connections.ensure_local_connection(product)
            return DefaultLocalProviderConnectionResult(product.catalog_id, True)
        except ProviderPortError as error:
            raise ProvidersUnavailable(
                "Default local Provider connection unavailable"
            ) from error

    def inspect_local_provider(
        self,
        principal: AccountPrincipal,
        query: InspectLocalProviderQuery,
        refresh_scheduler: BackgroundTaskScheduler | None = None,
    ) -> LocalProviderStatusResult:
        self._require_manager(principal)
        if not query.refresh and self._local_status_cache is not None:
            try:
                cached = self._local_status_cache.load()
            except Exception as error:
                raise ProvidersUnavailable(
                    "Local Provider status cache unavailable"
                ) from error
            if cached is not None:
                if refresh_scheduler is not None and not self._is_local_status_fresh(
                    cached
                ):
                    self._schedule_local_status_refresh(refresh_scheduler)
                return replace(
                    self._local_status_result(cached),
                    task=self._local_jobs.current(),
                )
            if refresh_scheduler is not None:
                self._schedule_local_status_refresh(refresh_scheduler)
            return self._unknown_local_provider_status()
        return self.refresh_local_provider_status()

    @staticmethod
    def _is_local_status_fresh(
        status: StoredLocalProviderStatus,
        *,
        now: datetime | None = None,
    ) -> bool:
        try:
            checked_at = datetime.fromisoformat(
                status.checked_at.replace("Z", "+00:00")
            )
        except ValueError:
            return False
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=timezone.utc)
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return current - checked_at.astimezone(timezone.utc) <= LOCAL_STATUS_FRESHNESS

    def _schedule_local_status_refresh(
        self,
        scheduler: BackgroundTaskScheduler,
    ) -> None:
        cache = self._local_status_cache
        if cache is None:
            return
        owner_id = f"provider-status-request-{uuid4().hex}"
        try:
            claimed = cache.try_acquire_refresh_lease(
                owner_id,
                lease_seconds=int(LOCAL_STATUS_REFRESH_COOLDOWN.total_seconds()),
            )
        except Exception:
            return
        if not claimed:
            return
        try:
            scheduler.add_task(
                lambda: self._run_scheduled_local_status_refresh(owner_id)
            )
        except Exception:
            try:
                cache.release_refresh_lease(owner_id)
            except Exception:
                pass

    def _run_scheduled_local_status_refresh(self, owner_id: str) -> None:
        cache = self._local_status_cache
        if cache is None:
            return
        try:
            self.refresh_local_provider_validation()
        except Exception:
            # Keep the lease until its five-minute expiry after a failed
            # attempt so repeated page loads do not hammer the local service.
            return
        try:
            cache.release_refresh_lease(owner_id)
        except Exception:
            pass

    def refresh_local_provider_status(self) -> LocalProviderStatusResult:
        """Probe Ollama and persist the resulting status snapshot."""
        return self._persist_local_provider_status(self._inspect_local_provider_live())

    def _persist_local_provider_status(
        self,
        result: LocalProviderStatusResult,
    ) -> LocalProviderStatusResult:
        if self._local_status_cache is not None:
            checked_at = result.checked_at or datetime.now(timezone.utc).isoformat()
            result = replace(result, checked_at=checked_at)
            try:
                self._local_status_cache.save(self._stored_local_status(result))
            except Exception as error:
                raise ProvidersUnavailable(
                    "Local Provider status cache unavailable"
                ) from error
        return result

    def _inspect_local_provider_live(self) -> LocalProviderStatusResult:
        try:
            recorded = self._local_state.load_local_binding()
            binding = recorded or self._local_technology.default_binding()
            probe = self._local_technology.probe(binding)
            if recorded is None and probe.state == "deleted":
                probe = replace(probe, state="absent")
            if recorded is None and probe.state == "healthy":
                # A healthy Ollama discovered before the startup bootstrap
                # has created its connection still needs a durable Provider
                # endpoint before installed models can be registered.
                binding = self._local_state.save_local_binding(
                    replace(binding, version=probe.version or binding.version)
                )
            installed = self._installed_local_models(probe.state, binding)
            configured_candidates = self._local_technology.candidate_models()
            # The recommendation catalog is not the local Provider's model
            # inventory.  Keep its bounded recommended order, then append
            # models actually installed or already referenced by the local
            # connection so an Ollama upgrade/custom pull is never invisible.
            candidate_by_id = {item.model_id: item for item in configured_candidates}
            referenced = self._local_state.list_local_model_ids()
            if probe.state == "healthy":
                # The Ollama inventory is authoritative for local endpoints.
                # Persist newly observed installed models so a custom pull is
                # not merely displayed: it becomes a resolvable endpoint for
                # Food and validation as well. This is additive and never
                # removes an existing Food reference.
                for model_id in installed:
                    if model_id not in referenced:
                        self._local_state.save_local_model(model_id)
                referenced = self._local_state.list_local_model_ids()
            extra_ids = sorted(
                (set(installed) | set(referenced)) - set(candidate_by_id)
            )
            candidates = configured_candidates + tuple(
                StoredLocalProviderCandidate(
                    model_id=model_id,
                    display_name=model_id,
                    recommended=False,
                )
                for model_id in extra_ids
            )
            memory_gb = self._local_technology.available_memory_gb()
        except ProviderPortError as error:
            raise ProvidersUnavailable("Local Provider status unavailable") from error
        task = self._local_jobs.current()
        state = probe.state
        if task is not None and task.key == "install":
            if task.state == "running":
                state = "installing"
            elif task.state == "failed":
                state = "failed"
        models = tuple(
            self._local_model_result(
                item.model_id,
                item.display_name,
                item.model_id in installed,
                item.recommended,
                state=state,
            )
            for item in candidates
        )
        return LocalProviderStatusResult(
            state=state,
            endpoint=probe.endpoint or None,
            version=probe.version,
            memory_gb=memory_gb,
            recommended_model=next(
                (item.model_id for item in candidates if item.recommended),
                None,
            ),
            installed_model_count=sum(item.installed for item in models),
            models=models,
            task=task,
            model_counts=LocalModelCounts(
                installed=sum(item.installed for item in models),
                available=sum(
                    item.availability_status == "available" for item in models
                ),
                degraded=sum(item.availability_status == "degraded" for item in models),
                pending=sum(
                    item.installed and item.availability_status == "unknown"
                    for item in models
                ),
                unavailable=sum(
                    item.installed and item.availability_status == "unavailable"
                    for item in models
                ),
            ),
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def _unknown_local_provider_status(self) -> LocalProviderStatusResult:
        return LocalProviderStatusResult(
            state="unknown",
            endpoint=None,
            version=None,
            memory_gb=0,
            recommended_model=None,
            installed_model_count=0,
            models=(),
            task=self._local_jobs.current(),
            checked_at=None,
        )

    @staticmethod
    def _local_status_result(
        status: StoredLocalProviderStatus,
    ) -> LocalProviderStatusResult:
        return LocalProviderStatusResult(
            state=status.state,
            endpoint=status.endpoint,
            version=status.version,
            memory_gb=status.memory_gb,
            recommended_model=status.recommended_model,
            installed_model_count=status.installed_model_count,
            models=tuple(
                LocalProviderModelResult(
                    model_id=item.model_id,
                    display_name=item.display_name,
                    installed=item.installed,
                    recommended=item.recommended,
                    availability_status=item.availability_status,
                    available=item.available,
                )
                for item in status.models
            ),
            task=None,
            model_counts=LocalModelCounts(
                installed=status.model_counts.installed,
                available=status.model_counts.available,
                degraded=status.model_counts.degraded,
                pending=status.model_counts.pending,
                unavailable=status.model_counts.unavailable,
            ),
            checked_at=status.checked_at,
        )

    @staticmethod
    def _stored_local_status(
        result: LocalProviderStatusResult,
    ) -> StoredLocalProviderStatus:
        checked_at = result.checked_at
        if checked_at is None:
            raise ProvidersUnavailable("Local Provider status is missing its timestamp")
        return StoredLocalProviderStatus(
            state=result.state,
            endpoint=result.endpoint,
            version=result.version,
            memory_gb=result.memory_gb,
            recommended_model=result.recommended_model,
            installed_model_count=result.installed_model_count,
            models=tuple(
                StoredLocalProviderModelStatus(
                    model_id=item.model_id,
                    display_name=item.display_name,
                    installed=item.installed,
                    recommended=item.recommended,
                    availability_status=item.availability_status,
                    available=item.available,
                )
                for item in result.models
            ),
            model_counts=StoredLocalModelCounts(
                installed=result.model_counts.installed,
                available=result.model_counts.available,
                degraded=result.model_counts.degraded,
                pending=result.model_counts.pending,
                unavailable=result.model_counts.unavailable,
            ),
            checked_at=checked_at,
        )

    def _local_model_result(
        self,
        model_id: str,
        display_name: str,
        installed: bool,
        recommended: bool,
        *,
        state: str,
    ) -> LocalProviderModelResult:
        if not installed:
            return LocalProviderModelResult(
                model_id=model_id,
                display_name=display_name,
                installed=False,
                recommended=recommended,
            )
        try:
            reference = self._local_state.local_model_reference(model_id)
            verification = (
                None
                if reference is None
                else self._technology.summarize_model(
                    reference.split("/", 1)[0],
                    model_id,
                )
            )
        except (AttributeError, ProviderPortError, ValueError):
            verification = None
        availability_status = (
            "unknown" if verification is None else verification.availability_status
        )
        return LocalProviderModelResult(
            model_id=model_id,
            display_name=display_name,
            installed=True,
            recommended=recommended,
            availability_status=(
                "unavailable" if state != "healthy" else availability_status
            ),
            available=state == "healthy"
            and availability_status in {"available", "degraded"},
        )

    def install_local_provider(
        self,
        principal: AccountPrincipal,
        command: InstallLocalProviderCommand,
        scheduler: BackgroundTaskScheduler,
    ) -> LocalProviderStatusResult:
        self._require_manager(principal)
        if not command.confirmed:
            raise ProvidersValidationError("Ollama installation requires confirmation")
        current = self._local_jobs.current()
        if current is not None and current.state == "running":
            raise ProvidersConflict("当前 Ollama 已有进行中的任务")
        try:
            recorded = self._local_state.load_local_binding()
            binding = recorded or self._local_technology.default_binding()
            probe = self._local_technology.probe(binding)
            if probe.state in {"absent", "deleted"}:
                self._local_jobs.enqueue(
                    "install",
                    scheduler,
                    self._install_local_provider,
                )
            elif probe.state in {"healthy", "stopped"}:
                self._connect_or_start_local_provider(binding, probe.state)
                self._local_jobs.clear_terminal()
            else:
                raise ProvidersConflict("已记录的 Ollama 安装需要修复")
        except ProvidersConflict:
            raise
        except ProviderPortError as error:
            raise ProvidersUnavailable(
                "Local Provider installation unavailable"
            ) from error
        except RuntimeError as error:
            raise ProvidersConflict(str(error)) from error
        return self.inspect_local_provider(
            principal,
            InspectLocalProviderQuery(refresh=True),
        )

    def start_local_provider(
        self,
        principal: AccountPrincipal,
        command: StartLocalProviderCommand,
    ) -> LocalProviderStatusResult:
        _ = command
        self._require_manager(principal)
        current = self._local_jobs.current()
        if current is not None and current.state == "running":
            raise ProvidersConflict("当前 Ollama 已有进行中的任务")
        try:
            binding = (
                self._local_state.load_local_binding()
                or self._local_technology.default_binding()
            )
            probe = self._local_technology.probe(binding)
            self._connect_or_start_local_provider(binding, probe.state)
        except ProviderPortError as error:
            raise ProvidersUnavailable("Local Provider startup unavailable") from error
        self._local_jobs.clear_terminal()
        return self.inspect_local_provider(
            principal,
            InspectLocalProviderQuery(refresh=True),
        )

    def pull_local_models(
        self,
        principal: AccountPrincipal,
        command: PullLocalProviderModelsCommand,
        scheduler: BackgroundTaskScheduler,
    ) -> LocalProviderStatusResult:
        self._require_manager(principal)
        if not command.confirmed:
            raise ProvidersValidationError("Model download requires confirmation")
        try:
            allowed = {
                item.model_id for item in self._local_technology.candidate_models()
            }
        except ProviderPortError as error:
            raise ProvidersUnavailable("Local Provider catalog unavailable") from error
        if not command.model_ids or any(
            model_id not in allowed for model_id in command.model_ids
        ):
            raise ProvidersValidationError("所选模型不在本地候选清单中")
        try:
            binding = (
                self._local_state.load_local_binding()
                or self._local_technology.default_binding()
            )
            if self._local_technology.probe(binding).state != "healthy":
                raise ProvidersConflict("Ollama 未运行，不能下载模型")
            self._local_jobs.enqueue(
                "model_pull",
                scheduler,
                lambda: self._pull_local_models(binding, command.model_ids),
            )
        except ProvidersConflict:
            raise
        except ProviderPortError as error:
            raise ProvidersUnavailable(
                "Local Provider model download unavailable"
            ) from error
        except RuntimeError as error:
            raise ProvidersConflict(str(error)) from error
        return self.inspect_local_provider(
            principal,
            InspectLocalProviderQuery(refresh=True),
        )

    def _install_local_provider(self) -> None:
        binding = self._local_technology.install_official()
        self._local_state.save_local_binding(binding)

    def _connect_or_start_local_provider(
        self,
        binding: StoredLocalProviderBinding,
        state: str,
    ) -> None:
        if state == "healthy":
            probe = self._local_technology.probe(binding)
            self._local_state.save_local_binding(
                replace(binding, version=probe.version or binding.version)
            )
            return
        if state == "stopped":
            self._local_state.save_local_binding(self._local_technology.start(binding))
            return
        if state in {"absent", "deleted"}:
            raise ProvidersValidationError("Ollama 安装不存在，请先安装")
        raise ProvidersConflict("已记录的 Ollama 安装需要修复")

    def _pull_local_models(
        self,
        binding: StoredLocalProviderBinding,
        model_ids: tuple[str, ...],
    ) -> None:
        installed = set(self._local_technology.list_models(binding))
        for model_id in model_ids:
            if model_id not in installed:
                self._local_technology.pull_model(binding, model_id)
        self._local_state.replace_local_models(
            self._local_technology.list_models(binding)
        )

    def _installed_local_models(
        self,
        state: str,
        binding: StoredLocalProviderBinding,
    ) -> tuple[str, ...]:
        if state == "healthy":
            try:
                return self._local_technology.list_models(binding)
            except ProviderPortError:
                pass
        return self._local_state.list_local_model_ids()

    def list_products(
        self,
        principal: AccountPrincipal,
        query: ListProviderProductsQuery,
    ) -> tuple[ProviderProductResult, ...]:
        _ = query
        self._require_manager(principal)
        started_at = time.monotonic()
        _log_provider_event("list_products", "start", "started")
        try:
            products = tuple(
                self._product_result(item) for item in self._catalog.list_products()
            )
            _log_provider_event(
                "list_products",
                "complete",
                "succeeded",
                result_count=len(products),
                duration_ms=_elapsed_ms(started_at),
            )
            return products
        except ProviderPortError as error:
            _log_provider_event(
                "list_products",
                "complete",
                "failed",
                duration_ms=_elapsed_ms(started_at),
                error=error,
            )
            raise ProvidersUnavailable("Provider catalog unavailable") from error

    def list_connections(
        self,
        principal: AccountPrincipal,
        query: ListProviderConnectionsQuery,
    ) -> tuple[ProviderConnectionResult, ...]:
        _ = query
        self._require_manager(principal)
        started_at = time.monotonic()
        _log_provider_event("list_connections", "start", "started")
        try:
            connections = self._connections.list_connections()
            projections = self._technology.project_connections(connections)
            projections_by_id = {
                projection.connection_id: projection for projection in projections
            }
            connection_ids = {item.connection_id for item in connections}
            if (
                len(projections_by_id) != len(projections)
                or set(projections_by_id) != connection_ids
            ):
                raise ProviderPortError("Provider projection inventory mismatch")
            results = tuple(
                self._connection_result(
                    item,
                    projection=projections_by_id[item.connection_id],
                )
                for item in connections
            )
            _log_provider_event(
                "list_connections",
                "complete",
                "succeeded",
                model_count=sum(len(item.models) for item in connections),
                duration_ms=_elapsed_ms(started_at),
            )
            return results
        except ProviderPortError as error:
            _log_provider_event(
                "list_connections",
                "complete",
                "failed",
                duration_ms=_elapsed_ms(started_at),
                error=error,
            )
            raise ProvidersUnavailable("Provider connections unavailable") from error

    async def create_connection(
        self,
        principal: AccountPrincipal,
        command: CreateProviderConnectionCommand,
    ) -> ProviderConnectionResult:
        self._require_manager(principal)
        started_at = time.monotonic()
        _log_provider_event(
            "create_connection",
            "start",
            "started",
            catalog_id=command.catalog_id,
        )
        product = self._product(command.catalog_id)
        if product.connection_method == "local" and command.api_key:
            raise ProvidersValidationError("Local connections do not accept an API key")
        if product.connection_method == "oauth":
            raise ProvidersValidationError(
                "OAuth connections must be created through authorization"
            )
        api_base = product.api_base if command.api_base is None else command.api_base
        if command.catalog_id == "custom_openai" and not api_base:
            raise ProvidersValidationError("Custom connections require an API base URL")
        models = tuple(self._prepare_model(item) for item in command.models)
        try:
            existing = tuple(
                item
                for item in self._connections.list_connections()
                if item.catalog_id == command.catalog_id
            )
            alias = (command.alias or "").strip() or (
                product.name if not existing else f"{product.name} {len(existing) + 1}"
            )
            connection = self._connections.create_connection(
                StoredProviderConnection(
                    connection_id="",
                    catalog_id=command.catalog_id,
                    alias=alias,
                    api_base=api_base,
                    api_mode=command.api_mode or product.api_mode,
                    auth_type=command.auth_type or product.auth_type,
                    credential_ref="",
                    models=models,
                ),
                command.api_key,
            )
            _log_provider_event(
                "create_connection",
                "persist",
                "succeeded",
                connection_id=connection.connection_id,
                catalog_id=connection.catalog_id,
                model_count=len(connection.models),
            )
            if not command.defer_validation:
                await self._probe_reachability(connection)
            refresh = None
            if command.refresh_models:
                refresh = await self._refresh(connection)
                connection = self._require_connection(connection.connection_id)
            verification = (
                await self._technology.verify_connection(connection, force_full=False)
                if command.verify
                else None
            )
            if verification is not None:
                _log_provider_event(
                    "create_connection",
                    "verification",
                    verification.status,
                    connection_id=connection.connection_id,
                    catalog_id=connection.catalog_id,
                    force_full=False,
                    reason=verification.error or verification.reason,
                )
            if not command.verify and not command.defer_validation:
                await self._probe_representative(connection)
            result = self._connection_result(
                connection,
                verification=verification,
                refresh=refresh,
            )
            _log_provider_event(
                "create_connection",
                "complete",
                "succeeded",
                connection_id=connection.connection_id,
                catalog_id=connection.catalog_id,
                model_count=len(connection.models),
                duration_ms=_elapsed_ms(started_at),
            )
            return result
        except ProviderPortError as error:
            _log_provider_event(
                "create_connection",
                "complete",
                "failed",
                catalog_id=command.catalog_id,
                duration_ms=_elapsed_ms(started_at),
                error=error,
            )
            raise ProvidersUnavailable(
                "Provider connection could not be created"
            ) from error
        except Exception as error:
            _log_provider_event(
                "create_connection",
                "complete",
                "failed",
                catalog_id=command.catalog_id,
                duration_ms=_elapsed_ms(started_at),
                error=error,
            )
            raise

    async def update_connection(
        self,
        principal: AccountPrincipal,
        command: UpdateProviderConnectionCommand,
    ) -> ProviderConnectionResult:
        self._require_manager(principal)
        connection = self._require_connection(command.connection_id)
        started_at = time.monotonic()
        _log_provider_event(
            "update_connection",
            "start",
            "started",
            connection_id=connection.connection_id,
            catalog_id=connection.catalog_id,
            model_count=len(connection.models),
        )
        self._product(connection.catalog_id)
        models = connection.models
        if "models" in command.fields:
            models = tuple(self._prepare_model(item) for item in (command.models or ()))
        alias = connection.alias
        if "alias" in command.fields and command.alias is not None:
            alias = command.alias.strip() or connection.alias
        updated = replace(
            connection,
            alias=alias,
            api_base=(
                command.api_base
                if "api_base" in command.fields and command.api_base is not None
                else connection.api_base
            ),
            api_mode=(
                command.api_mode
                if "api_mode" in command.fields and command.api_mode is not None
                else connection.api_mode
            ),
            auth_type=(
                command.auth_type
                if "auth_type" in command.fields and command.auth_type is not None
                else connection.auth_type
            ),
            models=models,
        )
        try:
            updated = self._connections.replace_connection(
                updated,
                command.api_key,
                update_credential="api_key" in command.fields,
            )
            _log_provider_event(
                "update_connection",
                "persist",
                "succeeded",
                connection_id=updated.connection_id,
                catalog_id=updated.catalog_id,
                model_count=len(updated.models),
            )
            if not command.defer_validation and (
                command.verify
                or bool(
                    set(command.fields)
                    & {"api_base", "api_mode", "auth_type", "api_key", "models"}
                )
            ):
                await self._probe_reachability(updated)
            refresh = None
            if command.refresh_models:
                refresh = await self._refresh(updated)
                updated = self._require_connection(updated.connection_id)
            verification = (
                await self._technology.verify_connection(updated, force_full=False)
                if command.verify
                else None
            )
            if verification is not None:
                _log_provider_event(
                    "update_connection",
                    "verification",
                    verification.status,
                    connection_id=updated.connection_id,
                    catalog_id=updated.catalog_id,
                    force_full=False,
                    reason=verification.error or verification.reason,
                )
            if (
                not command.verify
                and not command.defer_validation
                and bool(
                    set(command.fields)
                    & {"api_base", "api_mode", "auth_type", "api_key", "models"}
                )
            ):
                await self._probe_representative(updated)
            result = self._connection_result(
                updated,
                verification=verification,
                refresh=refresh,
            )
            _log_provider_event(
                "update_connection",
                "complete",
                "succeeded",
                connection_id=updated.connection_id,
                catalog_id=updated.catalog_id,
                model_count=len(updated.models),
                duration_ms=_elapsed_ms(started_at),
            )
            return result
        except ProviderPortError as error:
            _log_provider_event(
                "update_connection",
                "complete",
                "failed",
                connection_id=connection.connection_id,
                catalog_id=connection.catalog_id,
                duration_ms=_elapsed_ms(started_at),
                error=error,
            )
            raise ProvidersUnavailable(
                "Provider connection could not be updated"
            ) from error
        except Exception as error:
            _log_provider_event(
                "update_connection",
                "complete",
                "failed",
                connection_id=connection.connection_id,
                catalog_id=connection.catalog_id,
                duration_ms=_elapsed_ms(started_at),
                error=error,
            )
            raise

    def delete_connection(
        self,
        principal: AccountPrincipal,
        command: DeleteProviderConnectionCommand,
    ) -> ProviderConnectionDeletedResult:
        self._require_manager(principal)
        connection = self._require_connection(command.connection_id)
        if connection.catalog_id == "ollama":
            raise ProvidersValidationError(
                "The default Ollama connection cannot be deleted"
            )
        try:
            references = self._references.connections_referenced_by_food(
                connection.connection_id
            )
            if references:
                if not connection.archived:
                    raise ProvidersConflict(
                        "The connection must be archived before deletion"
                    )
                raise ProvidersConflict(
                    "The connection is referenced by food packages: "
                    + ", ".join(references)
                )
            if not self._connections.delete_connection(connection.connection_id):
                raise ProviderConnectionNotFound(connection.connection_id)
        except ProviderPortError as error:
            raise ProvidersUnavailable(
                "Provider connection could not be deleted"
            ) from error
        return ProviderConnectionDeletedResult(connection_id=connection.connection_id)

    def remove_local_connection(
        self,
        principal: AccountPrincipal,
        command: RemoveLocalProviderConnectionCommand,
    ) -> ProviderConnectionDeletedResult:
        """Preserve the local CLI's explicit Ollama removal use-case."""
        self._require_manager(principal)
        connection = self._require_connection(command.connection_id)
        if connection.catalog_id != "ollama":
            raise ProvidersValidationError(
                "Only the default Ollama connection uses local removal"
            )
        try:
            if not self._connections.delete_connection(connection.connection_id):
                raise ProviderConnectionNotFound(connection.connection_id)
        except ProviderPortError as error:
            raise ProvidersUnavailable(
                "Local Provider connection could not be removed"
            ) from error
        return ProviderConnectionDeletedResult(connection_id=connection.connection_id)

    def change_lifecycle(
        self,
        principal: AccountPrincipal,
        command: ChangeProviderConnectionLifecycleCommand,
    ) -> ProviderConnectionResult:
        self._require_manager(principal)
        connection = self._require_connection(command.connection_id)
        if command.action == "enable":
            if connection.archived:
                raise ProvidersConflict("An archived connection must be restored first")
            updated = replace(connection, enabled=True)
        elif command.action == "disable":
            updated = replace(connection, enabled=False)
        elif command.action == "archive":
            updated = replace(connection, enabled=False, archived=True)
        else:
            updated = replace(connection, enabled=False, archived=False)
        try:
            updated = self._connections.replace_connection(
                updated,
                None,
                update_credential=False,
            )
        except ProviderPortError as error:
            raise ProvidersUnavailable(
                "Provider lifecycle could not be changed"
            ) from error
        return self._connection_result(updated)

    async def verify_connection(
        self,
        principal: AccountPrincipal,
        command: VerifyProviderConnectionCommand,
    ) -> ProviderConnectionVerificationResult:
        self._require_manager(principal)
        connection = self._require_connection(command.connection_id)
        started_at = time.monotonic()
        _log_provider_event(
            "verify_connection",
            "start",
            "started",
            connection_id=connection.connection_id,
            catalog_id=connection.catalog_id,
            model_count=len(connection.models),
            force_full=command.force_full,
        )
        try:
            await self._probe_reachability(connection)
            verification = await self._technology.verify_connection(
                connection,
                force_full=command.force_full,
            )
            _log_provider_event(
                "verify_connection",
                "validation",
                verification.status,
                connection_id=connection.connection_id,
                catalog_id=connection.catalog_id,
                model_count=len(connection.models),
                force_full=command.force_full,
                reason=verification.error or verification.reason,
            )
        except ProviderPortError as error:
            _log_provider_event(
                "verify_connection",
                "complete",
                "failed",
                connection_id=connection.connection_id,
                catalog_id=connection.catalog_id,
                duration_ms=_elapsed_ms(started_at),
                force_full=command.force_full,
                error=error,
            )
            raise ProvidersUnavailable("Provider validation unavailable") from error
        except Exception as error:
            _log_provider_event(
                "verify_connection",
                "complete",
                "failed",
                connection_id=connection.connection_id,
                catalog_id=connection.catalog_id,
                duration_ms=_elapsed_ms(started_at),
                force_full=command.force_full,
                error=error,
            )
            raise
        result = ProviderConnectionVerificationResult(
            connection_id=connection.connection_id,
            verification=self._verification_result(verification),
        )
        _log_provider_event(
            "verify_connection",
            "complete",
            verification.status,
            connection_id=connection.connection_id,
            catalog_id=connection.catalog_id,
            model_count=len(connection.models),
            duration_ms=_elapsed_ms(started_at),
            force_full=command.force_full,
            reason=verification.error or verification.reason,
        )
        return result

    async def verify_local_models(
        self,
        principal: AccountPrincipal,
    ) -> LocalProviderStatusResult:
        """Verify only supported, installed Ollama models awaiting evidence."""
        self._require_manager(principal)
        return await self._verify_local_models()

    def refresh_local_provider_validation(self) -> LocalProviderStatusResult:
        """Refresh Ollama status and unknown model evidence from a worker thread."""
        return asyncio.run(self._verify_local_models())

    async def _verify_local_models(self) -> LocalProviderStatusResult:
        current = self._inspect_local_provider_live()
        if current.state != "healthy":
            return self._persist_local_provider_status(current)

        supported_ids = {
            item.model_id for item in self._local_technology.candidate_models()
        }
        references: list[str] = []
        for model in current.models:
            if (
                not model.installed
                or model.model_id not in supported_ids
                or model.availability_status != "unknown"
            ):
                continue
            reference = self._local_state.local_model_reference(model.model_id)
            if reference is not None:
                references.append(reference)

        probe = getattr(self._technology, "probe_model", None)
        if not callable(probe) or not references:
            return self._persist_local_provider_status(current)

        semaphore = asyncio.Semaphore(2)

        async def verify_one(reference: str) -> None:
            async with semaphore:
                await probe(reference)

        unexpected_error: Exception | None = None
        latest = current
        pending = [verify_one(reference) for reference in references]
        for completed in asyncio.as_completed(pending):
            try:
                await completed
            except (ProviderPortError, ValueError, OSError):
                # A normal endpoint failure should be reflected by the model
                # observation and must not prevent other local models from
                # establishing usable evidence.
                pass
            except Exception as error:
                unexpected_error = error
            latest = self.refresh_local_provider_status()
        if unexpected_error is not None:
            raise ProvidersUnavailable(
                "Local Provider validation unavailable"
            ) from unexpected_error
        return latest

    async def refresh_models(
        self,
        principal: AccountPrincipal,
        command: RefreshProviderModelsCommand,
    ) -> ProviderModelRefreshResult:
        self._require_manager(principal)
        connection = self._require_connection(command.connection_id)
        started_at = time.monotonic()
        _log_provider_event(
            "refresh_models",
            "start",
            "started",
            connection_id=connection.connection_id,
            catalog_id=connection.catalog_id,
            model_count=len(connection.models),
        )
        try:
            refresh = await self._refresh(connection)
            result = self._refresh_result(refresh, command.connection_id)
        except ProviderPortError as error:
            _log_provider_event(
                "refresh_models",
                "complete",
                "failed",
                connection_id=connection.connection_id,
                catalog_id=connection.catalog_id,
                model_count=len(connection.models),
                duration_ms=_elapsed_ms(started_at),
                error=error,
            )
            raise
        except Exception as error:
            _log_provider_event(
                "refresh_models",
                "complete",
                "failed",
                connection_id=connection.connection_id,
                catalog_id=connection.catalog_id,
                model_count=len(connection.models),
                duration_ms=_elapsed_ms(started_at),
                error=error,
            )
            raise
        _log_provider_event(
            "refresh_models",
            "complete",
            refresh.status,
            connection_id=connection.connection_id,
            catalog_id=connection.catalog_id,
            model_count=len(refresh.models),
            duration_ms=_elapsed_ms(started_at),
        )
        return result

    async def probe_capabilities(
        self,
        principal: AccountPrincipal,
        command: ProbeProviderModelCapabilitiesCommand,
    ) -> ProviderCapabilityProbeResult:
        self._require_manager(principal)
        connection = self._require_connection(command.connection_id)
        started_at = time.monotonic()
        _log_provider_event(
            "probe_capabilities",
            "start",
            "started",
            connection_id=connection.connection_id,
            catalog_id=connection.catalog_id,
        )
        reference = f"{command.connection_id}/{command.model_id}"
        try:
            results = await self._technology.probe_capabilities(
                reference,
                command.capabilities,
            )
        except ProviderPortError as error:
            _log_provider_event(
                "probe_capabilities",
                "complete",
                "failed",
                connection_id=connection.connection_id,
                catalog_id=connection.catalog_id,
                duration_ms=_elapsed_ms(started_at),
                error=error,
            )
            raise ProvidersUnavailable(
                "Provider capability probe unavailable"
            ) from error
        result = ProviderCapabilityProbeResult(
            reference=reference,
            results=tuple(results),
        )
        _log_provider_event(
            "probe_capabilities",
            "complete",
            "succeeded",
            connection_id=connection.connection_id,
            catalog_id=connection.catalog_id,
            result_count=len(result.results),
            duration_ms=_elapsed_ms(started_at),
        )
        return result

    def list_obsolete_models(
        self,
        principal: AccountPrincipal,
        query: ListObsoleteProviderModelsQuery,
    ) -> tuple[ProviderObsoleteModelResult, ...]:
        self._require_manager(principal)
        connection = self._require_connection(query.connection_id)
        try:
            candidates = self._technology.list_obsolete_models(connection.connection_id)
            projected: list[ProviderObsoleteModelResult] = []
            for candidate in candidates:
                references = self._references.models_referenced_by_food(
                    connection.connection_id,
                    candidate.model.model_id,
                )
                eligible = candidate.eligible and not references
                reason = candidate.reason
                if references:
                    reason = "仍被 Food 使用：" + ", ".join(references)
                projected.append(
                    ProviderObsoleteModelResult(
                        model=self._model_result(
                            connection.connection_id, candidate.model
                        ),
                        eligible=eligible,
                        reason=reason,
                        last_production_at=candidate.last_production_at,
                    )
                )
            return tuple(projected)
        except ProviderPortError as error:
            raise ProvidersUnavailable(
                "Obsolete Provider models unavailable"
            ) from error

    def cleanup_obsolete_models(
        self,
        principal: AccountPrincipal,
        command: CleanupObsoleteProviderModelsCommand,
    ) -> ProviderConnectionResult | ProviderModelsCleanupResult:
        self._require_manager(principal)
        connection = self._require_connection(command.connection_id)
        if not command.model_ids:
            # Keep the original explicit Owner action for callers that ask to
            # clean all currently eligible source-managed models.  The newer
            # model-management route below requires an explicit selection.
            referenced: set[str] = set()
            try:
                for model in connection.models:
                    if self._references.models_referenced_by_food(
                        connection.connection_id,
                        model.model_id,
                    ):
                        referenced.add(model.model_id)
                candidates = self._technology.obsolete_model_ids(
                    connection,
                    referenced_model_ids=tuple(sorted(referenced)),
                )
            except ProviderPortError as error:
                raise ProvidersUnavailable(
                    "Provider cleanup eligibility unavailable"
                ) from error
            if not candidates:
                return ProviderModelsCleanupResult(connection.connection_id, ())
            current = self._require_connection(connection.connection_id)
            safe: list[str] = []
            for model_id in candidates:
                try:
                    still_referenced = self._references.models_referenced_by_food(
                        current.connection_id,
                        model_id,
                    )
                except ProviderPortError as error:
                    raise ProvidersUnavailable(
                        "Provider references unavailable"
                    ) from error
                if not still_referenced:
                    safe.append(model_id)
            if safe:
                self._replace_models(
                    current,
                    tuple(item for item in current.models if item.model_id not in safe),
                )
            return ProviderModelsCleanupResult(current.connection_id, tuple(safe))
        model_ids = tuple(
            dict.fromkeys(model_id.strip() for model_id in command.model_ids)
        )
        if not model_ids or any(not model_id for model_id in model_ids):
            raise ProvidersValidationError("待清理模型不能为空")
        try:
            obsolete_by_id = {
                item.model.model_id: item
                for item in self._technology.list_obsolete_models(
                    connection.connection_id
                )
            }
            for model_id in model_ids:
                candidate = obsolete_by_id.get(model_id)
                if candidate is None:
                    raise ProviderModelNotFound(model_id)
                references = self._references.models_referenced_by_food(
                    connection.connection_id,
                    model_id,
                )
                if references:
                    raise ProvidersConflict(
                        "The model is referenced by food packages: "
                        + ", ".join(references)
                    )
                if not candidate.eligible:
                    raise ProvidersConflict(candidate.reason)
            for model_id in model_ids:
                self._technology.delete_obsolete_model(
                    connection.connection_id,
                    model_id,
                )
        except (ProviderModelNotFound, ProvidersConflict):
            raise
        except ProviderPortError as error:
            raise ProvidersUnavailable(
                "Obsolete Provider model cleanup unavailable"
            ) from error
        return self._connection_result(
            self._require_connection(connection.connection_id)
        )

    def add_model(
        self,
        principal: AccountPrincipal,
        command: AddProviderModelCommand,
    ) -> ProviderModelResult:
        self._require_manager(principal)
        connection = self._require_connection(command.connection_id)
        if any(item.model_id == command.model.model_id for item in connection.models):
            raise ProvidersConflict("The connection already contains this model ID")
        model = self._prepare_model(command.model)
        updated_connection = self._replace_models(
            connection, (*connection.models, model)
        )
        persisted_model = next(
            item
            for item in updated_connection.models
            if item.model_id == model.model_id
        )
        return self._model_result(updated_connection.connection_id, persisted_model)

    def replace_models(
        self,
        principal: AccountPrincipal,
        command: ReplaceProviderModelsCommand,
    ) -> ProviderConnectionResult:
        self._require_manager(principal)
        connection = self._require_connection(command.connection_id)
        current_by_id = {item.model_id: item for item in connection.models}
        original_ids = [item.original_model_id for item in command.models]
        if len(set(original_ids)) != len(original_ids):
            raise ProvidersValidationError("Original model IDs cannot repeat")
        if set(original_ids) != set(current_by_id):
            raise ProvidersValidationError(
                "The complete existing model list must be submitted"
            )
        target_ids = [item.model_id for item in command.models]
        if len(set(target_ids)) != len(target_ids):
            raise ProvidersValidationError("Model IDs cannot repeat")
        updated: list[StoredProviderModel] = []
        for item in command.models:
            current = current_by_id[item.original_model_id]
            if item.model_id != item.original_model_id and current.source != "manual":
                raise ProvidersValidationError(
                    "Discovered or catalog model IDs cannot be changed"
                )
            updated.append(
                replace(
                    current,
                    model_id=item.model_id,
                    display_name=_replacement_value(
                        item, "display_name", item.display_name, current.display_name
                    ),
                    canonical_model_id=_replacement_value(
                        item,
                        "canonical_model_id",
                        item.canonical_model_id,
                        current.canonical_model_id,
                    ),
                    context_window_tokens=_replacement_value(
                        item,
                        "context_window_tokens",
                        item.context_window_tokens,
                        current.context_window_tokens,
                    ),
                    max_output_tokens=_replacement_value(
                        item,
                        "max_output_tokens",
                        item.max_output_tokens,
                        current.max_output_tokens,
                    ),
                    supports_tools=_replacement_value(
                        item,
                        "supports_tools",
                        item.supports_tools,
                        current.supports_tools,
                    ),
                    supports_vision=_replacement_value(
                        item,
                        "supports_vision",
                        item.supports_vision,
                        current.supports_vision,
                    ),
                    supports_reasoning=_replacement_value(
                        item,
                        "supports_reasoning",
                        item.supports_reasoning,
                        current.supports_reasoning,
                    ),
                    supports_structured_output=_replacement_value(
                        item,
                        "supports_structured_output",
                        item.supports_structured_output,
                        current.supports_structured_output,
                    ),
                    request_profile_id=_replacement_value(
                        item,
                        "request_profile_id",
                        item.request_profile_id,
                        current.request_profile_id,
                    ),
                    request_profile_version=_replacement_value(
                        item,
                        "request_profile_version",
                        item.request_profile_version,
                        current.request_profile_version,
                    ),
                    capability_evidence=_user_capability_evidence(
                        current=current,
                        values={
                            "tools": _replacement_value(
                                item,
                                "supports_tools",
                                item.supports_tools,
                                current.supports_tools,
                            ),
                            "vision": _replacement_value(
                                item,
                                "supports_vision",
                                item.supports_vision,
                                current.supports_vision,
                            ),
                            "reasoning": _replacement_value(
                                item,
                                "supports_reasoning",
                                item.supports_reasoning,
                                current.supports_reasoning,
                            ),
                            "structured_output": _replacement_value(
                                item,
                                "supports_structured_output",
                                item.supports_structured_output,
                                current.supports_structured_output,
                            ),
                        },
                        fields=item.fields,
                    ),
                    hidden=item.hidden,
                )
            )
        return self._connection_result(self._replace_models(connection, tuple(updated)))

    def update_model(
        self,
        principal: AccountPrincipal,
        command: UpdateProviderModelCommand,
    ) -> ProviderModelResult:
        self._require_manager(principal)
        connection = self._require_connection(command.connection_id)
        current = next(
            (item for item in connection.models if item.model_id == command.model_id),
            None,
        )
        if current is None:
            raise ProviderModelNotFound(command.model_id)
        updated = replace(
            current,
            display_name=(
                command.display_name
                if "display_name" in command.fields and command.display_name
                else current.display_name
            ),
            canonical_model_id=(
                command.canonical_model_id
                if "canonical_model_id" in command.fields
                else current.canonical_model_id
            ),
            context_window_tokens=(
                command.context_window_tokens
                if "context_window_tokens" in command.fields
                else current.context_window_tokens
            ),
            max_output_tokens=(
                command.max_output_tokens
                if "max_output_tokens" in command.fields
                else current.max_output_tokens
            ),
            supports_tools=(
                command.supports_tools
                if "supports_tools" in command.fields
                else current.supports_tools
            ),
            supports_vision=(
                command.supports_vision
                if "supports_vision" in command.fields
                else current.supports_vision
            ),
            supports_reasoning=(
                command.supports_reasoning
                if "supports_reasoning" in command.fields
                else current.supports_reasoning
            ),
            supports_structured_output=(
                command.supports_structured_output
                if "supports_structured_output" in command.fields
                else current.supports_structured_output
            ),
            request_profile_id=(
                command.request_profile_id
                if "request_profile_id" in command.fields
                else current.request_profile_id
            ),
            request_profile_version=(
                command.request_profile_version
                if "request_profile_version" in command.fields
                else current.request_profile_version
            ),
            capability_evidence=_updated_capability_evidence(
                current,
                command.fields,
                values={
                    "tools": command.supports_tools,
                    "vision": command.supports_vision,
                    "reasoning": command.supports_reasoning,
                    "structured_output": command.supports_structured_output,
                },
            ),
            hidden=(
                command.hidden
                if "hidden" in command.fields and command.hidden is not None
                else current.hidden
            ),
            retired=(
                command.retired
                if "retired" in command.fields and command.retired is not None
                else current.retired
            ),
        )
        persisted_connection = self._replace_models(
            connection,
            tuple(
                updated if item.model_id == command.model_id else item
                for item in connection.models
            ),
        )
        persisted_model = next(
            item
            for item in persisted_connection.models
            if item.model_id == command.model_id
        )
        return self._model_result(persisted_connection.connection_id, persisted_model)

    def delete_model(
        self,
        principal: AccountPrincipal,
        command: DeleteProviderModelCommand,
    ) -> ProviderModelDeletedResult:
        self._require_manager(principal)
        connection = self._require_connection(command.connection_id)
        current = next(
            (item for item in connection.models if item.model_id == command.model_id),
            None,
        )
        if current is None:
            raise ProviderModelNotFound(command.model_id)
        if current.source != "manual":
            raise ProvidersConflict("Discovered or catalog models must be hidden")
        try:
            references = self._references.models_referenced_by_food(
                connection.connection_id,
                current.model_id,
            )
        except ProviderPortError as error:
            raise ProvidersUnavailable("Provider references unavailable") from error
        if references:
            raise ProvidersConflict(
                "The model is referenced by food packages: " + ", ".join(references)
            )
        self._replace_models(
            connection,
            tuple(
                item for item in connection.models if item.model_id != current.model_id
            ),
        )
        return ProviderModelDeletedResult(
            connection_id=connection.connection_id,
            model_id=current.model_id,
        )

    def get_model_matrix(
        self,
        principal: AccountPrincipal,
        query: GetProviderModelMatrixQuery,
    ) -> ProviderModelMatrixResult:
        self._require_manager(principal)
        if query.as_of and query.run_id:
            raise ProvidersValidationError("as_of and run_id cannot be used together")
        try:
            matrix = self._technology.model_matrix(
                self._connections.list_connections(),
                as_of=query.as_of,
                run_id=query.run_id,
            )
        except KeyError as error:
            raise ProviderConnectionNotFound("Report snapshot not found") from error
        except ValueError as error:
            raise ProvidersValidationError("Invalid report snapshot") from error
        except ProviderPortError as error:
            raise ProvidersUnavailable("Provider model matrix unavailable") from error
        return ProviderModelMatrixResult(
            snapshot=ProviderMatrixSnapshotResult(**vars(matrix.snapshot)),
            connections=tuple(
                ProviderMatrixConnectionResult(
                    connection_id=item.connection_id,
                    name=item.name,
                    verification=self._verification_result(item.verification),
                )
                for item in matrix.connections
            ),
            models=tuple(
                ProviderMatrixModelResult(
                    model_key=item.model_key,
                    display_name=item.display_name,
                    capabilities=item.capabilities,
                    connections=tuple(
                        ProviderMatrixCellResult(**vars(cell))
                        for cell in item.connections
                    ),
                )
                for item in matrix.models
            ),
        )

    async def benchmark_models(
        self,
        principal: AccountPrincipal,
        command: BenchmarkProviderModelsCommand,
    ) -> ProviderBenchmarkRunResult:
        self._require_manager(principal)
        combinations = tuple(
            StoredBenchmarkCombination(item.connection_id, item.model_id)
            for item in command.combinations
        )
        try:
            run = await self._technology.benchmark_models(
                self._connections.list_connections(),
                combinations,
            )
        except ValueError as error:
            raise ProvidersValidationError(str(error)) from error
        except ProviderPortError as error:
            raise ProvidersUnavailable("Provider benchmark unavailable") from error
        return ProviderBenchmarkRunResult(
            run_id=run.run_id,
            status=run.status,
            results=tuple(
                ProviderBenchmarkResult(**vars(item)) for item in run.results
            ),
        )

    async def validate_all(
        self,
        principal: AccountPrincipal,
        command: ValidateAllProviderModelsCommand,
        cancelled: CancellationCheck,
    ) -> ProviderValidationRunResult:
        _ = command
        self._require_manager(principal)
        started_at = time.monotonic()
        _log_provider_event("validate_all", "start", "started")
        try:
            run = await self._technology.validate_all(
                tuple(
                    item
                    for item in self._connections.list_connections()
                    if item.enabled and not item.archived
                ),
                cancelled,
            )
        except ProviderPortError as error:
            _log_provider_event(
                "validate_all",
                "complete",
                "failed",
                duration_ms=_elapsed_ms(started_at),
                error=error,
            )
            raise ProvidersUnavailable("Provider validation unavailable") from error
        result = ProviderValidationRunResult(
            run_id=run.run_id,
            status=run.status,
            results=tuple(
                ProviderValidationItemResult(**vars(item)) for item in run.results
            ),
        )
        _log_provider_event(
            "validate_all",
            "complete",
            result.status,
            result_count=len(result.results),
            duration_ms=_elapsed_ms(started_at),
        )
        return result

    def _product(self, catalog_id: str) -> StoredProviderProduct:
        try:
            product = self._catalog.get_product(catalog_id)
        except ProviderPortError as error:
            raise ProvidersUnavailable("Provider catalog unavailable") from error
        if product is None:
            raise ProviderProductNotFound(catalog_id)
        return product

    def _require_connection(self, connection_id: str) -> StoredProviderConnection:
        try:
            connection = self._connections.get_connection(connection_id)
        except ProviderPortError as error:
            raise ProvidersUnavailable("Provider connections unavailable") from error
        if connection is None:
            raise ProviderConnectionNotFound(connection_id)
        return connection

    def _prepare_model(self, model: ProviderModelInput) -> StoredProviderModel:
        try:
            return self._technology.prepare_manual_model(model)
        except ValueError as error:
            raise ProvidersValidationError(str(error)) from error
        except ProviderPortError as error:
            raise ProvidersUnavailable("Provider model metadata unavailable") from error

    def _replace_models(
        self,
        connection: StoredProviderConnection,
        models: tuple[StoredProviderModel, ...],
    ) -> StoredProviderConnection:
        started_at = time.monotonic()
        _log_provider_event(
            "persist_models",
            "start",
            "started",
            connection_id=connection.connection_id,
            catalog_id=connection.catalog_id,
            model_count=len(models),
        )
        try:
            updated = self._connections.replace_connection(
                replace(connection, models=models),
                None,
                update_credential=False,
            )
            _log_provider_event(
                "persist_models",
                "complete",
                "succeeded",
                connection_id=updated.connection_id,
                catalog_id=updated.catalog_id,
                model_count=len(updated.models),
                duration_ms=_elapsed_ms(started_at),
            )
            return updated
        except ProviderPortError as error:
            _log_provider_event(
                "persist_models",
                "complete",
                "failed",
                connection_id=connection.connection_id,
                catalog_id=connection.catalog_id,
                model_count=len(models),
                duration_ms=_elapsed_ms(started_at),
                error=error,
            )
            raise ProvidersUnavailable(
                "Provider models could not be updated"
            ) from error

    async def _refresh(
        self,
        connection: StoredProviderConnection,
    ) -> StoredModelRefresh:
        started_at = time.monotonic()
        _log_provider_event(
            "refresh_models",
            "discovery",
            "started",
            connection_id=connection.connection_id,
            catalog_id=connection.catalog_id,
            model_count=len(connection.models),
        )
        try:
            refresh = await self._technology.refresh_models(connection)
            persisted_models = refresh.persisted_models
            if persisted_models is None:
                persisted_models = refresh.models
            # A failed or malformed discovery response must never erase a
            # previously usable inventory. An intentional empty inventory is
            # represented explicitly by authoritative_empty plus a persisted
            # snapshot from the technology adapter.
            if persisted_models or refresh.status == "authoritative_empty":
                self._replace_models(connection, persisted_models)
            else:
                _log_provider_event(
                    "refresh_models",
                    "preserve_inventory",
                    "succeeded",
                    connection_id=connection.connection_id,
                    catalog_id=connection.catalog_id,
                    model_count=len(connection.models),
                )
            _log_provider_event(
                "refresh_models",
                "discovery",
                refresh.status,
                connection_id=connection.connection_id,
                catalog_id=connection.catalog_id,
                model_count=len(persisted_models),
                duration_ms=_elapsed_ms(started_at),
                reason=refresh.message,
            )
            return refresh
        except ProviderPortError as error:
            _log_provider_event(
                "refresh_models",
                "discovery",
                "failed",
                connection_id=connection.connection_id,
                catalog_id=connection.catalog_id,
                model_count=len(connection.models),
                duration_ms=_elapsed_ms(started_at),
                error=error,
            )
            raise ProvidersUnavailable("Provider model refresh unavailable") from error
        except Exception as error:
            _log_provider_event(
                "refresh_models",
                "discovery",
                "failed",
                connection_id=connection.connection_id,
                catalog_id=connection.catalog_id,
                model_count=len(connection.models),
                duration_ms=_elapsed_ms(started_at),
                error=error,
            )
            raise

    async def _probe_representative(
        self,
        connection: StoredProviderConnection,
    ) -> None:
        """Spend at most one tiny request after a new/changed connection save."""
        started_at = time.monotonic()
        _log_provider_event(
            "probe_representative",
            "start",
            "started",
            connection_id=connection.connection_id,
            catalog_id=connection.catalog_id,
        )
        candidate = next(
            (
                item
                for item in connection.models
                if not item.hidden
                and not item.retired
                and item.discovery_state == "present"
            ),
            None,
        )
        if candidate is None:
            _log_provider_event(
                "probe_representative",
                "complete",
                "skipped",
                connection_id=connection.connection_id,
                catalog_id=connection.catalog_id,
                duration_ms=_elapsed_ms(started_at),
            )
            return
        probe = getattr(self._technology, "probe_model", None)
        if not callable(probe):
            _log_provider_event(
                "probe_representative",
                "complete",
                "skipped",
                connection_id=connection.connection_id,
                catalog_id=connection.catalog_id,
                duration_ms=_elapsed_ms(started_at),
            )
            return
        try:
            await probe(f"{connection.connection_id}/{candidate.model_id}")
        except (ProviderPortError, ValueError, OSError) as error:
            # The connection and inventory are already durable.  The probe
            # boundary records the failure; a failed check must not roll back
            # the user's configuration or hide the inventory.
            _log_provider_event(
                "probe_representative",
                "complete",
                "failed",
                connection_id=connection.connection_id,
                catalog_id=connection.catalog_id,
                model_count=1,
                duration_ms=_elapsed_ms(started_at),
                error=error,
            )
            return
        _log_provider_event(
            "probe_representative",
            "complete",
            "succeeded",
            connection_id=connection.connection_id,
            catalog_id=connection.catalog_id,
            model_count=1,
            duration_ms=_elapsed_ms(started_at),
        )

    async def _probe_reachability(
        self,
        connection: StoredProviderConnection,
    ) -> None:
        """Record zero-generation transport/auth evidence after saving config."""
        started_at = time.monotonic()
        _log_provider_event(
            "probe_reachability",
            "start",
            "started",
            connection_id=connection.connection_id,
            catalog_id=connection.catalog_id,
        )
        probe = getattr(self._technology, "probe_reachability", None)
        if not callable(probe):
            _log_provider_event(
                "probe_reachability",
                "complete",
                "skipped",
                connection_id=connection.connection_id,
                catalog_id=connection.catalog_id,
                duration_ms=_elapsed_ms(started_at),
            )
            return
        try:
            await probe(connection.connection_id)
        except (ProviderPortError, ValueError, OSError) as error:
            # Reachability is evidence, not a save gate. The connection and
            # inventory remain durable so the Owner can repair credentials or
            # the endpoint and retry explicitly.
            _log_provider_event(
                "probe_reachability",
                "complete",
                "failed",
                connection_id=connection.connection_id,
                catalog_id=connection.catalog_id,
                duration_ms=_elapsed_ms(started_at),
                error=error,
            )
            return
        _log_provider_event(
            "probe_reachability",
            "complete",
            "succeeded",
            connection_id=connection.connection_id,
            catalog_id=connection.catalog_id,
            duration_ms=_elapsed_ms(started_at),
        )

    def _connection_result(
        self,
        connection: StoredProviderConnection,
        *,
        verification: StoredVerification | None = None,
        refresh: StoredModelRefresh | None = None,
        projection: StoredProviderProjection | None = None,
    ) -> ProviderConnectionResult:
        try:
            product = self._product(connection.catalog_id)
            current_verification = verification or (
                projection.verification
                if projection is not None
                else self._technology.summarize_connection(connection)
            )
            if projection is None:
                model_results = tuple(
                    self._model_result(connection.connection_id, item)
                    for item in connection.models
                )
            else:
                model_ids = {item.model_id for item in connection.models}
                if set(projection.model_verifications) != model_ids:
                    raise ProviderPortError("Provider model projection mismatch")
                model_results = tuple(
                    self._model_result_from_verification(
                        item,
                        projection.model_verifications[item.model_id],
                    )
                    for item in connection.models
                )
            has_credential = self._connections.has_credential(connection.credential_ref)
            return ProviderConnectionResult(
                connection_id=connection.connection_id,
                catalog_id=connection.catalog_id,
                alias=connection.alias,
                api_base=connection.api_base,
                api_mode=connection.api_mode,
                auth_type=connection.auth_type,
                has_api_key=(product.connection_method == "api_key" and has_credential),
                has_credential=has_credential,
                enabled=connection.enabled,
                archived=connection.archived,
                usage_scope=product.usage_scope,
                verification=self._verification_result(current_verification),
                models=model_results,
                model_counts=self._model_counts(model_results),
                model_refresh=(
                    None
                    if refresh is None
                    else self._refresh_result(refresh, connection.connection_id)
                ),
            )
        except ProviderPortError as error:
            raise ProvidersUnavailable("Provider projection unavailable") from error

    def _model_result(
        self,
        connection_id: str,
        model: StoredProviderModel,
    ) -> ProviderModelResult:
        try:
            verification = self._technology.summarize_model(
                connection_id,
                model.model_id,
            )
        except ProviderPortError as error:
            raise ProvidersUnavailable(
                "Provider model projection unavailable"
            ) from error
        return self._model_result_from_verification(model, verification)

    @staticmethod
    def _model_result_from_verification(
        model: StoredProviderModel,
        verification: StoredModelVerification,
    ) -> ProviderModelResult:
        return ProviderModelResult(
            model_id=model.model_id,
            display_name=model.display_name,
            canonical_model_id=model.canonical_model_id,
            source=model.source,
            request_profile_id=model.request_profile_id,
            request_profile_version=model.request_profile_version,
            context_window_tokens=model.context_window_tokens,
            max_output_tokens=model.max_output_tokens,
            supports_tools=model.supports_tools,
            supports_vision=model.supports_vision,
            supports_reasoning=model.supports_reasoning,
            supports_structured_output=model.supports_structured_output,
            capability_evidence=model.capability_evidence,
            hidden=model.hidden,
            retired=model.retired,
            available=verification.availability_status == "available",
            verification=ProvidersService._model_verification_result(verification),
            discovery_state=model.discovery_state,
            consecutive_missing=model.consecutive_missing,
            last_seen_at=model.last_seen_at,
            pricing=model.pricing,
        )

    def _refresh_result(
        self,
        refresh: StoredModelRefresh,
        connection_id: str,
    ) -> ProviderModelRefreshResult:
        try:
            return ProviderModelRefreshResult(
                status=refresh.status,
                checked_at=refresh.checked_at,
                message=refresh.message,
                models=tuple(
                    self._model_result_from_verification(
                        item,
                        self._technology.summarize_model(
                            connection_id,
                            item.model_id,
                        ),
                    )
                    for item in refresh.models
                ),
            )
        except ProviderPortError as error:
            raise ProvidersUnavailable(
                "Provider model projection unavailable"
            ) from error

    @staticmethod
    def _model_counts(
        models: tuple[ProviderModelResult, ...],
    ) -> ProviderModelCounts:
        inventory = tuple(
            model
            for model in models
            if model.discovery_state == "present" and not model.retired
        )
        enabled = tuple(model for model in inventory if not model.hidden)
        statuses = tuple(model.verification.availability_status for model in enabled)
        return ProviderModelCounts(
            total=len(inventory),
            enabled=len(enabled),
            in_use=sum(model.verification.is_core for model in enabled),
            available=sum(status == "available" for status in statuses),
            degraded=sum(status == "degraded" for status in statuses),
            pending=sum(status == "unknown" for status in statuses),
            unavailable=sum(status == "unavailable" for status in statuses),
        )

    @staticmethod
    def _product_result(product: StoredProviderProduct) -> ProviderProductResult:
        return ProviderProductResult(
            catalog_id=product.catalog_id,
            name=product.name,
            brand=ProviderBrandResult(**vars(product.brand)),
            connection_method=product.connection_method,
            oauth_available=product.oauth_available,
            usage_scope=product.usage_scope,
            discovery_strategy=product.discovery_strategy,
            api_mode=product.api_mode,
            api_base=product.api_base,
            auth_type=product.auth_type,
            api_key_url=product.api_key_url,
            has_free_models=product.has_free_models,
        )

    @staticmethod
    def _verification_result(item: StoredVerification) -> ProviderVerificationResult:
        return ProviderVerificationResult(**vars(item))

    @staticmethod
    def _model_verification_result(
        item: StoredModelVerification,
    ) -> ProviderVerificationResult:
        return ProviderVerificationResult(
            status=item.status,
            checked_at=item.checked_at,
            latency_ms=item.latency_ms,
            error=item.error,
            validation_mode=item.validation_mode or "none",
            cache_hit=False,
            needs_full_validation=False,
            needs_heartbeat=False,
            full_run_id=item.full_run_id,
            full_checked_at=None,
            heartbeat_checked_at=None,
            heartbeat_status=None,
            representative_model_id=None,
            reason=None,
            availability_status=item.availability_status,
            reason_code=item.reason_code,
            evidence_source=item.evidence_source,
            expires_at=item.expires_at,
            is_core=item.is_core,
        )

    @staticmethod
    def _require_manager(principal: AccountPrincipal) -> None:
        if not is_manager(principal.role):
            raise ProvidersForbidden("Provider administration requires a manager")


def _updated_capability_evidence(
    model: StoredProviderModel,
    fields: frozenset[str],
    *,
    values: dict[str, bool | None],
) -> dict[str, CapabilityEvidence]:
    evidence = dict(model.capability_evidence)
    for capability, field_name in {
        "tools": "supports_tools",
        "vision": "supports_vision",
        "reasoning": "supports_reasoning",
        "structured_output": "supports_structured_output",
    }.items():
        if field_name in fields:
            evidence[capability] = (
                "declared_by_user" if values.get(capability) is not None else "unknown"
            )
    return evidence


def _user_capability_evidence(
    *,
    current: StoredProviderModel,
    values: dict[str, bool | None],
    fields: frozenset[str] | None,
) -> dict[str, CapabilityEvidence]:
    evidence = dict(current.capability_evidence)
    field_names = {
        "tools": "supports_tools",
        "vision": "supports_vision",
        "reasoning": "supports_reasoning",
        "structured_output": "supports_structured_output",
    }
    for capability, value in values.items():
        if fields is not None and field_names[capability] not in fields:
            continue
        evidence[capability] = "declared_by_user" if value is not None else "unknown"
    return evidence


def _replacement_value(
    item: ProviderModelReplacement,
    field_name: str,
    value: _T,
    current: _T,
) -> _T:
    if item.fields is not None and field_name not in item.fields:
        return current
    return value


__all__ = ("ProvidersService",)
