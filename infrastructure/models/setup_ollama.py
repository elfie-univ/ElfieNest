"""Ollama technical Adapter used only by first-run Setup."""

from __future__ import annotations

from dataclasses import replace
from typing import Callable, Literal, Optional, Protocol

from app.features.setup import SetupPortError, StoredOllamaObservation
from app.orchestration.setup_installation import (
    SetupDownloadedInstaller,
    SetupInstallationPortError,
    SetupOllamaBinding,
    SetupOllamaProbe,
    SetupOllamaTaskLease,
)

LoadBinding = Callable[[], Optional[SetupOllamaBinding]]
SaveBinding = Callable[[SetupOllamaBinding], None]
SaveModel = Callable[[str], str]
AcquireTaskLease = Callable[[SetupOllamaBinding], Optional[SetupOllamaTaskLease]]


class SetupOllamaTechnologyPort(Protocol):
    @property
    def platform(self) -> Literal["darwin", "linux", "win32"]: ...

    def default_binding(self) -> SetupOllamaBinding: ...
    def probe(self, binding: SetupOllamaBinding) -> SetupOllamaProbe: ...
    def list_models(self, binding: SetupOllamaBinding) -> tuple[str, ...]: ...
    def download_official_installer(self) -> SetupDownloadedInstaller: ...
    def run_confirmed_installer(
        self, installer: SetupDownloadedInstaller, *, user_confirmed: bool
    ) -> None: ...
    def official_binding_after_install(
        self, *, endpoint: str, installer: SetupDownloadedInstaller
    ) -> SetupOllamaBinding: ...
    def start_bound_installation(self, binding: SetupOllamaBinding) -> None: ...
    def wait_for_healthy(self, binding: SetupOllamaBinding) -> SetupOllamaProbe: ...
    def pull_model(self, binding: SetupOllamaBinding, model_id: str) -> None: ...


class SetupOllamaAdapter:
    """Probe and execute explicit Ollama choices without owning Provider facts."""

    def __init__(
        self,
        *,
        technology: SetupOllamaTechnologyPort,
        load_binding: LoadBinding,
        save_binding: SaveBinding,
        save_model: SaveModel,
        acquire_task_lease: AcquireTaskLease | None = None,
    ) -> None:
        self._technology = technology
        self._load_binding = load_binding
        self._save_binding = save_binding
        self._save_model = save_model
        self._acquire_task_lease = acquire_task_lease

    @property
    def platform(self) -> Literal["darwin", "linux", "win32"]:
        return self._technology.platform

    def inspect(self) -> StoredOllamaObservation:
        try:
            saved = self._load_binding()
            binding = saved or self._default_binding()
            probe = self._technology.probe(binding)
            state = (
                "absent" if saved is None and probe.state == "deleted" else probe.state
            )
            models = (
                self._technology.list_models(binding)
                if probe.state == "healthy"
                else ()
            )
            return StoredOllamaObservation(
                state=state,
                endpoint=probe.endpoint or None,
                version=probe.version,
                models=models,
            )
        except (OSError, RuntimeError, ValueError) as error:
            raise SetupPortError("unable to inspect Ollama") from error

    def ensure_installation(
        self, report: Callable[[str], None]
    ) -> Optional[SetupOllamaTaskLease]:
        try:
            saved = self._load_binding()
            binding = saved or self._default_binding()
            probe = self._technology.probe(binding)
            if probe.state == "healthy":
                report("ollama.reuse")
                self._save_binding(
                    replace(binding, version=probe.version or binding.version)
                )
                return self._acquire_task_lease_for(binding)
            if probe.state == "stopped":
                report("ollama.start")
                lease = self._acquire_task_lease_for(binding)
                if lease is None:
                    self._technology.start_bound_installation(binding)
                started = self._technology.wait_for_healthy(binding)
                if started.state == "healthy":
                    self._save_binding(
                        replace(binding, version=started.version or binding.version)
                    )
                    return lease
            if self.platform == "linux":
                report("ollama.manual")
                raise SetupInstallationPortError(
                    "Linux Ollama 安装需要先在用户终端执行官方安装命令"
                )
            report("ollama.repair" if saved is not None else "ollama.install")
            installer = self._technology.download_official_installer()
            self._technology.run_confirmed_installer(installer, user_confirmed=True)
            installed = self._technology.official_binding_after_install(
                endpoint=binding.api_base,
                installer=installer,
            )
            self._save_binding(installed)
            lease = self._acquire_task_lease_for(installed)
            if lease is None:
                self._technology.start_bound_installation(installed)
            healthy = self._technology.wait_for_healthy(installed)
            if healthy.state != "healthy":
                raise RuntimeError("官方 Ollama 安装后未通过健康检查")
            self._save_binding(
                replace(installed, version=healthy.version or installed.version)
            )
            return lease
        except SetupInstallationPortError:
            raise
        except (OSError, RuntimeError, ValueError) as error:
            raise SetupInstallationPortError("unable to prepare Ollama") from error

    def _acquire_task_lease_for(
        self, binding: SetupOllamaBinding
    ) -> Optional[SetupOllamaTaskLease]:
        if self._acquire_task_lease is None:
            return None
        return self._acquire_task_lease(binding)

    def ensure_model(self, model_id: str, report: Callable[[str], None]) -> str:
        try:
            binding = self._load_binding()
            if binding is None:
                raise RuntimeError("Ollama 连接配置缺失")
            if self._technology.probe(binding).state != "healthy":
                raise RuntimeError("本地 Ollama 未通过健康检查")
            models = set(self._technology.list_models(binding))
            if model_id in models:
                report("model.reuse")
            else:
                report("model.download")
                self._technology.pull_model(binding, model_id)
                if model_id not in set(self._technology.list_models(binding)):
                    raise RuntimeError("Ollama 未确认所选模型已下载")
            return self._save_model(model_id)
        except (OSError, RuntimeError, ValueError) as error:
            raise SetupInstallationPortError(
                "unable to prepare Ollama model"
            ) from error

    def _default_binding(self) -> SetupOllamaBinding:
        return self._technology.default_binding()


__all__ = ("SetupOllamaAdapter", "SetupOllamaTechnologyPort")
