from __future__ import annotations

from ai_runtime.storage.data_home import get_db_path
from app.bootstrap.cli_configuration import build_cli_configuration
from app.features.configuration import ListProviderProductsQuery


def test_cli_configuration_builds_narrow_facades(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))

    container = build_cli_configuration(str(get_db_path()))

    products = container.providers.list_products(
        container.principal,
        ListProviderProductsQuery(),
    )
    assert any(item.catalog_id == "ollama" for item in products)
    assert container.settings is not None
    assert container.models is not None
