from __future__ import annotations

from pathlib import Path

from app.infrastructure.persistence.store import get_db, init_db
from scripts import serve


class _CapturingGenerator:
    def generate(self, **kwargs: str) -> None:
        self.elfie_id = kwargs["elfie_id"]


def test_default_seed_uses_a_workspace_safe_id(monkeypatch, tmp_path: Path) -> None:
    # Given: an Owner and a fresh production data root.
    db_path = str(tmp_path / "nest.db")
    init_db(db_path)
    with get_db(db_path) as connection:
        connection.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("owner", "hash", "owner"),
        )
        connection.commit()
    generator = _CapturingGenerator()
    monkeypatch.setenv("ELFIE_HOME", str(tmp_path / "elfienest"))
    monkeypatch.setattr(serve, "ElfieGenerator", lambda: generator)

    # When: the service creates its default elfie.
    assert serve.seed_single_elfie(db_path) is True

    # Then: the stable directory ID is separate from the visible display name.
    with get_db(db_path) as connection:
        row = connection.execute("SELECT elfie_id, name FROM elfie_registry").fetchone()
    assert row["elfie_id"] == "elfie_default"
    assert row["name"] == "Aifei"
    assert generator.elfie_id == "elfie_default"
