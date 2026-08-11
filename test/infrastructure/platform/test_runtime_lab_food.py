from infrastructure.persistence.food import SQLiteFoodAdapter
from infrastructure.persistence.store import init_db


def test_runtime_lab_store_uses_contract_catalog(tmp_path):
    db_path = tmp_path / "nest.db"
    init_db(str(db_path))
    catalog = SQLiteFoodAdapter(db_path).load()
    assert [item.system_role for item in catalog.ordered_packages()] == [
        "emergency",
        "common",
    ]
