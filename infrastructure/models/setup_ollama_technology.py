"""Typed Setup technology Adapter over the one public Ollama platform implementation."""

from __future__ import annotations

from typing import cast

from app.orchestration.setup_installation import (
    SetupDownloadedInstaller,
    SetupOllamaBinding,
    SetupOllamaProbe,
)
from infrastructure.models.ollama.ollama_platform import (
    DownloadedInstaller,
    OllamaBinding,
    OllamaPlatformAdapter,
    wait_for_healthy,
)
from infrastructure.models.ollama.ollama_platform_commands import official_launch_target


class PublicOllamaSetupTechnologyAdapter:
    def __init__(self, platform: OllamaPlatformAdapter | None = None) -> None:
        self._platform = platform or OllamaPlatformAdapter()

    @property
    def platform(self) -> str:
        return cast(str, self._platform.platform)

    def default_binding(self) -> SetupOllamaBinding:
        try:
            target, _ = official_launch_target(self._platform.platform)
        except RuntimeError:
            target, install_kind = "", "existing-public"
        else:
            # A default binding describes an already present public installation.
            # Official provenance is only available after the explicit installer
            # flow records its source and digest; treating this initial binding as
            # ``official-script`` makes a healthy existing Ollama look corrupt.
            install_kind = "existing-public"
        return SetupOllamaBinding(
            api_base="http://127.0.0.1:11434",
            platform=self._platform.platform,
            install_kind=install_kind,
            launch_target=target,
            version="",
        )

    def probe(self, binding: SetupOllamaBinding) -> SetupOllamaProbe:
        item = self._platform.probe(_binding(binding))
        return SetupOllamaProbe(item.state, item.endpoint, item.version)

    def list_models(self, binding: SetupOllamaBinding) -> tuple[str, ...]:
        return self._platform.list_models(_binding(binding))

    def download_official_installer(self) -> SetupDownloadedInstaller:
        item = self._platform.download_official_installer()
        return SetupDownloadedInstaller(
            item.source_url, item.sha256, item.script_path, item.command
        )

    def run_confirmed_installer(
        self, installer: SetupDownloadedInstaller, *, user_confirmed: bool
    ) -> None:
        self._platform.run_confirmed_installer(
            _installer(installer), user_confirmed=user_confirmed
        )

    def official_binding_after_install(
        self, *, endpoint: str, installer: SetupDownloadedInstaller
    ) -> SetupOllamaBinding:
        item = self._platform.official_binding_after_install(
            endpoint=endpoint,
            installer=_installer(installer),
        )
        return _setup_binding(item)

    def start_bound_installation(self, binding: SetupOllamaBinding) -> None:
        self._platform.start_bound_installation(_binding(binding))

    def wait_for_healthy(self, binding: SetupOllamaBinding) -> SetupOllamaProbe:
        item = wait_for_healthy(self._platform, _binding(binding))
        return SetupOllamaProbe(item.state, item.endpoint, item.version)

    def pull_model(self, binding: SetupOllamaBinding, model_id: str) -> None:
        self._platform.pull_model(_binding(binding), model_id)


def _binding(item: SetupOllamaBinding) -> OllamaBinding:
    return OllamaBinding(
        item.api_base,
        item.platform,
        item.install_kind,
        item.launch_target,
        item.version,
        item.installer_source_url,
        item.installer_sha256,
    )


def _setup_binding(item: OllamaBinding) -> SetupOllamaBinding:
    return SetupOllamaBinding(
        item.api_base,
        item.platform,
        item.install_kind,
        item.launch_target,
        item.version,
        item.installer_source_url,
        item.installer_sha256,
    )


def _installer(item: SetupDownloadedInstaller) -> DownloadedInstaller:
    return DownloadedInstaller(
        item.source_url, item.sha256, item.script_path, item.command
    )


__all__ = ("PublicOllamaSetupTechnologyAdapter",)
