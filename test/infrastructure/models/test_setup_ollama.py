from __future__ import annotations

from pathlib import Path

import pytest

from app.orchestration.setup_installation import (
    SetupDownloadedInstaller,
    SetupOllamaBinding,
    SetupOllamaProbe,
)
from infrastructure.models.setup_ollama import SetupOllamaAdapter


class FakeTechnology:
    def __init__(self, platform: str = "darwin") -> None:
        self.platform = platform
        self.actions: list[str] = []

    def default_binding(self) -> SetupOllamaBinding:
        return SetupOllamaBinding(
            "http://127.0.0.1:11434", "darwin", "existing-public", "", ""
        )

    def probe(self, binding: SetupOllamaBinding) -> SetupOllamaProbe:
        _ = binding
        return SetupOllamaProbe("deleted", "http://127.0.0.1:11434")

    def list_models(self, _binding: SetupOllamaBinding) -> tuple[str, ...]:
        self.actions.append("list")
        return ()

    def download_official_installer(self) -> SetupDownloadedInstaller:
        self.actions.append("download")
        return SetupDownloadedInstaller(
            "https://ollama.com/install.sh",
            "hash",
            Path("installer"),
            ("sh", "installer"),
        )

    def run_confirmed_installer(
        self, _installer: SetupDownloadedInstaller, *, user_confirmed: bool
    ) -> None:
        assert user_confirmed is True
        self.actions.append("run")

    def official_binding_after_install(
        self, *, endpoint: str, installer: SetupDownloadedInstaller
    ) -> SetupOllamaBinding:
        _ = installer
        return SetupOllamaBinding(endpoint, "darwin", "official-script", "/ollama", "")

    def start_bound_installation(self, _binding: SetupOllamaBinding) -> None:
        self.actions.append("start")

    def wait_for_healthy(self, binding: SetupOllamaBinding) -> SetupOllamaProbe:
        self.actions.append("wait")
        return SetupOllamaProbe("healthy", binding.api_base, "1.0")

    def pull_model(self, _binding: SetupOllamaBinding, _model_id: str) -> None:
        self.actions.append("pull")


def _adapter(technology: FakeTechnology) -> SetupOllamaAdapter:
    return SetupOllamaAdapter(
        technology=technology,
        load_binding=lambda: None,
        save_binding=lambda _binding: None,
        save_model=lambda model_id: f"ollama_0001/{model_id}",
    )


def test_inspection_is_read_only_and_never_downloads_or_starts() -> None:
    technology = FakeTechnology()
    result = _adapter(technology).inspect()
    assert result.state == "absent"
    assert technology.actions == []


def test_confirmed_workflow_action_owns_external_install_side_effects() -> None:
    technology = FakeTechnology()
    reports: list[str] = []
    _adapter(technology).ensure_installation(reports.append)
    assert reports == ["ollama.install"]
    assert technology.actions == ["download", "run", "start", "wait"]


def test_linux_setup_never_downloads_or_runs_a_hidden_privileged_installer() -> None:
    technology = FakeTechnology(platform="linux")

    with pytest.raises(RuntimeError, match="终端"):
        _adapter(technology).ensure_installation(lambda _action: None)

    assert technology.actions == []
