from __future__ import annotations

from pathlib import Path

from app.bootstrap.app_wiring import adoption as adoption_bootstrap
from infrastructure.persistence.nest_db.store import get_db, init_db


class _CapturingWorkspace:
    def materialize(self, reservation: object) -> str:
        self.reservation = reservation
        return "/unused"


def test_default_seed_uses_a_workspace_safe_id(monkeypatch, tmp_path: Path) -> None:
    # Given: an Owner and a fresh production data root.
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    with get_db(db_path) as connection:
        connection.execute(
            "INSERT INTO users (account_id, password_hash, role) VALUES (?, ?, ?)",
            ("owner", "hash", "owner"),
        )
        connection.commit()
    workspace = _CapturingWorkspace()
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path / "elfienest"))
    monkeypatch.setattr(
        adoption_bootstrap.FinalElfieWorkspaceAdapter,
        "from_database_path",
        lambda _data_home: workspace,
    )

    # When: the service creates its default elfie.
    assert adoption_bootstrap.seed_single_elfie(db_path) is True

    # Then: the stable directory ID is separate from the visible display name.
    with get_db(db_path) as connection:
        row = connection.execute("SELECT elfie_id, name FROM elfies").fetchone()
    assert row["elfie_id"] == "00000001"
    assert row["name"] == "Aifei"
    assert workspace.reservation.elfie_id == "00000001"
