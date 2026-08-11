"""Public Ollama technology adapter for Provider administration."""

from __future__ import annotations

import os
from dataclasses import replace

from app.features.configuration import (
    ProviderPortError,
    StoredLocalProviderBinding,
    StoredLocalProviderCandidate,
    StoredLocalProviderProbe,
)
from infrastructure.models.providers.profiles import PROVIDER_CATALOG

from .ollama_platform import (
    DEFAULT_OLLAMA_ENDPOINT,
    OllamaBinding,
    OllamaPlatformAdapter,
    wait_for_healthy,
)
from .ollama_platform_commands import official_launch_target


class PublicOllamaProviderAdapter:
    def __init__(self, platform: OllamaPlatformAdapter | None = None) -> None:
        self._platform = platform or OllamaPlatformAdapter()

    def default_binding(self) -> StoredLocalProviderBinding:
        try:
            target, install_kind = official_launch_target(self._platform.platform)
        except (OSError, RuntimeError):
            target, install_kind = "", "existing-public"
        return StoredLocalProviderBinding(
            api_base=DEFAULT_OLLAMA_ENDPOINT,
            platform=self._platform.platform,
            install_kind=install_kind,
            launch_target=target,
        )

    def probe(
        self,
        binding: StoredLocalProviderBinding,
    ) -> StoredLocalProviderProbe:
        try:
            item = self._platform.probe(_platform_binding(binding))
            return StoredLocalProviderProbe(
                item.state,
                item.endpoint,
                item.version,
                item.detail,
            )
        except (OSError, RuntimeError, ValueError) as error:
            raise ProviderPortError("Unable to probe local Provider") from error

    def available_memory_gb(self) -> int:
        try:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
        except (AttributeError, OSError, ValueError):
            return 0
        if not isinstance(pages, int) or not isinstance(page_size, int):
            return 0
        return max(0, pages * page_size // (1024**3))

    def candidate_models(self) -> tuple[StoredLocalProviderCandidate, ...]:
        return tuple(
            StoredLocalProviderCandidate(
                model_id=item.model_id,
                display_name=item.model_id,
                recommended=item.recommended,
            )
            for item in PROVIDER_CATALOG.ollama_recommended_models
        )

    def list_models(self, binding: StoredLocalProviderBinding) -> tuple[str, ...]:
        try:
            return self._platform.list_models(_platform_binding(binding))
        except (OSError, RuntimeError, ValueError) as error:
            raise ProviderPortError("Unable to list local Provider models") from error

    def install_official(self) -> StoredLocalProviderBinding:
        try:
            installer = self._platform.download_official_installer()
            self._platform.run_confirmed_installer(installer, user_confirmed=True)
            binding = self._platform.official_binding_after_install(
                endpoint=DEFAULT_OLLAMA_ENDPOINT,
                installer=installer,
            )
            self._platform.start_bound_installation(binding)
            probe = wait_for_healthy(self._platform, binding)
            if probe.state != "healthy":
                raise RuntimeError("官方 Ollama 安装后未通过健康检查")
            return _stored_binding(
                replace(binding, version=probe.version or binding.version)
            )
        except (
            FileNotFoundError,
            OSError,
            PermissionError,
            RuntimeError,
            ValueError,
        ) as error:
            raise ProviderPortError("Unable to install local Provider") from error

    def start(
        self,
        binding: StoredLocalProviderBinding,
    ) -> StoredLocalProviderBinding:
        platform_binding = _platform_binding(binding)
        try:
            self._platform.start_bound_installation(platform_binding)
            probe = wait_for_healthy(self._platform, platform_binding)
            if probe.state != "healthy":
                raise RuntimeError("Ollama 启动后仍未健康")
            return replace(binding, version=probe.version or binding.version)
        except (
            FileNotFoundError,
            OSError,
            PermissionError,
            RuntimeError,
            ValueError,
        ) as error:
            raise ProviderPortError("Unable to start local Provider") from error

    def pull_model(
        self,
        binding: StoredLocalProviderBinding,
        model_id: str,
    ) -> None:
        try:
            self._platform.pull_model(_platform_binding(binding), model_id)
        except (OSError, RuntimeError, ValueError) as error:
            raise ProviderPortError("Unable to pull local Provider model") from error


def _platform_binding(item: StoredLocalProviderBinding) -> OllamaBinding:
    return OllamaBinding(
        api_base=item.api_base,
        platform=item.platform,
        install_kind=item.install_kind,
        launch_target=item.launch_target,
        version=item.version,
        installer_source_url=item.installer_source_url,
        installer_sha256=item.installer_sha256,
    )


def _stored_binding(item: OllamaBinding) -> StoredLocalProviderBinding:
    return StoredLocalProviderBinding(
        api_base=item.api_base,
        platform=item.platform,
        install_kind=item.install_kind,
        launch_target=item.launch_target,
        version=item.version,
        installer_source_url=item.installer_source_url,
        installer_sha256=item.installer_sha256,
    )


__all__ = ("PublicOllamaProviderAdapter",)
