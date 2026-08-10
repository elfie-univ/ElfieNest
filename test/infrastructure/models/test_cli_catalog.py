from __future__ import annotations

import json

from infrastructure.models import CliModelCatalogAdapter


class Response:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()


def test_cli_catalog_projects_existing_visible_model_metadata() -> None:
    rows = CliModelCatalogAdapter().list_models()

    by_id = {row.model_id: row for row in rows}
    assert by_id["openai/gpt-4o"].capabilities_text.startswith("text, vision")
    assert by_id["ollama/qwen3.5:0.8b"].cost_text == "免费"


def test_cli_catalog_scans_existing_ollama_inventory(monkeypatch) -> None:
    monkeypatch.setattr(
        "infrastructure.models.cli_catalog.urllib.request.urlopen",
        lambda *_args, **_kwargs: Response(
            {
                "models": [
                    {
                        "name": "qwen:test",
                        "size": 123,
                        "modified_at": "today",
                    }
                ]
            }
        ),
    )

    result = CliModelCatalogAdapter().scan_local_models()

    assert result.status == "available"
    assert result.models[0].name == "qwen:test"
    assert result.models[0].size_bytes == 123
