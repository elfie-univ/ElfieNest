from app.infrastructure.persistence.food_packages import SQLiteFoodPackageRepository
from infrastructure.persistence.store import init_db


def test_runtime_lab_store_uses_contract_catalog(tmp_path):
    db_path = tmp_path / "nest.db"
    init_db(str(db_path))
    catalog = SQLiteFoodPackageRepository(db_path).load()
    assert [item.system_role for item in catalog.ordered_packages()] == [
        "emergency",
        "common",
    ]
