"""Security invariants for Card 9 body transition rows."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.infrastructure.persistence.store import get_db, init_db
from app.infrastructure.persistence.transition_body_schema import (
    TransitionLeaseConflict,
    ensure_body_transition_schema,
    start_embodiment_lease_v2,
)
from app.infrastructure.persistence.transition_elfie_nest_schema import (
    ensure_elfie_nest_transition_schema,
)

VALID_HASH = "a" * 64


def test_external_body_revoke_state_requires_matching_timestamp(
    tmp_path: Path,
) -> None:
    # Given: Card 9 transition schema with one final Elfie.
    db_path = init_db(str(tmp_path / "nest.db"))
    with get_db(db_path) as connection:
        _prepare_elfie(connection)

        # When/Then: body secrets must be stored as SHA-256 lowercase hex only.
        for unsafe_hash in ("raw-secret", "", "A" * 64):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO external_bodies
                        (body_id, owner_elfie_id, display_name, body_type,
                         secret_hash, status)
                    VALUES (?, '00000001', 'Toy Body', 'toy', ?, 'active')
                    """,
                    (f"bad-secret-{len(unsafe_hash)}", unsafe_hash),
                )

        # When/Then: active states cannot carry revoked_at.
        for status in ("available", "active"):
            connection.execute(
                """
                INSERT INTO external_bodies
                    (body_id, owner_elfie_id, display_name, body_type,
                     secret_hash, status)
                VALUES (?, '00000001', 'Toy Body', 'toy', ?, ?)
                """,
                (f"body-{status}", VALID_HASH, status),
            )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO external_bodies
                        (body_id, owner_elfie_id, display_name, body_type,
                         secret_hash, status, revoked_at)
                    VALUES (?, '00000001', 'Toy Body', 'toy', ?, ?, ?)
                    """,
                    (
                        f"bad-{status}",
                        VALID_HASH,
                        status,
                        "2026-07-29T00:20:00Z",
                    ),
                )

        # When/Then: revoked rows must carry revoked_at, and accepted revoked
        # rows are rejected consistently by helper and direct lease paths.
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO external_bodies
                    (body_id, owner_elfie_id, display_name, body_type,
                     secret_hash, status)
                VALUES ('bad-revoked', '00000001', 'Toy Body', 'toy', ?, 'revoked')
                """,
                (VALID_HASH,),
            )
        connection.execute(
            """
            INSERT INTO external_bodies
                (body_id, owner_elfie_id, display_name, body_type,
                 secret_hash, status, revoked_at)
            VALUES (
                'body-revoked',
                '00000001',
                'Toy Body',
                'toy',
                ?,
                'revoked',
                '2026-07-29T00:20:00Z'
            )
            """,
            (VALID_HASH,),
        )
        with pytest.raises(TransitionLeaseConflict):
            start_embodiment_lease_v2(
                connection,
                elfie_id="00000001",
                body_id="body-revoked",
                state="hosted",
                lease_expires_at="2026-07-29T00:21:00Z",
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO embodiment_sessions_v2
                    (elfie_id, body_id, state, lease_expires_at, lease_version)
                VALUES (
                    '00000001',
                    'body-revoked',
                    'hosted',
                    '2026-07-29T00:21:00Z',
                    1
                )
                """
            )


def _prepare_elfie(connection: sqlite3.Connection) -> None:
    ensure_elfie_nest_transition_schema(connection)
    ensure_body_transition_schema(connection)
    owner_id = connection.execute(
        """
        INSERT INTO users (username, password_hash, role)
        VALUES ('owner', 'hash', 'owner')
        """
    ).lastrowid
    connection.execute(
        """
        INSERT INTO elfies
            (elfie_id, name, owner_user_id, species, adopted_at, status)
        VALUES ('00000001', '小狐', ?, 'fox', '2026-07-29T00:00:00Z', 'online')
        """,
        (owner_id,),
    )
