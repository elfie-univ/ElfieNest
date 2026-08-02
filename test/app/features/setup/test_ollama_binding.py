from __future__ import annotations

from pathlib import Path

import pytest

from ai_runtime.storage.provider_connections import ProviderConnectionStore
from app.features.setup.ollama import OllamaSetupService
from app.features.setup.service import create_first_owner, get_setup_progress
from app.infrastructure.ollama_platform import OllamaBinding, OllamaProbe
from app.infrastructure.persistence.store import init_db


class _HealthyAdapter:
    platform = "darwin"

    def probe(self, binding: OllamaBinding | None) -> OllamaProbe:
        assert binding is not None
        return OllamaProbe("healthy", binding.api_base, version="0.12.0")


def test_healthy_existing_ollama_binds_without_installer_or_endpoint_switch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path))
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    create_first_owner(db_path, account_id="owner", password="secret123")
    service = OllamaSetupService(
        adapter=_HealthyAdapter(),  # type: ignore[arg-type]
    )

    probe = service.bind_existing(db_path=db_path, endpoint="http://127.0.0.1:11434")

    assert probe.state == "healthy"
    connection = next(iter(ProviderConnectionStore().load().connections.values()))
    assert connection.connection_id == "ollama_0001"
    assert connection.api_base == "http://127.0.0.1:11434"
    assert get_setup_progress(db_path).current_step == 3
    with pytest.raises(ValueError, match="已固定"):
        service.bind_existing(db_path=db_path, endpoint="http://127.0.0.1:22444")
