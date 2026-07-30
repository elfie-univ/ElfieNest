"""Runtime configuration boundary for an explicit Setup database root."""

from __future__ import annotations

from pathlib import Path

from ai_runtime.food.evidence import ModelEvidenceStore
from ai_runtime.food.store import FoodCatalogStore
from app.features.configuration.runtime_store import (
    read_runtime_config,
    write_runtime_config,
)
from app.features.setup.ollama import OllamaSetupService
from app.infrastructure.ollama_platform import OllamaPlatformAdapter


def build_ollama_setup_service(
    db_path: str,
    adapter: OllamaPlatformAdapter | None = None,
) -> OllamaSetupService:
    root = Path(db_path).resolve().parent
    config_path = root / "config.yaml"
    return OllamaSetupService(
        adapter=adapter or OllamaPlatformAdapter(),
        read_config=lambda: read_runtime_config(config_path),
        write_config=lambda config: write_runtime_config(config_path, config),
        restore_config=lambda config: write_runtime_config(
            config_path, config, backup_existing=False
        ),
        food_catalog_store=FoodCatalogStore(
            root / "foods.yaml", root / "food_history"
        ),
        model_evidence_store=ModelEvidenceStore(root / "model_evidence.yaml"),
    )
