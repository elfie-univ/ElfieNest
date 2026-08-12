from __future__ import annotations

from app.bootstrap.app_wiring.cli_configuration import build_cli_configuration
from app.features.configuration import ListProviderProductsQuery
from infrastructure.persistence.layout.data_home import get_db_path


class _RuntimeMenus:
    def tool_menu(self) -> None:
        pass

    def food_menu(self) -> None:
        pass


def test_cli_configuration_builds_narrow_facades(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))

    container = build_cli_configuration(
        str(get_db_path()),
        runtime_menus=_RuntimeMenus(),
    )

    products = container.providers.list_products(
        container.principal,
        ListProviderProductsQuery(),
    )
    assert any(item.catalog_id == "ollama" for item in products)
    assert container.settings is not None
    assert container.models is not None
