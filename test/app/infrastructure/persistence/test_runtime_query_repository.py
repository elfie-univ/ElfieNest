"""Integration contract for API-facing reads from the final root database."""

from pathlib import Path

from app.infrastructure.persistence.final_schema import create_final_nest_database
from app.infrastructure.persistence.runtime_query_repository import (
    RuntimeQueryRepository,
)
from app.infrastructure.persistence.session_repository import hash_session_token
from app.infrastructure.persistence.store import get_db


def test_runtime_queries_use_final_users_and_elfies(tmp_path: Path) -> None:
    # Given: one account and one Elfie in the final root schema.
    db_path = create_final_nest_database(tmp_path / "nest.db")
    with get_db(str(db_path)) as connection:
        owner_id = int(
            connection.execute(
                "INSERT INTO users(username,password_hash,role) VALUES(?,?,?)",
                ("owner", "hash", "owner"),
            ).lastrowid
        )
        connection.execute(
            """INSERT INTO elfies(
                   elfie_id,name,owner_user_id,species,adopted_at,status
               ) VALUES(?,?,?,?,?,?)""",
            ("00000001", "小白", owner_id, "biped", "2026-07-30T00:00:00Z", "offline"),
        )
        connection.commit()

    # When: the API-facing repository resolves account and ownership.
    repository = RuntimeQueryRepository(str(db_path))
    account = repository.find_account_by_username("owner")

    # Then: only final-table records are returned.
    assert account is not None
    assert account.user_id == owner_id
    assert repository.owner_id_for_elfie("00000001") == owner_id
    assert repository.elfie_is_owned_by("00000001", owner_id) is True
    assert repository.list_elfies_for_owner(owner_id)[0].elfie_id == "00000001"


def test_password_change_keeps_only_the_current_final_session(tmp_path: Path) -> None:
    # Given: one account with two hashed final sessions.
    db_path = create_final_nest_database(tmp_path / "nest.db")
    repository = RuntimeQueryRepository(str(db_path))
    with get_db(str(db_path)) as connection:
        owner_id = int(
            connection.execute(
                "INSERT INTO users(username,password_hash,role) VALUES(?,?,?)",
                ("owner", "old-hash", "owner"),
            ).lastrowid
        )
        connection.commit()
    current_token = "current-token"
    with get_db(str(db_path)) as connection:
        connection.executemany(
            "INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(?,?,?)",
            (
                (hash_session_token(current_token), owner_id, "2099-01-01T00:00:00Z"),
                (hash_session_token("other-token"), owner_id, "2099-01-01T00:00:00Z"),
            ),
        )
        connection.commit()

    # When: the password is changed while preserving the current cookie session.
    repository.update_password_and_revoke_other_sessions(
        owner_id, "new-hash", current_token
    )

    # Then: the password changed and only the current session remains active.
    account = repository.find_account_by_id(owner_id)
    assert account is not None
    assert account.password_hash == "new-hash"
    with get_db(str(db_path)) as connection:
        remaining = int(
            connection.execute(
                """SELECT COUNT(*) FROM sessions
                   WHERE user_id=? AND revoked_at IS NULL""",
                (owner_id,),
            ).fetchone()[0]
        )
    assert remaining == 1
