from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from app.features.configuration.food import StoredModelEvidence
from app.orchestration.lifecycle import ModelOverallState
from infrastructure.models.provider_records import ProviderModelRecord
from infrastructure.persistence.food import SQLiteFoodAdapter
from infrastructure.persistence.food_evidence import record_model_evidence
from infrastructure.persistence.model_health_projection import (
    FoodModelHealthProjectionAdapter,
)
from infrastructure.persistence.nest_db.store import init_db
from infrastructure.persistence.provider_connections import ProviderConnectionStore
from infrastructure.persistence.reports.report_repository import ReportRepository


def test_model_projection_does_not_create_data_or_validation_files_for_a_fresh_root(
    tmp_path: Path,
) -> None:
    home = tmp_path / "elfie-home"

    projection = FoodModelHealthProjectionAdapter(home).read()

    assert projection.state is ModelOverallState.UNCONFIGURED
    assert projection.common_state is ModelOverallState.UNCONFIGURED
    assert projection.emergency_state is ModelOverallState.UNAVAILABLE
    assert not home.exists()


def test_model_projection_reads_persisted_common_and_emergency_evidence(
    tmp_path: Path,
) -> None:
    home = tmp_path / "elfie-home"
    init_db(str(home / "nest.db"))
    provider_store = ProviderConnectionStore(home / "configs" / "providers.yaml")
    provider_store.create(
        catalog_id="ollama",
        alias="Ollama",
        api_base="http://127.0.0.1:11434",
        api_mode="ollama",
        auth_type="none",
        models=(
            ProviderModelRecord("common", "Common", source="manual"),
            ProviderModelRecord("emergency", "Emergency", source="manual"),
        ),
    )
    food = SQLiteFoodAdapter(home / "nest.db")
    common = food.get_package("food_common")
    emergency = food.get_package("food_emergency")
    assert common is not None
    assert emergency is not None
    food.update_package(
        replace(
            common,
            enabled=True,
            primary_model="ollama_0001/common",
        )
    )
    food.update_package(
        replace(
            emergency,
            enabled=True,
            primary_model="ollama_0001/emergency",
        )
    )
    now = datetime.now(timezone.utc).isoformat()
    record_model_evidence(
        (
            StoredModelEvidence(
                reference="ollama_0001/common",
                display_name="Common",
                capabilities=frozenset({"text"}),
                verified=True,
                observed_at=now,
            ),
            StoredModelEvidence(
                reference="ollama_0001/emergency",
                display_name="Emergency",
                capabilities=frozenset({"text"}),
                verified=True,
                observed_at=now,
            ),
        ),
        repository=ReportRepository(home / "reports" / "ai-runtime.sqlite"),
        scope="model:common-emergency",
        trigger="test",
    )

    projection = FoodModelHealthProjectionAdapter(home).read()

    assert projection.state is ModelOverallState.READY
    assert projection.common_state is ModelOverallState.READY
    assert projection.emergency_state is ModelOverallState.READY
