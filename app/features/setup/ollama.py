"""首次 Setup 的公共 Ollama 绑定用例。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from typing import cast

from ai_runtime.food.evidence import query_model_evidence, record_model_evidence
from ai_runtime.food.models import FOOD_COMMON_ID, FOOD_EMERGENCY_ID
from ai_runtime.food.planner import FoodPlanner, ModelEvidence
from ai_runtime.food.store import FoodCatalogStore
from ai_runtime.models.capabilities import canonical_display_name, known_capabilities
from ai_runtime.models.model_reference import ModelReferenceError, parse_model_reference
from ai_runtime.storage.provider_connections import (
    ProviderConnection,
    ProviderConnectionStore,
    ProviderModelRecord,
)
from ai_runtime.storage.report_repository import ReportRepository
from app.features.setup.progress import complete_setup_step
from app.infrastructure.ollama_platform import (
    DEFAULT_OLLAMA_ENDPOINT,
    OllamaBinding,
    OllamaPlatformAdapter,
    OllamaProbe,
    PlatformName,
)


@dataclass(frozen=True)
class OllamaSetupObservation:
    """One fixed-endpoint inspection used by Setup UI recommendations."""

    probe: OllamaProbe
    models: tuple[str, ...]


class OllamaSetupService:
    """Bind one public Ollama endpoint and refuse implicit endpoint replacement."""

    def __init__(
        self,
        *,
        adapter: OllamaPlatformAdapter,
        provider_connection_store: ProviderConnectionStore | None = None,
        food_catalog_store: FoodCatalogStore | None = None,
        report_repository: ReportRepository | None = None,
    ) -> None:
        self._adapter = adapter
        self._provider_connection_store = (
            provider_connection_store or ProviderConnectionStore()
        )
        self._food_catalog_store = food_catalog_store or FoodCatalogStore()
        self._report_repository = report_repository or ReportRepository()

    def detect(self) -> OllamaProbe:
        return self._adapter.probe(self._saved_binding())

    def inspect(
        self,
        *,
        default_endpoint: str = DEFAULT_OLLAMA_ENDPOINT,
    ) -> OllamaSetupObservation:
        """Inspect the saved endpoint or the documented local endpoint once."""
        saved_binding = self._saved_binding()
        binding = saved_binding or OllamaBinding(
            api_base=default_endpoint.rstrip("/"),
            platform=self._adapter.platform,
            install_kind="existing-public",
            launch_target="",
            version="",
        )
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

    def bind_existing(self, *, db_path: str, endpoint: str) -> OllamaProbe:
        existing = self._saved_binding()
        if existing is not None and existing.api_base != endpoint:
            raise ValueError("Ollama endpoint 已固定；变更必须走 Owner 迁移")
        binding = existing or OllamaBinding(
            api_base=endpoint,
            platform=self._adapter.platform,
            install_kind="existing-public",
            launch_target="",
            version="",
        )
        probe = self._adapter.probe(binding)
        if probe.state != "healthy":
            raise RuntimeError("指定的 Ollama endpoint 未健康，不能绑定")
        self._save_binding(
            OllamaBinding(
                api_base=endpoint,
                platform=binding.platform,
                install_kind=binding.install_kind,
                launch_target=binding.launch_target,
                version=probe.version or binding.version,
            )
        )
        complete_setup_step(
            db_path,
            step=2,
            decision="bound_existing",
            ollama_endpoint=endpoint,
        )
        return probe

    def skip(self, *, db_path: str) -> None:
        complete_setup_step(db_path, step=2, decision="skipped")

    def install_official(
        self,
        *,
        db_path: str,
        endpoint: str,
        user_confirmed: bool,
    ) -> OllamaProbe:
        """Install only once, from the fixed official source, after user consent."""
        if self._saved_binding() is not None:
            raise ValueError("已有 Ollama 绑定；升级或修复必须单独确认")
        installer = self._adapter.download_official_installer()
        self._adapter.run_confirmed_installer(installer, user_confirmed=user_confirmed)
        binding = self._adapter.official_binding_after_install(
            endpoint=endpoint,
            installer=installer,
        )
        self._adapter.start_bound_installation(binding)
        probe = self._adapter.probe(binding)
        if probe.state != "healthy":
            raise RuntimeError("官方 Ollama 安装后未通过健康检查")
        self._adapter.list_models(binding)
        self._save_binding(
            OllamaBinding(
                api_base=binding.api_base,
                platform=binding.platform,
                install_kind=binding.install_kind,
                launch_target=binding.launch_target,
                version=probe.version or binding.version,
                installer_source_url=binding.installer_source_url,
                installer_sha256=binding.installer_sha256,
            )
        )
        complete_setup_step(
            db_path,
            step=2,
            decision="install_official",
            ollama_endpoint=endpoint,
        )
        return probe

    def repair_bound(self, *, db_path: str) -> OllamaProbe:
        """Start the one saved public installation; never discover a replacement."""
        binding = self._saved_binding()
        if binding is None:
            raise ValueError("没有已保存的 Ollama 绑定可修复")
        probe = self._adapter.probe(binding)
        if probe.state == "healthy":
            return probe
        if probe.state != "stopped":
            raise RuntimeError("已绑定的 Ollama 需要手动修复，不能自动改绑")
        self._adapter.start_bound_installation(binding)
        repaired = self._adapter.probe(binding)
        if repaired.state != "healthy":
            raise RuntimeError("已绑定的 Ollama 启动后仍未健康")
        complete_setup_step(
            db_path,
            step=2,
            decision="bound_existing",
            ollama_endpoint=binding.api_base,
        )
        return repaired

    def configure_installed_model(
        self,
        *,
        db_path: str,
        model_reference: str,
    ) -> None:
        """Persist only a model verified on the one already bound Ollama endpoint."""
        try:
            reference = parse_model_reference(model_reference)
        except ModelReferenceError as exc:
            raise ValueError(str(exc)) from exc
        if reference.provider_id != "ollama":
            raise ValueError("本地模型必须使用已绑定的 ollama/provider_id")
        binding = self._saved_binding()
        if binding is None:
            raise ValueError("尚未绑定 Ollama，不能配置本地模型")
        if self._adapter.probe(binding).state != "healthy":
            raise RuntimeError("已绑定的 Ollama 不健康，不能配置模型")
        if reference.model_id not in self._adapter.list_models(binding):
            raise ValueError("所选模型不在已绑定的 Ollama endpoint 中")
        connection = self._saved_connection()
        if connection is None:
            raise ValueError("Ollama 连接配置缺失")
        models = {model.endpoint_model_id: model for model in connection.models}
        models[reference.model_id] = ProviderModelRecord(
            endpoint_model_id=reference.model_id,
            display_name=reference.model_id,
            source="official",
        )
        self._provider_connection_store.replace(
            replace(connection, models=tuple(models.values()))
        )
        exact_reference = f"{connection.connection_id}/{reference.model_id}"
        self._generate_foods(exact_reference)
        complete_setup_step(
            db_path,
            step=4,
            decision="configured",
            model_reference=model_reference,
        )

    def pull_and_configure_model(
        self,
        *,
        db_path: str,
        model_reference: str,
    ) -> None:
        """Pull only through the saved endpoint, then prove the model is really present."""
        try:
            reference = parse_model_reference(model_reference)
        except ModelReferenceError as exc:
            raise ValueError(str(exc)) from exc
        if reference.provider_id != "ollama":
            raise ValueError("本地模型必须使用已绑定的 ollama/provider_id")
        binding = self._saved_binding()
        if binding is None:
            raise ValueError("尚未绑定 Ollama，不能拉取本地模型")
        if self._adapter.probe(binding).state != "healthy":
            raise RuntimeError("已绑定的 Ollama 不健康，不能拉取模型")
        if reference.model_id not in self._adapter.list_models(binding):
            self._adapter.pull_model(binding, reference.model_id)
        self.configure_installed_model(
            db_path=db_path,
            model_reference=model_reference,
        )

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
        catalog = self._food_catalog_store.load()
        packages = dict(catalog.packages)
        planner = FoodPlanner()
        for food_id in (FOOD_EMERGENCY_ID, FOOD_COMMON_ID):
            packages[food_id] = planner.propose_package(
                packages[food_id],
                all_evidence,
                connection_ids=(model_reference.split("/", 1)[0],),
                local_first=food_id == FOOD_EMERGENCY_ID,
                allow_remote=False,
            ).package
        self._food_catalog_store.save(replace(catalog, packages=packages))

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
