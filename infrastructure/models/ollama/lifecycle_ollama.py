"""Lifecycle projection for the already configured public Ollama installation."""

from __future__ import annotations

from app.features.configuration.providers import (
    ProviderLocalTechnologyPort,
    ProviderPortError,
)


class OllamaLifecycleAdapter:
    """Expose only readiness and best-effort start to Runtime lifecycle."""

    def __init__(self, technology: ProviderLocalTechnologyPort) -> None:
        self._technology = technology

    def ready(self) -> bool:
        try:
            binding = self._technology.default_binding()
            return self._technology.probe(binding).state == "healthy"
        except ProviderPortError:
            return False

    def prepare(self) -> None:
        try:
            binding = self._technology.default_binding()
            if self._technology.probe(binding).state != "healthy":
                self._technology.start(binding)
        except ProviderPortError:
            return


__all__ = ("OllamaLifecycleAdapter",)
