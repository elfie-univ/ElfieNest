from pathlib import Path

from ai_runtime.food.models import FoodPackage, ModelAssignment
from infrastructure.persistence.food_catalog import SQLiteFoodPackageRepository
from infrastructure.persistence.store import init_db


def seed_mock_food(runtime_dir: Path) -> None:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    db_path = runtime_dir / "nest.db"
    init_db(str(db_path))
    SQLiteFoodPackageRepository(db_path).create(
        FoodPackage(
            key="mock",
            display_name="测试粮",
            primary=ModelAssignment("ollama/elfie-mock"),
        )
    )
