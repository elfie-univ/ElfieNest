from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from infrastructure.persistence import model_execution_config


def test_model_execution_source_reads_connections_from_selected_home(
    monkeypatch,
    tmp_path: Path,
) -> None:
    selected_home = tmp_path / "selected"
    (selected_home / "configs").mkdir(parents=True)
    (selected_home / "configs" / "providers.yaml").write_text("{}\n", encoding="utf-8")
    captured: list[Path] = []

    class Store:
        def __init__(self, path: Path) -> None:
            captured.append(path)

        def load(self):
            return SimpleNamespace(connections={})

    monkeypatch.setattr(model_execution_config, "ProviderConnectionStore", Store)
    source = model_execution_config.LocalModelExecutionConfigSource(
        provider_catalog=SimpleNamespace(products={}),
        config_home=selected_home,
    )

    assert source.load_connections() == {}
    assert captured == [selected_home / "configs" / "providers.yaml"]
