from __future__ import annotations

from pathlib import Path

from app.bootstrap.app_wiring.cli_configuration import build_cli_configuration
from app.features.configuration import (
    CapabilitiesService,
    ListProviderProductsQuery,
)
from app.features.configuration.food import FoodService
from infrastructure.persistence.layout.data_home import get_db_path
from infrastructure.persistence.layout.data_layout import final_root_layout


def test_formal_cli_entrypoint_has_no_developer_tool_bridge() -> None:
    source = (
        Path(__file__).resolve().parents[3] / "scripts" / "elfienest.py"
    ).read_text(encoding="utf-8")

    assert "devtools" not in source


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


def test_cli_configuration_binds_capability_validation_to_selected_home(
    monkeypatch,
    tmp_path: Path,
) -> None:
    selected_home = (tmp_path / "selected").resolve()
    selected_layout = final_root_layout(selected_home)
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "app.bootstrap.app_wiring.cli_configuration.build_capability_adapters",
        lambda config_path, secret_path, *, data_home: (
            captured.update(
                config_path=config_path,
                secret_path=secret_path,
                data_home=data_home,
            )
            or (object(), object(), object())
        ),
    )

    container = build_cli_configuration(str(selected_layout.nest_database))
    assert container.capabilities is not None
    assert captured == {
        "config_path": selected_layout.runtime_config,
        "secret_path": selected_layout.auth_env,
        "data_home": selected_home,
    }
