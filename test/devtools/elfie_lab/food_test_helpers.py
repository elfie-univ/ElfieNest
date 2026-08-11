from pathlib import Path

from app.features.configuration.food import StoredFoodPackage
from infrastructure.persistence.food import SQLiteFoodAdapter
from infrastructure.persistence.nest_db.store import init_db


def seed_mock_food(runtime_dir: Path) -> None:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    db_path = runtime_dir / "nest.db"
    init_db(str(db_path))
    SQLiteFoodAdapter(db_path).create_package(
        StoredFoodPackage(
            food_id="mock",
            display_name="测试粮",
            primary_model="ollama/elfie-mock",
        )
    )
