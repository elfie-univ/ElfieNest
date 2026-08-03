"""Owner-facing Ollama state, binding, and local model operations."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final

from ai_runtime.models.local_profiles import recommend_local_profile
from ai_runtime.providers.catalog import ProviderProfile
from ai_runtime.providers.profiles import get_product
from ai_runtime.storage.provider_connections import (
    ProviderConnection,
    ProviderConnectionStore,
    ProviderModelRecord,
)
from app.features.setup.hardware import get_available_memory_gb
from app.features.setup.ollama_owner_jobs import OllamaTask
from app.infrastructure.ollama_platform import (
    DEFAULT_OLLAMA_ENDPOINT,
    OllamaBinding,
    OllamaPlatformAdapter,
    OllamaProbe,
    PlatformName,
    is_safe_local_endpoint,
    wait_for_healthy,
)
from app.infrastructure.ollama_platform_commands import official_launch_target

_OLLAMA_CATALOG_ID: Final[str] = "ollama"


@dataclass(frozen=True)
class OllamaModelOption:
    id: str
    display_name: str
    installed: bool
    recommended: bool


@dataclass(frozen=True)
class OllamaOwnerObservation:
    probe: OllamaProbe
    memory_gb: int
    recommended_model: str | None
    installed_model_count: int
    models: tuple[OllamaModelOption, ...]
    task: OllamaTask | None


class OllamaOwnerService:
    """Inspect the fixed local endpoint and persist only proven local models."""

    def __init__(
        self,
        adapter: OllamaPlatformAdapter,
        provider_connection_store: ProviderConnectionStore | None = None,
    ) -> None:
        self._adapter = adapter
        self._store = provider_connection_store or ProviderConnectionStore()

    def inspect(self, task: OllamaTask | None = None) -> OllamaOwnerObservation:
        profile = _ollama_profile()
        recorded = self._recorded_binding()
        binding = recorded or self._default_binding()
        probe = self._adapter.probe(binding)
        if recorded is None and probe.state == "deleted":
            probe = OllamaProbe("absent", probe.endpoint, detail=probe.detail)
        installed = self._installed_names(probe, binding)
        memory_gb = get_available_memory_gb()
        recommendation = recommend_local_profile(memory_gb)
        recommended_model = recommendation.text_model if recommendation else None
        models = _model_options(installed, profile, recommended_model)
        return OllamaOwnerObservation(
            probe=probe,
            memory_gb=memory_gb,
            recommended_model=recommended_model,
            installed_model_count=sum(model.installed for model in models),
            models=models,
            task=task,
        )

    def connect_or_start(self) -> OllamaProbe:
        recorded = self._recorded_binding()
        binding = recorded or self._default_binding()
        probe = self._adapter.probe(binding)
        if probe.state == "healthy":
            return self._save_binding(replace(binding, version=probe.version or binding.version))
        if probe.state == "stopped":
            self._adapter.start_bound_installation(binding)
            started = wait_for_healthy(self._adapter, binding)
            if started.state != "healthy":
                raise RuntimeError("Ollama 启动后仍未健康")
            return self._save_binding(replace(binding, version=started.version or binding.version))
        if probe.state in {"absent", "deleted"}:
            raise RuntimeError("Ollama 安装不存在，请先安装")
        raise RuntimeError("已记录的 Ollama 安装需要修复")

    def pull_and_save(self, model_ids: tuple[str, ...]) -> None:
        allowed = set(_ollama_profile().bundled_models)
        if any(model_id not in allowed for model_id in model_ids):
            raise ValueError("所选模型不在本地候选清单中")
        binding = self._recorded_binding()
        if binding is None:
            binding = self._default_binding()
            if binding is None or self._adapter.probe(binding).state != "healthy":
                raise RuntimeError("Ollama 尚未健康，不能下载模型")
            self._save_binding(binding)
        if self._adapter.probe(binding).state != "healthy":
            raise RuntimeError("Ollama 不健康，不能下载模型")
        installed = set(self._adapter.list_models(binding))
        for model_id in model_ids:
            if model_id not in installed:
                self._adapter.pull_model(binding, model_id)
        self._save_models(binding, self._adapter.list_models(binding))

    def _installed_names(
        self,
        probe: OllamaProbe,
        binding: OllamaBinding,
    ) -> tuple[str, ...]:
        if probe.state == "healthy":
            try:
                return self._adapter.list_models(binding)
            except RuntimeError:
                return self._stored_model_names()
        return self._stored_model_names()

    def _recorded_binding(self) -> OllamaBinding | None:
        connection = self._ollama_connection()
        if connection is None or not connection.installation or not connection.api_base:
            return None
        if not is_safe_local_endpoint(connection.api_base):
            return None
        raw = connection.installation
        platform_name = raw.get("platform")
        if platform_name is None:
            return None
        if platform_name == "darwin":
            platform: PlatformName = "darwin"
        elif platform_name == "linux":
            platform = "linux"
        elif platform_name == "win32":
            platform = "win32"
        else:
            return None
        return OllamaBinding(
            api_base=connection.api_base,
            platform=platform,
            install_kind=raw.get("install_kind", "existing-public"),
            launch_target=raw.get("launch_target", ""),
            version=raw.get("version", ""),
            installer_source_url=raw.get("installer_source_url", ""),
            installer_sha256=raw.get("installer_sha256", ""),
        )

    def _default_binding(self) -> OllamaBinding:
        launch_target = ""
        try:
            launch_target, _ = official_launch_target(self._adapter.platform)
        except (OSError, RuntimeError):
            pass
        return OllamaBinding(
            api_base=DEFAULT_OLLAMA_ENDPOINT,
            platform=self._adapter.platform,
            install_kind="existing-public",
            launch_target=launch_target,
            version="",
        )

    def _save_binding(self, binding: OllamaBinding) -> OllamaProbe:
        if not is_safe_local_endpoint(binding.api_base):
            raise ValueError("Ollama endpoint 必须是本机回环地址")
        connection = self._ollama_connection()
        installation = {
            "platform": binding.platform,
            "install_kind": binding.install_kind,
            "launch_target": binding.launch_target,
            "version": binding.version,
            "installer_source_url": binding.installer_source_url,
            "installer_sha256": binding.installer_sha256,
        }
        if connection is None:
            self._store.create(
                catalog_id=_OLLAMA_CATALOG_ID,
                alias="Ollama",
                api_base=binding.api_base,
                api_mode="ollama",
                auth_type="none",
                installation=installation,
            )
        else:
            self._store.replace(replace(
                connection,
                api_base=binding.api_base,
                api_mode="ollama",
                auth_type="none",
                installation=installation,
                enabled=True,
                archived=False,
            ))
        return OllamaProbe("healthy", binding.api_base, version=binding.version or None)

    def _save_models(self, binding: OllamaBinding, model_ids: tuple[str, ...]) -> None:
        connection = self._ollama_connection()
        if connection is None:
            self._save_binding(binding)
            connection = self._ollama_connection()
        if connection is None:
            raise RuntimeError("Ollama 连接配置保存失败")
        old_models = {model.endpoint_model_id: model for model in connection.models}
        models = tuple(
            replace(old_models[model_id], source="official", available=True)
            if model_id in old_models
            else ProviderModelRecord(endpoint_model_id=model_id, display_name=model_id, source="official")
            for model_id in model_ids
        )
        self._store.replace(replace(connection, models=models, enabled=True, archived=False))

    def _stored_model_names(self) -> tuple[str, ...]:
        connection = self._ollama_connection()
        return tuple(model.endpoint_model_id for model in connection.models) if connection else ()

    def _ollama_connection(self) -> ProviderConnection | None:
        return next((connection for connection in self._store.load().connections.values() if connection.catalog_id == _OLLAMA_CATALOG_ID), None)


def _ollama_profile() -> ProviderProfile:
    profile = get_product(_OLLAMA_CATALOG_ID)
    if profile is None:
        raise RuntimeError("Ollama 产品目录缺失")
    return profile


def _model_options(
    installed: tuple[str, ...],
    profile: ProviderProfile,
    recommended_model: str | None,
) -> tuple[OllamaModelOption, ...]:
    installed_set = set(installed)
    ordered_ids = list(dict.fromkeys((*installed, *profile.bundled_models)))
    return tuple(
        OllamaModelOption(
            id=model_id,
            display_name=model_id,
            installed=model_id in installed_set,
            recommended=model_id == recommended_model,
        )
        for model_id in ordered_ids
    )
