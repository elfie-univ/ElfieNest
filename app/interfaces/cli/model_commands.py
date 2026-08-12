from __future__ import annotations

from typing import Optional, Protocol, Sequence

from app.features.accounts import AccountPrincipal
from app.features.configuration import ProvidersService
from app.interfaces.cli.provider_projection import connections


class CatalogModelView(Protocol):
    model_id: str
    capabilities_text: str
    cost_text: str
    provider_id: str


class LocalModelView(Protocol):
    name: str
    size_bytes: int
    modified_at: str


class LocalModelScanView(Protocol):
    status: str
    error: str | None
    models: Sequence[LocalModelView]


class CliModelCatalogPort(Protocol):
    def list_models(self) -> Sequence[CatalogModelView]: ...

    def scan_local_models(self) -> LocalModelScanView: ...


def dispatch_models(
    providers: ProvidersService,
    principal: AccountPrincipal,
    catalog: CliModelCatalogPort,
    subcmd: Optional[str],
) -> None:
    command = subcmd or "list"
    if command == "list":
        list_models(providers, principal, catalog)
    elif command == "scan":
        scan_models(catalog)


def list_models(
    providers: ProvidersService,
    principal: AccountPrincipal,
    catalog: CliModelCatalogPort,
) -> None:
    print("\n  📦 Model Catalog\n")
    configured = {
        item.catalog_id
        for item in connections(providers, principal)
        if item.enabled and not item.archived
    }

    print(f"  {'Model ID':<35s} {'Capabilities':<25s} {'Cost':<8s} {'Status':<8s}")
    print("  " + "-" * 85)
    for row in catalog.list_models():
        available = row.provider_id == "ollama" or row.provider_id in configured
        status_text = "✅ 可用" if available else "⭕ 未配置"
        print(
            f"  {row.model_id:<35s} {row.capabilities_text:<25s} "
            f"{row.cost_text:<8s} {status_text:<8s}"
        )
    print()


def scan_models(catalog: CliModelCatalogPort) -> None:
    print("\n  🔍 Scanning Ollama local models...\n")
    result = catalog.scan_local_models()
    if result.status == "not_running":
        print("  ❌ Ollama not running")
        print("  💡 Start Ollama: ollama serve")
        print()
        return
    if result.status == "failed":
        print(f"  ❌ Scan failed: {result.error or 'unknown error'}")
        print()
        return
    if not result.models:
        print("  ⚠️  No models in Ollama")
        print("  💡 Use 'ollama pull qwen3.5:0.8b' to download a model")
        return

    print(f"  Found {len(result.models)} local models:\n")
    print(f"  {'Model Name':<30s} {'Size':<12s} {'Modified'}")
    print("  " + "-" * 70)
    for model in result.models:
        size_gb = model.size_bytes / (1024**3)
        size_str = (
            f"{size_gb:.1f} GB"
            if size_gb >= 1
            else f"{model.size_bytes / (1024**2):.0f} MB"
        )
        print(f"  {model.name:<30s} {size_str:<12s} {model.modified_at}")
    print("\n  ✅ Ollama models listed")
    print()


__all__ = (
    "CatalogModelView",
    "CliModelCatalogPort",
    "LocalModelScanView",
    "LocalModelView",
    "dispatch_models",
    "list_models",
    "scan_models",
)
