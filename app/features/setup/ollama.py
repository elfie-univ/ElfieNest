"""首次 Setup 的公共 Ollama 绑定用例。"""

from __future__ import annotations

import copy
from dataclasses import asdict
from typing import Any, Callable, Dict, cast

from ai_runtime.food.evidence import ModelEvidenceStore
from ai_runtime.food.store import FoodCatalogStore
from ai_runtime.models.model_reference import ModelReferenceError, parse_model_reference
from app.features.setup.artifact_rollback import rollback_artifacts
from app.features.setup.config_commit import complete_configured_setup_step
from app.features.setup.food_generation import generate_model_foods
from app.features.setup.progress import complete_setup_step, require_setup_step
from app.infrastructure.ollama_platform import (
    OllamaBinding,
    OllamaPlatformAdapter,
    OllamaProbe,
    PlatformName,
)


class OllamaSetupService:
    """Bind one public Ollama endpoint and refuse implicit endpoint replacement."""

    def __init__(
        self,
        *,
        adapter: OllamaPlatformAdapter,
        read_config: Callable[[], Dict[str, Any]],
        write_config: Callable[[Dict[str, Any]], None],
        restore_config: Callable[[Dict[str, Any]], None] | None = None,
        food_catalog_store: FoodCatalogStore | None = None,
        model_evidence_store: ModelEvidenceStore | None = None,
    ) -> None:
        self._adapter = adapter
        self._read_config = read_config
        self._write_config = write_config
        self._restore_config = restore_config or write_config
        self._food_catalog_store = food_catalog_store or FoodCatalogStore()
        self._model_evidence_store = model_evidence_store or ModelEvidenceStore()

    def detect(self) -> OllamaProbe:
        return self._adapter.probe(self._saved_binding())

    def bind_existing(self, *, db_path: str, endpoint: str) -> OllamaProbe:
        existing = self._saved_binding()
        if existing is not None and existing.api_base != endpoint:
            raise ValueError("Ollama endpoint 已固定；变更必须走 Owner 迁移")
        require_setup_step(db_path, 2)
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
        previous_config, config = self._save_binding(
            OllamaBinding(
                api_base=endpoint,
                platform=binding.platform,
                install_kind=binding.install_kind,
                launch_target=binding.launch_target,
                version=probe.version or binding.version,
            )
        )
        complete_configured_setup_step(
            restore_config=self._restore_config,
            previous_config=previous_config,
            config_snapshot=config,
            db_path=db_path,
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
        require_setup_step(db_path, 2)
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
        previous_config, config = self._save_binding(
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
        complete_configured_setup_step(
            restore_config=self._restore_config,
            previous_config=previous_config,
            config_snapshot=config,
            db_path=db_path,
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
            config_snapshot=self._read_config(),
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
        require_setup_step(db_path, 4)
        binding = self._saved_binding()
        if binding is None:
            raise ValueError("尚未绑定 Ollama，不能配置本地模型")
        if self._adapter.probe(binding).state != "healthy":
            raise RuntimeError("已绑定的 Ollama 不健康，不能配置模型")
        if reference.model_id not in self._adapter.list_models(binding):
            raise ValueError("所选模型不在已绑定的 Ollama endpoint 中")
        config = self._read_config()
        previous_config = copy.deepcopy(config)
        providers = config.get("providers")
        if not isinstance(providers, dict):
            raise ValueError("providers 配置无效")
        provider = providers.get("ollama")
        if not isinstance(provider, dict):
            raise ValueError("Ollama 配置缺失")
        provider["selected_model"] = model_reference
        with rollback_artifacts(self._model_evidence_store, self._food_catalog_store):
            generate_model_foods(
                model_reference,
                self._model_evidence_store,
                self._food_catalog_store,
            )
            self._write_config(config)
            complete_configured_setup_step(
                restore_config=self._restore_config,
                previous_config=previous_config,
                config_snapshot=config,
                db_path=db_path,
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
        require_setup_step(db_path, 4)
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

    def _saved_binding(self) -> OllamaBinding | None:
        providers = self._read_config().get("providers", {})
        if not isinstance(providers, dict):
            return None
        provider = providers.get("ollama", {})
        if not isinstance(provider, dict):
            return None
        raw = provider.get("installation")
        if not isinstance(raw, dict) or not provider.get("api_base"):
            return None
        try:
            return OllamaBinding(
                api_base=str(provider["api_base"]),
                platform=cast(PlatformName, str(raw["platform"])),
                install_kind=str(raw["install_kind"]),
                launch_target=str(raw["launch_target"]),
                version=str(raw.get("version", "")),
                installer_source_url=str(raw.get("installer_source_url", "")),
                installer_sha256=str(raw.get("installer_sha256", "")),
            )
        except KeyError:
            return None

    def _save_binding(
        self, binding: OllamaBinding
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        config = self._read_config()
        previous_config = copy.deepcopy(config)
        providers = config.setdefault("providers", {})
        if not isinstance(providers, dict):
            raise ValueError("providers 配置无效")
        providers["ollama"] = {
            "api_base": binding.api_base,
            "api_mode": "ollama",
            "auth_type": "none",
            "status": "configured",
            "installation": asdict(binding),
        }
        self._write_config(config)
        return previous_config, config
