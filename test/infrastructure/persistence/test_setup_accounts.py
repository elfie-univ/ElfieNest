from __future__ import annotations

from pathlib import Path

from app.bootstrap.app_wiring.accounts import build_accounts_service
from infrastructure.persistence.nest_db.store import get_db, init_db
from infrastructure.persistence.setup_accounts import SetupAccountsAdapter
from test.app.interfaces.api._helpers import create_test_owner


def test_setup_finalization_persists_default_landing_page(tmp_path: Path) -> None:
    db_path = init_db(str(tmp_path / "nest.db"))
    owner_id = create_test_owner(db_path)
    adapter = SetupAccountsAdapter(build_accounts_service(db_path))

    adapter.set_default_landing_page(owner_id, "chat")

    with get_db(db_path) as connection:
        page = connection.execute(
            "SELECT default_landing_page FROM users WHERE id=?", (owner_id,)
        ).fetchone()[0]
    assert page == "chat"
