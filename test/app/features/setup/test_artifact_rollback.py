from pathlib import Path

import pytest

from ai_runtime.food.evidence import ModelEvidenceStore
from ai_runtime.food.store import FoodCatalogStore
from app.features.setup.artifact_rollback import rollback_artifacts


def test_model_artifact_rollback_restores_existing_files_and_history(
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "model_evidence.yaml"
    catalog_path = tmp_path / "foods.yaml"
    history_dir = tmp_path / "food_history"
    history_dir.mkdir()
    old_history = history_dir / "foods-old.yaml"
    evidence_path.write_bytes(b"old evidence")
    catalog_path.write_bytes(b"old foods")
    old_history.write_bytes(b"old history")
    evidence_store = ModelEvidenceStore(evidence_path)
    catalog_store = FoodCatalogStore(catalog_path, history_dir)

    with pytest.raises(RuntimeError, match="reject"):
        with rollback_artifacts(evidence_store, catalog_store):
            evidence_path.write_bytes(b"new evidence")
            catalog_path.write_bytes(b"new foods")
            (history_dir / "foods-new.yaml").write_bytes(b"new history")
            raise RuntimeError("reject")

    assert evidence_path.read_bytes() == b"old evidence"
    assert catalog_path.read_bytes() == b"old foods"
    assert old_history.read_bytes() == b"old history"
    assert not (history_dir / "foods-new.yaml").exists()


def test_model_artifact_rollback_keeps_successful_changes(tmp_path: Path) -> None:
    evidence_path = tmp_path / "model_evidence.yaml"
    catalog_path = tmp_path / "foods.yaml"
    history_dir = tmp_path / "food_history"
    evidence_store = ModelEvidenceStore(evidence_path)
    catalog_store = FoodCatalogStore(catalog_path, history_dir)

    with rollback_artifacts(evidence_store, catalog_store):
        evidence_path.write_bytes(b"new evidence")
        catalog_path.write_bytes(b"new foods")

    assert evidence_path.read_bytes() == b"new evidence"
    assert catalog_path.read_bytes() == b"new foods"
