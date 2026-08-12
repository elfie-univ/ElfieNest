"""Authorized Provider connection and model-resource use-cases."""

from __future__ import annotations

from dataclasses import replace

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
    CreateProviderConnectionCommand,
    DefaultLocalProviderConnectionResult,
    DeleteProviderConnectionCommand,
    DeleteProviderModelCommand,
    EnsureDefaultLocalProviderConnectionCommand,
    GetProviderModelMatrixQuery,
    InspectLocalProviderQuery,
    InstallLocalProviderCommand,
    ListProviderConnectionsQuery,
    ListProviderProductsQuery,
    LocalProviderModelResult,
    LocalProviderStatusResult,
    ProviderBenchmarkResult,
    ProviderBenchmarkRunResult,
    ProviderBrandResult,
    ProviderConnectionDeletedResult,
    ProviderConnectionResult,
    ProviderConnectionVerificationResult,
    ProviderMatrixCellResult,
    ProviderMatrixConnectionResult,
    ProviderMatrixModelResult,
    ProviderMatrixSnapshotResult,
    ProviderModelDeletedResult,
    ProviderModelInput,
    ProviderModelMatrixResult,
    ProviderModelRefreshResult,
    ProviderModelResult,
    ProviderProductResult,
    ProviderValidationItemResult,
    ProviderValidationRunResult,
    ProviderVerificationResult,
    PullLocalProviderModelsCommand,
    RefreshProviderModelsCommand,
    RemoveLocalProviderConnectionCommand,
    ReplaceProviderModelsCommand,
    StartLocalProviderCommand,
    UpdateProviderConnectionCommand,
    UpdateProviderModelCommand,
    ValidateAllProviderModelsCommand,
    VerifyProviderConnectionCommand,
)
from .port_models import (
    StoredBenchmarkCombination,
    StoredLocalProviderBinding,
    StoredModelRefresh,
    StoredModelVerification,
    StoredProviderConnection,
    StoredProviderModel,
    StoredProviderProduct,
    StoredVerification,
)
from .ports import (
    BackgroundTaskScheduler,
    CancellationCheck,
    ProviderCatalogPort,
    ProviderConnectionPort,
    ProviderLocalStatePort,
    ProviderLocalTechnologyPort,
    ProviderPortError,
    ProviderReferencePort,
    ProviderTechnologyPort,
)


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
    ) -> None:
        self._catalog = catalog
        self._connections = connections
        self._references = references
        self._technology = technology
        self._local_state = local_state
        self._local_technology = local_technology
        self._local_jobs = LocalProviderJobManager()

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
    ) -> LocalProviderStatusResult:
        _ = query
        self._require_manager(principal)
        try:
            recorded = self._local_state.load_local_binding()
            binding = recorded or self._local_technology.default_binding()
            probe = self._local_technology.probe(binding)
            if recorded is None and probe.state == "deleted":
                probe = replace(probe, state="absent")
            installed = self._installed_local_models(probe.state, binding)
            candidates = self._local_technology.candidate_models()
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
            LocalProviderModelResult(
                model_id=item.model_id,
                display_name=item.display_name,
                installed=item.model_id in installed,
                recommended=item.recommended,
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
        return self.inspect_local_provider(principal, InspectLocalProviderQuery())

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
        return self.inspect_local_provider(principal, InspectLocalProviderQuery())

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
        return self.inspect_local_provider(principal, InspectLocalProviderQuery())

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
        try:
            return tuple(
                self._product_result(item) for item in self._catalog.list_products()
            )
        except ProviderPortError as error:
            raise ProvidersUnavailable("Provider catalog unavailable") from error

    def list_connections(
        self,
        principal: AccountPrincipal,
        query: ListProviderConnectionsQuery,
    ) -> tuple[ProviderConnectionResult, ...]:
        _ = query
        self._require_manager(principal)
        try:
            return tuple(
                self._connection_result(item)
                for item in self._connections.list_connections()
            )
        except ProviderPortError as error:
            raise ProvidersUnavailable("Provider connections unavailable") from error

    async def create_connection(
        self,
        principal: AccountPrincipal,
        command: CreateProviderConnectionCommand,
    ) -> ProviderConnectionResult:
        self._require_manager(principal)
        product = self._product(command.catalog_id)
        if product.connection_method == "local" and command.api_key:
            raise ProvidersValidationError("Local connections do not accept an API key")
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
            refresh = None
            if command.refresh_models:
                refresh = await self._refresh(connection)
                connection = self._require_connection(connection.connection_id)
            verification = (
                await self._technology.verify_connection(connection, force_full=False)
                if command.verify
                else None
            )
            return self._connection_result(
                connection,
                verification=verification,
                refresh=refresh,
            )
        except ProviderPortError as error:
            raise ProvidersUnavailable(
                "Provider connection could not be created"
            ) from error

    async def update_connection(
        self,
        principal: AccountPrincipal,
        command: UpdateProviderConnectionCommand,
    ) -> ProviderConnectionResult:
        self._require_manager(principal)
        connection = self._require_connection(command.connection_id)
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
            refresh = None
            if command.refresh_models:
                refresh = await self._refresh(updated)
                updated = self._require_connection(updated.connection_id)
            verification = (
                await self._technology.verify_connection(updated, force_full=False)
                if command.verify
                else None
            )
            return self._connection_result(
                updated,
                verification=verification,
                refresh=refresh,
            )
        except ProviderPortError as error:
            raise ProvidersUnavailable(
                "Provider connection could not be updated"
            ) from error

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
        if not connection.archived:
            raise ProvidersConflict("The connection must be archived before deletion")
        try:
            references = self._references.connections_referenced_by_food(
                connection.connection_id
            )
            if references:
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
        try:
            verification = await self._technology.verify_connection(
                connection,
                force_full=command.force_full,
            )
        except ProviderPortError as error:
            raise ProvidersUnavailable("Provider validation unavailable") from error
        return ProviderConnectionVerificationResult(
            connection_id=connection.connection_id,
            verification=self._verification_result(verification),
        )

    async def refresh_models(
        self,
        principal: AccountPrincipal,
        command: RefreshProviderModelsCommand,
    ) -> ProviderModelRefreshResult:
        self._require_manager(principal)
        return self._refresh_result(
            await self._refresh(self._require_connection(command.connection_id)),
            command.connection_id,
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
        self._replace_models(connection, (*connection.models, model))
        return self._model_result(connection.connection_id, model)

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
                    display_name=item.display_name,
                    canonical_model_id=item.canonical_model_id,
                    context_window_tokens=item.context_window_tokens,
                    max_output_tokens=item.max_output_tokens,
                    supports_tools=item.supports_tools,
                    supports_vision=item.supports_vision,
                    supports_reasoning=item.supports_reasoning,
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
        self._replace_models(
            connection,
            tuple(
                updated if item.model_id == command.model_id else item
                for item in connection.models
            ),
        )
        return self._model_result(connection.connection_id, updated)

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
            raise ProvidersUnavailable("Provider validation unavailable") from error
        return ProviderValidationRunResult(
            run_id=run.run_id,
            status=run.status,
            results=tuple(
                ProviderValidationItemResult(**vars(item)) for item in run.results
            ),
        )

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
        try:
            return self._connections.replace_connection(
                replace(connection, models=models),
                None,
                update_credential=False,
            )
        except ProviderPortError as error:
            raise ProvidersUnavailable(
                "Provider models could not be updated"
            ) from error

    async def _refresh(
        self,
        connection: StoredProviderConnection,
    ) -> StoredModelRefresh:
        try:
            refresh = await self._technology.refresh_models(connection)
            self._replace_models(connection, refresh.models)
            return refresh
        except ProviderPortError as error:
            raise ProvidersUnavailable("Provider model refresh unavailable") from error

    def _connection_result(
        self,
        connection: StoredProviderConnection,
        *,
        verification: StoredVerification | None = None,
        refresh: StoredModelRefresh | None = None,
    ) -> ProviderConnectionResult:
        try:
            product = self._product(connection.catalog_id)
            current_verification = (
                verification or self._technology.summarize_connection(connection)
            )
            return ProviderConnectionResult(
                connection_id=connection.connection_id,
                catalog_id=connection.catalog_id,
                alias=connection.alias,
                api_base=connection.api_base,
                api_mode=connection.api_mode,
                auth_type=connection.auth_type,
                has_api_key=self._connections.has_credential(connection.credential_ref),
                enabled=connection.enabled,
                archived=connection.archived,
                usage_scope=product.usage_scope,
                verification=self._verification_result(current_verification),
                models=tuple(
                    self._model_result(connection.connection_id, item)
                    for item in connection.models
                ),
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
        return ProviderModelResult(
            model_id=model.model_id,
            display_name=model.display_name,
            canonical_model_id=model.canonical_model_id,
            source=model.source,
            context_window_tokens=model.context_window_tokens,
            max_output_tokens=model.max_output_tokens,
            supports_tools=model.supports_tools,
            supports_vision=model.supports_vision,
            supports_reasoning=model.supports_reasoning,
            hidden=model.hidden,
            retired=model.retired,
            available=model.available,
            verification=self._model_verification_result(verification),
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
                    ProviderModelResult(
                        model_id=item.model_id,
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
                        verification=self._model_verification_result(
                            self._technology.summarize_model(
                                connection_id,
                                item.model_id,
                            )
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
        )

    @staticmethod
    def _require_manager(principal: AccountPrincipal) -> None:
        if not is_manager(principal.role):
            raise ProvidersForbidden("Provider administration requires a manager")


__all__ = ("ProvidersService",)
