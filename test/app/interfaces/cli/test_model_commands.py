from __future__ import annotations

from dataclasses import dataclass

from _pytest.capture import CaptureFixture

from app.interfaces.cli import model_commands
from test.app.interfaces.cli.configuration_test_support import (
    FakeProvidersService,
    manager_principal,
)


@dataclass(frozen=True)
class CatalogModel:
    model_id: str
    capabilities_text: str
    cost_text: str
    provider_id: str


@dataclass(frozen=True)
class LocalModel:
    name: str
    size_bytes: int
    modified_at: str


@dataclass(frozen=True)
class ScanResult:
    status: str
    error: str | None
    models: tuple[LocalModel, ...]


class FakeCatalog:
    def __init__(self) -> None:
        self.scan = ScanResult(
            "available",
            None,
            (LocalModel("qwen:test", 2 * 1024**3, "today"),),
        )

    def list_models(self):
        return (
            CatalogModel("openai/gpt-test", "text, code", "低", "openai"),
            CatalogModel("ollama/qwen:test", "text", "免费", "ollama"),
        )

    def scan_local_models(self):
        return self.scan


def test_list_models_uses_provider_facade_for_availability(
    capsys: CaptureFixture[str],
) -> None:
    providers = FakeProvidersService()
    providers.add_connection("openai")

    model_commands.list_models(providers, manager_principal(), FakeCatalog())

    output = capsys.readouterr().out
    assert "openai/gpt-test" in output
    assert output.count("✅ 可用") == 2


def test_scan_models_preserves_size_and_modified_output(
    capsys: CaptureFixture[str],
) -> None:
    model_commands.scan_models(FakeCatalog())

    output = capsys.readouterr().out
    assert "qwen:test" in output
    assert "2.0 GB" in output
    assert "today" in output
