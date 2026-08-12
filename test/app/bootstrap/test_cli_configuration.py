from __future__ import annotations

from pathlib import Path

from app.bootstrap.app_wiring.cli_configuration import build_cli_configuration
from app.features.configuration import (
    CapabilitiesService,
    ListProviderProductsQuery,
)
from app.features.configuration.food import FoodService
from infrastructure.persistence.layout.data_home import get_db_path


def test_formal_cli_entrypoint_has_no_developer_tool_bridge() -> None:
    source = (
        Path(__file__).resolve().parents[3] / "scripts" / "elfienest.py"
    ).read_text(encoding="utf-8")

    assert "devtools" not in source
    assert "RuntimeLab" not in source


def test_cli_configuration_builds_narrow_facades(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))

    container = build_cli_configuration(str(get_db_path()))

    products = container.providers.list_products(
        container.principal,
        ListProviderProductsQuery(),
    )
    assert any(item.catalog_id == "ollama" for item in products)
    assert isinstance(container.food, FoodService)
    assert isinstance(container.capabilities, CapabilitiesService)
    assert container.settings is not None
    assert container.models is not None
