"""首次 Setup 的公共 Ollama 绑定用例。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from typing import Callable, cast

from ai_runtime.food.evidence import query_model_evidence, record_model_evidence
from ai_runtime.food.models import FOOD_EMERGENCY_ID
from ai_runtime.food.planner import FoodPlanner, ModelEvidence
from ai_runtime.food.store import FoodCatalogRepository
from ai_runtime.models.capabilities import canonical_display_name, known_capabilities
from ai_runtime.storage.provider_connections import (
    ProviderConnection,
    ProviderConnectionStore,
    ProviderModelRecord,
)
from ai_runtime.storage.report_repository import ReportRepository
from app.infrastructure.ollama_platform import (
    DEFAULT_OLLAMA_ENDPOINT,
    OllamaBinding,
    OllamaPlatformAdapter,
    OllamaProbe,
    PlatformName,
    wait_for_healthy,
)
from app.infrastructure.ollama_platform_commands import official_launch_target


@dataclass(frozen=True)
class OllamaSetupObservation:
    """One fixed-endpoint inspection used by Setup UI recommendations."""

    probe: OllamaProbe
    models: tuple[str, ...]


class OllamaSetupService:
    """Inspect and prepare the one documented public Ollama endpoint."""

    def __init__(
        self,
        *,
        adapter: OllamaPlatformAdapter,
        provider_connection_store: ProviderConnectionStore | None = None,
        food_catalog_repository: FoodCatalogRepository | None = None,
        report_repository: ReportRepository | None = None,
    ) -> None:
        self._adapter = adapter
        self._provider_connection_store = (
            provider_connection_store or ProviderConnectionStore()
        )
        self._food_catalog_repository = food_catalog_repository
        self._report_repository = report_repository or ReportRepository()

    def inspect(
        self,
        *,
        default_endpoint: str = DEFAULT_OLLAMA_ENDPOINT,
    ) -> OllamaSetupObservation:
        """Inspect the saved endpoint or the documented local endpoint once."""
        saved_binding = self._saved_binding()
        binding = saved_binding or self._default_binding(default_endpoint)
        probe = self._adapter.probe(binding)
        if saved_binding is None and probe.state == "deleted":
            probe = OllamaProbe("absent", probe.endpoint, detail=probe.detail)
        if probe.state != "healthy":
            return OllamaSetupObservation(probe=probe, models=())
        try:
            models = self._adapter.list_models(binding)
        except RuntimeError:
            models = ()
        return OllamaSetupObservation(probe=probe, models=models)

    def ensure_for_install(
        self, *, report_action: Callable[[str], None]
    ) -> OllamaBinding:
        """Reuse, start, repair, or install the one documented public Ollama."""
        saved = self._saved_binding()
        candidate = saved or self._default_binding()
        probe = self._adapter.probe(candidate)
        if probe.state == "healthy":
            report_action("ollama.reuse")
            binding = replace(candidate, version=probe.version or candidate.version)
            self._save_binding(binding)
            return binding
        if probe.state == "stopped":
            report_action("ollama.start")
            try:
                self._adapter.start_bound_installation(candidate)
                started = wait_for_healthy(self._adapter, candidate)
                if started.state == "healthy":
                    binding = replace(
                        candidate, version=started.version or candidate.version
                    )
                    self._save_binding(binding)
                    return binding
            except RuntimeError:
                pass
        report_action("ollama.repair" if saved is not None else "ollama.install")
        return self._install_public(endpoint=candidate.api_base)

    def ensure_model_for_install(
        self,
        *,
        model_id: str,
        report_action: Callable[[str], None],
    ) -> str:
        """Reuse or pull one allow-listed model and persist its exact connection ref."""
        from app.features.setup.model_catalog import get_setup_model

        get_setup_model(model_id)
        binding = self._saved_binding()
        if binding is None or self._adapter.probe(binding).state != "healthy":
            raise RuntimeError("本地 Ollama 未通过健康检查")
        models = set(self._adapter.list_models(binding))
        if model_id in models:
            report_action("model.reuse")
        else:
            report_action("model.download")
            self._adapter.pull_model(binding, model_id)
            models = set(self._adapter.list_models(binding))
            if model_id not in models:
                raise RuntimeError("Ollama 未确认所选模型已下载")
        connection = self._saved_connection()
        if connection is None:
            raise RuntimeError("Ollama 连接配置缺失")
        configured_models = {
            model.endpoint_model_id: model for model in connection.models
        }
        configured_models[model_id] = ProviderModelRecord(
            endpoint_model_id=model_id,
            display_name=model_id,
            source="official",
        )
        self._provider_connection_store.replace(
            replace(connection, models=tuple(configured_models.values()))
        )
        return f"{connection.connection_id}/{model_id}"

    def generate_emergency_food(self, model_reference: str) -> None:
        """Generate only the emergency package for the verified local model."""
        self._generate_foods(model_reference)

    def _default_binding(
        self, endpoint: str = DEFAULT_OLLAMA_ENDPOINT
    ) -> OllamaBinding:
        try:
            target, _ = official_launch_target(self._adapter.platform)
        except RuntimeError:
            target = ""
        return OllamaBinding(
            api_base=endpoint.rstrip("/"),
            platform=self._adapter.platform,
            install_kind="existing-public",
            launch_target=target,
            version="",
        )

    def _install_public(self, *, endpoint: str) -> OllamaBinding:
        installer = self._adapter.download_official_installer()
        self._adapter.run_confirmed_installer(installer, user_confirmed=True)
        binding = self._adapter.official_binding_after_install(
            endpoint=endpoint,
            installer=installer,
        )
        self._adapter.start_bound_installation(binding)
        probe = wait_for_healthy(self._adapter, binding)
        if probe.state != "healthy":
            raise RuntimeError("官方 Ollama 安装后未通过健康检查")
        binding = replace(binding, version=probe.version or binding.version)
        self._save_binding(binding)
        return binding

    def _generate_foods(self, model_reference: str) -> None:
        """Generate only evidence-backed recipes for the verified local model."""
        evidence = ModelEvidence(
            model=model_reference,
            display_name=canonical_display_name(model_reference, model_reference),
            capabilities=frozenset({"text"})
            | known_capabilities(model_reference, model_reference),
            verified=True,
            cost_grade=0,
            local=True,
            observed_at=datetime.now(timezone.utc).isoformat(),
        )
        record_model_evidence(
            (evidence,),
            repository=self._report_repository,
            scope=f"setup:{model_reference}",
            trigger="setup",
        )
        all_evidence = tuple(
            query_model_evidence(
                repository=self._report_repository,
                connection_store=self._provider_connection_store,
            ).values()
        )
        if self._food_catalog_repository is None:
            raise RuntimeError("Setup 未注入粮食数据库仓储")
        package = self._food_catalog_repository.get(FOOD_EMERGENCY_ID)
        if package is None:
            raise RuntimeError("Setup 找不到保底粮数据库记录")
        planner = FoodPlanner()
        proposed = planner.propose_package(
            package,
            all_evidence,
            connection_ids=(model_reference.split("/", 1)[0],),
            local_first=True,
            allow_remote=False,
        ).package
        self._food_catalog_repository.update(proposed)

    def _saved_connection(self) -> ProviderConnection | None:
        return next(
            (
                connection
                for connection in self._provider_connection_store.load().connections.values()
                if connection.catalog_id == "ollama"
            ),
            None,
        )

    def _saved_binding(self) -> OllamaBinding | None:
        connection = self._saved_connection()
        if connection is None or not connection.installation or not connection.api_base:
            return None
        raw = connection.installation
        try:
            return OllamaBinding(
                api_base=connection.api_base,
                platform=cast(PlatformName, str(raw["platform"])),
                install_kind=str(raw["install_kind"]),
                launch_target=str(raw["launch_target"]),
                version=str(raw.get("version", "")),
                installer_source_url=str(raw.get("installer_source_url", "")),
                installer_sha256=str(raw.get("installer_sha256", "")),
            )
        except KeyError:
            return None

    def _save_binding(self, binding: OllamaBinding) -> None:
        installation = {
            key: str(value)
            for key, value in asdict(binding).items()
            if value is not None
        }
        connection = self._saved_connection()
        if connection is None:
            self._provider_connection_store.create(
                catalog_id="ollama",
                alias="Ollama",
                api_base=binding.api_base,
                api_mode="ollama",
                auth_type="none",
                installation=installation,
            )
            return
        self._provider_connection_store.replace(
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
